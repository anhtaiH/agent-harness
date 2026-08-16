# Verification

Load this reference when an outcome depends on an interaction surface or live
capability, or when the available proof is weaker than the claim.

- [Verify the experienced outcome](#verify-the-experienced-outcome)
- [Proof surfaces in Claude Code](#proof-surfaces-in-claude-code)
- [Inventory relevant capabilities](#inventory-relevant-capabilities)
- [Record proof, do not assert it](#record-proof-do-not-assert-it)
- [Handle unavailable proof](#handle-unavailable-proof)

## Verify the Experienced Outcome

The primary verifier must observe the outcome at the closest actual surface on
which the user, operator, or dependent system experiences it.

Proof order:

1. **Direct surface** — the real browser, authenticated account, app, OS,
   device, integration, or runtime path in the relevant state and environment.
2. **Equivalent surface** — a different mechanism that observes the same
   behavior, permissions, state transitions, and failure modes with equal
   strength.
3. **Supporting check** — source inspection, static analysis, unit or component
   tests, snapshots, mocks, logs, synthetic probes. These narrow regressions but
   do not exercise the experienced outcome.
4. **Weaker proxy** — evidence that omits a relevant surface, authority
   boundary, environment, state transition, or failure mode.

Use direct proof when available. You may choose an equivalent surface
autonomously and record why it is equally strong. Supporting checks complement
direct proof; they never silently replace it. A weaker proxy changes the
acceptance boundary and needs an explicit contract decision when the difference
matters.

Match fidelity to the claim. A browser-visible change needs browser proof;
behavior that depends on a signed-in user's state needs the relevant
authenticated context; a desktop or OS interaction needs the app or OS surface;
role or permission behavior needs representative authority; a physical-device
claim needs the device or an explicitly accepted limitation. Do not claim more
than the observed environment proves.

## Proof Surfaces in Claude Code

| Surface | How to reach it | Good for |
| --- | --- | --- |
| Test suite, linters, type checks | `UG verify -- <command>` | regression floors, deterministic contracts |
| Running app | `/run`, or `/verify` for build-and-drive | the change actually working, not just compiling |
| Long builds, servers, training runs | `Bash` with `run_in_background`, then `Monitor` or `TaskOutput` | anything that outlives one tool call |
| Browser | Playwright with the preinstalled Chromium (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`); never run `playwright install` | rendered UI, auth flows, end-to-end paths |
| CI and PRs | GitHub MCP tools; `subscribe_pr_activity` to be woken by checks and reviews | proof that lands where the team sees it |
| External services | MCP servers and connectors already configured in the session | integration behavior under real credentials |
| Screenshots and artifacts | `SendUserFile`, or an `Artifact` for a report the user will share | human-checkable evidence of a visual outcome |

`/run` and `/verify` infer the launch from the project. If a project needs more
than a standard launch, `/run-skill-generator` records the real recipe once and
every later run follows it — worth doing inside a long goal whose verifier is
"the app works".

When a check is slow, run it in the background and keep working. `UG waiting
"CI on PR 214" --signal "subscribe_pr_activity"` releases the gate honestly
instead of wasting continuations on polling — but arm a real wake signal
first; on a local machine with no wake mechanism, prefer a background task
watched from within the turn.

## Inventory Relevant Capabilities

Before activation, inspect the live tool list and environment for only the
capabilities that could materially affect proof:

- terminal and local runtime, language toolchains, package managers;
- `/run` and `/verify` viability, or a recorded run skill;
- browser automation and its profile; the user's authenticated browser when a
  clean automation profile is insufficient;
- MCP servers, connectors, and which are actually authenticated;
- devices, simulators, and platform environments;
- account roles, permissions, and approval boundaries;
- credential availability, without reading or exposing secret values;
- representative test environments, fixtures, and data;
- network reach — cloud sessions run behind a proxy with a policy that may
  block hosts a verifier needs.

Record a compact capability note only when it affects the plan:

```text
Surface | required state or role | live capability | constraint | chosen verifier
```

Distinguish configured, available, authenticated, authorized, and actually
tested. Do not infer live capability from documentation or a tool name. Do not
probe credentials or take external actions beyond the user's authority merely
to complete the inventory.

## Record Proof, Do Not Assert It

Run every check that matters through the engine:

```bash
UG verify --primary --label "pytest -q" -- pytest -q
UG verify --label "typecheck" -- npm run typecheck
```

It executes the command, stores the real exit code, duration, an output hash,
and the full log under `evidence/`, and exits non-zero when the check fails. A
check you did not record does not exist as far as `UG complete` is concerned,
and `complete` refuses without a recorded passing run of the primary verifier.

For a check the engine cannot run — a screenshot, a manual readback, a
reviewer's confirmation — record the artifact and its meaning:

```bash
UG evidence "Checkout renders the new banner for a signed-in user" --ref evidence/checkout-signed-in.png
UG met A2 --evidence "evidence/checkout-signed-in.png"
```

For flaky or stateful checks, require clean-state reproduction and enough
consecutive passes to rule out luck; record each run rather than only the one
that passed.

## Handle Unavailable Proof

1. Try an equally strong available surface when it preserves the same observable
   behavior and authority boundary.
2. Treat a local setup failure as an execution failure: change the setup or
   packet before one retry, and preserve the evidence.
3. If access, authentication, hardware, permission, or an external action is
   required, continue independent work first. When it becomes the critical
   path: on a full-autonomy goal the user is away — record it as an external
   blocker with evidence (`UG block`), or `UG waiting` if a real wake signal
   exists; do not stop to ask. Only a supervised goal requests the smallest
   precise human action — `UG await "<exact action>"` plus an
   `AskUserQuestion` with the options.
4. If only weaker proof remains, return to Plan. Under full autonomy, choose
   the safe default yourself — wait for stronger proof, narrow the claim, or
   accept the limitation — and record it with `UG decide`, including the
   tradeoff. A supervised goal recommends instead, with the tradeoff and the
   safe default stated.
5. If the contract still requires the inaccessible surface, record the missing
   completion evidence and apply the blocker standard. Do not mark complete, and
   do not quietly reclassify assurance.

Never lower the verifier merely because the preferred capability is
unavailable. An equally strong verification surface is an implementation detail
you may choose autonomously; accepting weaker proof is a contract change. When
the user accepts weaker proof, update `goal.md`, the acceptance conditions, and
the reported limitation before continuing.

`UG complete --force` exists for exactly that case. It closes the goal while
recording every missing proof in the journal, so the gap stays visible. Use it
only when the user accepted the weaker proof — explicitly in conversation, or
ahead of time in the goal's contract. On a full-autonomy run, acceptance
cannot be solicited mid-run: if the contract does not already authorize the
weaker proof, the honest close is `UG block` with the evidence, never a
forced complete.
