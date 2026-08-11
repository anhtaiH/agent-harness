# Paired sample — a case where the CONTROL won (primary judge)

These are the cases most useful for challenging our conclusions. Read both
outputs and form your own view before reading the judge's reason.

- case: `golden-missing-generated-runtime` · repetition 1 · judge `primary`
- fixture ground truth: `{"decision": "request_changes", "priority": "P1", "finding": "A generated project can import a runtime file that was not emitted.", "specialists": ["public_contract"], "proof": "code_path_proof"}`

## Judge's stated reason (read LAST, after forming your own view)

> Both outputs correctly identify the fixture's P1 blocker (hook emitted on hasInteraction while interaction-runtime is gated on executable actions, yielding a dangling import for empty timelines), both choose request_changes at P1, both respect preview-only, and both localize to the emission line with a code-path argument. B is stronger at the margins: it distinguishes the failure mode by pipeline (build-time in bundled pipelines vs lazy unhandled rejection in transpile-only), offers two bounded fix options with a reasoned preference plus a hook-implies-runtime invariant test, adds a well-calibrated non-blocking P2 on the dynamic import's silent-rejection risk, and explicitly withholds an unverifiable candidate finding, showing better disconfirmation discipline. A is clean and accurate but thinner on non-blocking value and fix framing. No critical failures on either side.

---

## Output A — CONTROL (frozen v19)

```
Both passes are done: the independent reviewer surfaced the dangling-import defect plus predicate duplication and a missing-test gap, and the adversarial verifier confirmed the blocker at P1 (not P0), with the caveat that the failure surfaces at build time in bundled pipelines but as a lazy runtime rejection in transpile-only pipelines. Here is the proposed review preview. Nothing has been posted or submitted.

~~~markdown
## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This PR makes the generator emit an `interaction-hook.ts` file whenever a component has `hasInteraction`, with the hook lazily importing `./interaction-runtime`. I reviewed the emission logic, the generated-output contract between the hook and the runtime emitter, and test coverage. There is one P1 blocker: the hook is emitted under a broader condition than the runtime module it imports, so a component referencing an empty timeline produces generated output with an unresolvable import. The remaining comments are non-blocking suggestions about the import's failure mode and test coverage.

## QA Spec

### Setup

1. A project with three components: one referencing a timeline with executable actions, one referencing an empty timeline (no executable actions), and one with no interaction at all.

### Generated output consistency

- When the project is generated with the empty-timeline component:
  - [ ] The generated project typechecks and builds successfully
  - [ ] No emitted file imports a module that does not exist in the output
- When the project is generated with the executable-actions component:
  - [ ] Both `interaction-hook.ts` and `interaction-runtime` are present in the output
  - [ ] The generated app runs the interaction hook without an unhandled rejection

### Regression smoke

Spend a few minutes around:
- The no-interaction component: confirm no `interaction-hook.ts` is emitted and generation output is unchanged from before this PR.

### Proposed inline comments

#### 1. `generator/hooks.ts` (added line: `if (component.hasInteraction) emit('interaction-hook.ts')`)

[P1 · Change request]

Can we make hook emission and runtime emission use the same "has executable actions" rule?

A component that references an empty timeline still sets `hasInteraction`, so this line emits `interaction-hook.ts`, but per the runtime emitter's current condition `interaction-runtime` is only created when the timeline has executable actions. The generated project then contains an unresolvable module specifier: in a typechecked or bundled pipeline that fails the customer's build outright, and in a transpile-only pipeline it ships and fails lazily as an unhandled rejection the first time the hook runs. I'd treat this as P1 because generation succeeds while producing broken output for a reachable, ordinary input, and there's no fallback.

Two ways to fix it, either of which works:

1. Gate this emit on the same predicate the runtime emitter uses (preferably a shared helper, so the two conditions can't drift apart again), or
2. Always emit a no-op `interaction-runtime` stub whenever the hook is emitted.

Option 1 seems better since it keeps one source of truth for "this interaction is real" and keeps the output minimal. Please also add a generated-output test for the empty-timeline case, plus an invariant check that `interaction-hook.ts` being present implies `interaction-runtime` is present. That second test catches every future regression of this class regardless of how the predicates are worded.

#### 2. `templates/interaction-hook.ts` (added line: `import('./interaction-runtime')`)

[P2 · Suggestion]

If lazy loading isn't specifically needed here, a static `import './interaction-runtime'` would make any missing-runtime mismatch fail at build time instead of at runtime.

The dynamic `import()` returns a promise with no visible rejection handling, so in pipelines that don't statically resolve dynamic specifiers, a missing or renamed runtime module surfaces as a silent unhandled rejection in the end user's app rather than a generation-time or build-time error. If lazy loading is intentional, adding explicit rejection handling with an actionable error message would get the same fail-fast benefit. This doesn't block the PR, especially once the P1 predicate fix removes the known trigger.
~~~

The proposed decision is Request Changes on the strength of the one P1: the fix is small (share the emission predicate or emit a stub runtime) and the highest-leverage test to request is the hook-implies-runtime co-presence invariant. A fourth candidate about `emit` possibly writing the same hook path repeatedly across multiple components was kept private since the bundle doesn't show `emit`'s pathing or dedupe semantics, so it couldn't be verified. If you'd like, I can adjust wording or priorities before anything is submitted.
```

