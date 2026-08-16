# Activation and Durability

Load this reference for the state machine, hook behavior, resume sequence, and
the durable templates. `UG` = `python3 <skill-dir>/scripts/ultragoal.py`.

- [What activation replaces](#what-activation-replaces)
- [Lifecycle states](#lifecycle-states)
- [The three hooks](#the-three-hooks)
- [Guardrails on the gate](#guardrails-on-the-gate)
- [Apply the artifact rule](#apply-the-artifact-rule)
- [Living goal and plan](#living-goal-and-plan)
- [Maintain and resume](#maintain-and-resume)
- [Running unattended](#running-unattended)

## What Activation Replaces

Other harnesses expose a native goal object with create/get/update calls. Claude
Code does not. Activation here means three things happen together:

1. A durable bundle exists on disk under `.claude/goals/<slug>/`.
2. `state.json` moves to `active`, which arms the `Stop` gate.
3. A `SessionStart` hook is installed so the goal survives the session.

Never describe a goal as active unless `UG status` says `ACTIVE`. Writing goal
files without activating is Design mode, and should be reported as `drafted`.

## Lifecycle States

| Status | Gate | Meaning | Leaves via |
| --- | --- | --- | --- |
| `drafted` | off | bundle exists, contract not yet armed | `activate` |
| `active` | **on** | work is in progress; turns cannot end | `complete`, `block`, `await`, `waiting`, `pause` |
| `waiting` | off | an external process must finish first | `resume` |
| `awaiting-input` | off | a consequential human decision is pending | `resume` |
| `paused` | off | user stood it down, or a budget tripped | `resume` |
| `blocked` | off | evidence-backed external blocker, no progress left | `resume` |
| `complete` | off | proof accepted | terminal |

Choose the release deliberately. `waiting` and `await` are not the same:
`waiting` is a machine you are waiting on, `await` is a person. `pause` is a
stand-down, `block` is a claim that nothing else can move — and `block` requires
`--evidence`, because difficulty and uncertainty are not blockers.

Before entering `waiting`, arm the thing that will wake you: a background `Bash`
task, a `Monitor` on the log or CI feed, a PR activity subscription, or a
scheduled wake. Record it with `--signal`. Do not sleep-poll.

## The Three Hooks

**Stop gate** (`hook stop`, armed by skill frontmatter). While a goal is
`active`, it returns `decision: "block"` and re-injects the contract, phase,
next action, unmet acceptance conditions, last verifier result, and the exact
release commands. This is what makes long-running execution real: the turn
cannot end merely because the model felt finished. It also repairs context loss
— after compaction the goal state comes back on the next stop attempt.

**Session resume** (`hook session-start`, installed by `activate` into
`.claude/settings.local.json`). On `startup`, `resume`, `clear`, and `compact`
it injects the full status of every open goal plus the resume sequence. This is
the hook that cannot come from skill frontmatter, because by the time a skill
loads the session has already started.

**Anti-cheating guard** (`hook pre-tool`, armed by skill frontmatter). Narrow
and high-confidence. It denies force-pushes and `--no-verify` while a goal is
active, denies deleting the goal bundle, and *asks* before removing or skipping
tests or editing the acceptance/verifier sections of `goal.md`. It targets the
goal's own proof surface; ordinary development is untouched. `UG config --guard
off` disables it per goal.

All three exit silently when no goal is active, and any internal error exits 0
with no output. A broken goal file can never wedge a session.

## Guardrails on the Gate

The gate is bounded in three independent ways, and every limit auto-pauses
rather than stopping silently:

- **Continuation budget** — default 40 blocked stops. Set at creation with
  `--max-continues`, or later with `UG config --max-continues N`.
- **Anti-spin** — 3 consecutive continuations that record no progress. Progress
  means a `verify`, `evidence`, `met`, `phase`, `next`, `attempt`, `lesson`, or
  `assurance` call. Spinning in the model's head does not count.
- **Wall clock** — optional, `--deadline-minutes` at creation.

The user always outranks all three: Esc interrupts, `/ultragoal pause` stands
down. Say so when you report activation.

## Apply the Artifact Rule

Use existing project-owned goal, plan, worklog, or execution-plan conventions
when they already provide equivalent state; do not create a competing format.
Otherwise use the fallback bundle. This rule is independent of route, assurance
tier, duration estimate, and file count.

Goal fit is the ceremony boundary. If the work is a routine one-pass task with
no credible need for persistent execution, recommend the ordinary task and do
not activate. Design and Critique stay read-only unless the user asks for a
durable artifact.

If the repository already tracks `.claude/`, decide deliberately whether the
bundle belongs in version control. It is useful shared context on a team goal
and noise on a personal one. Do not commit it automatically.

## Living Goal and Plan

`UG new` writes both files from templates. Keep `goal.md` concise and
relatively stable:

```markdown
# Goal: <title>
Outcome and why it matters
Baseline
Scope and non-goals
Constraints and approval gates
Acceptance conditions
Primary verifier, supporting checks, and proof boundary
Anti-cheating and stopping rules
Completion and blocker evidence
Decisions and assumptions
```

Keep `plan.md` operational rather than narrative:

```markdown
# Plan: <title>
Current state, current phase, strongest next action

## Phase: <name>
Status: pending | in_progress | waiting | blocked | completed
Implementation tasks
Verification tasks
Evidence and artifact pointers
Attempts and task-local lessons when needed
Exit criteria
```

Include as many phases as the dependency structure needs and no more. Exactly
one phase is `in_progress` while work is executing. After completion or a
blocked stop, no phase remains in progress.

Acceptance conditions live in both places: prose in `goal.md`, and one
`UG accept` call each so `complete` can check them. Keep them in sync — the
machine copy is what gates completion.

`TodoWrite` is a good within-session view of the current phase's tasks. It is
not durable and does not survive a restart, so it never replaces `plan.md`.

## Maintain and Resume

Update the smallest relevant section after: user steering changes the contract
or a chosen assumption; material evidence changes confidence, scope, route, or
next action; a verifier fails or a hypothesis changes; a phase meets or fails
its exit criteria; an external wait times out or changes state; the goal
completes or is blocked.

Store conclusions, exact commands, small decisive outputs, causal lessons, and
artifact pointers. Retire invalidated assumptions instead of letting stale state
accumulate. Do not turn the plan into a transcript or paste large tool output —
`UG verify` already keeps full logs under `evidence/`.

On interruption or restart:

1. Run `UG status` and confirm the lifecycle state. (The session-resume hook has
   usually already injected this.)
2. Read `goal.md`, `plan.md`, and any project-owned status artifacts.
3. Refresh mutable reality: repository, tests, PR, CI, runtime, interaction
   surface, external systems relevant to the verifier.
4. Reconcile recorded state against live reality; classify work as completed,
   stale, invalidated, blocked, or still valid.
5. Restore exactly one in-progress phase, reapply recorded lessons, and take the
   smallest safe next action under the existing contract.
6. Return to Research or Plan only when new evidence changes a boundary.

Do not ask the user to reconstruct discoverable context. Ask only when
resumption exposes a new consequential decision, approval gate, or required
external action.

## Running Unattended

For genuinely hands-off runs, tell the user the three levers rather than
choosing invasively for them:

- **Permission mode.** `claude --permission-mode acceptEdits` removes edit
  prompts; `dontAsk` auto-denies anything not pre-approved, which pairs well
  with a tight `permissions.allow` list. `bypassPermissions` belongs only in a
  container or VM.
- **Fewer prompts.** `activate` already allows the engine's own commands. The
  bundled `/fewer-permission-prompts` skill can add the project's common
  read-only commands.
- **Scheduled continuation.** For a goal that spans hours, `/loop` re-enters on
  an interval or self-paced, and a scheduled task can fire `/ultragoal resume`.
  In cloud sessions, a routine can wake a fresh session that reads the bundle
  from the repository — which only works if the bundle is committed.

`--unattended` in the user's request means: never ask, record assumptions
instead, and reserve `await` for decisions that would be unsafe to make alone.