---

## Output B — TREATMENT (skill v2.0.0)

```
The review is complete. Here's the result.

I reviewed the PR bundle following the pull-request review skill in preview mode. The change makes the generator emit an `interaction-hook.ts` (which imports `./interaction-runtime`) whenever a component has `hasInteraction` set. The supplied repository context states that the runtime emitter only creates `interaction-runtime` when a referenced timeline has executable actions, while empty timelines still set `hasInteraction`. That predicate mismatch means a component referencing only an empty timeline gets a generated project containing an import of a module that was never emitted — a broken generated artifact with no fallback. An independent adversarial verifier tried to refute this and confirmed it with high confidence (the only escape hatch requires an unbundled, un-type-checked toolchain plus a lazy call site, none of which is evidenced). The mismatch is newly introduced by this PR, so it blocks as a P1, and the proposed decision is Request Changes. Nothing has been posted or submitted.

---

## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This PR emits an interaction hook into generated projects whenever a component references an interaction, with the hook importing the interaction runtime. The main review surface is generated-output integrity: the hook is emitted on `hasInteraction`, but the runtime module it imports is only emitted when a referenced timeline has executable actions, and empty timelines still set `hasInteraction`. That mismatch is a P1 blocker because a component referencing only an empty timeline produces a generated project that imports a file the pipeline never emitted, so the artifact fails at build or module resolution with no fallback for the downstream developer. Details and a suggested fix are in the inline comment; no other blocking issues found.

## QA Spec

### Setup

1. Create a source project with three components: one referencing a timeline that contains executable actions, one referencing a timeline with no actions (empty), and one with no interaction reference.

### Generated output

- When generating the project with the executable-action timeline:
  - [ ] `interaction-hook.ts` and `interaction-runtime` are both present in the output
  - [ ] the generated project builds without manual file changes
- When generating the project where the only referenced timeline is empty:
  - [ ] the generated project builds without manual file changes
  - [ ] no emitted file imports a module that was not emitted
- When generating the component with no interaction:
  - [ ] no interaction hook is emitted

### Regression smoke

Spend a few minutes around:
- regenerating an existing interaction-free project and confirming its output is unchanged by this PR

### Proposed inline comments

#### 1. `generator/hooks.ts` (added `hasInteraction` emission line)

[P1 · Change request]

Can we gate hook emission on the same rule the runtime emitter uses, rather than on `hasInteraction`?

A component that references an empty timeline still sets `hasInteraction`, so this line emits `interaction-hook.ts`, but the runtime emitter only creates `interaction-runtime` when the timeline has executable actions. The generated project then contains `import('./interaction-runtime')` with no such module emitted, so the artifact fails at build or module resolution. I'd treat this as P1 because it breaks the normal generated-output path for a reachable input class and the downstream developer has no fallback.

A shared predicate (for example, "has executable actions") used by both the hook emission and the runtime emitter would keep the emitted import and the emitted module aligned, and would prevent the two rules from drifting again. Alternatively, emit `interaction-runtime` whenever the hook is emitted. Please also add a generated-output case for the empty-timeline component that asserts the project builds.
```
