# Specification and Control Loop

Load this reference when the intended outcome or verifier is ambiguous, the goal
is risky or genuinely long-running, clarification is required, or execution has
stopped making progress. Keep routine Light goals on the core workflow.

- [Specification readiness](#specification-readiness)
- [Acceptance audit](#acceptance-audit)
- [Clarification frontier](#clarification-frontier)
- [Adaptive control loop](#adaptive-researchoptionsplanexecutereview)
- [Anti-spin control](#anti-spin-control)
- [Run-local learning and recovery](#run-local-learning-and-recovery)

## Specification Readiness

You draft this contract from the prompt and discovered evidence. The user
supplies intent and consequential preferences; the user is not responsible for
writing a correct specification.

| Field | Readiness question |
| --- | --- |
| Outcome | What externally observable state must exist? |
| Why and audience | Whose problem is solved, and why does it matter? |
| Target | Where must the result land or operate? |
| Baseline | What is true or failing now? |
| Scope | What surfaces may change, and what is explicitly out? |
| Constraints | What compatibility, safety, quality, time, or policy floor applies? |
| Acceptance | What independently observable conditions imply the outcome? |
| Verifier | What strongest check can fail, and what supporting checks prevent regressions? |
| Authority | Which writes are already authorized, and which need separate approval? |
| Control | When should the loop complete, re-plan, ask, wait, or stop? |

Classify the draft:

- **Ready** — one coherent outcome, credible verifier, no unresolved high-impact decision.
- **Ready with assumptions** — only reversible low-risk ambiguity remains; record the assumptions in `goal.md`.
- **Needs decisions** — an irreducible choice changes outcome, scope, permissions, risk, cost, or proof. Do not activate.
- **Not goal fit** — success is taste-only, one-shot, unbounded, or lacks a credible verifier. Recommend an ordinary task or a Design packet.

Plan mode pairs naturally with this gate. `EnterPlanMode` keeps you read-only
while you ground the contract; `ExitPlanMode` is the user's approval of the
approach, after which activation and mutation begin. Use it when the plan itself
is the risky part; skip it for a clear routine goal.

## Acceptance Audit

Before activation, challenge your own draft:

1. **Outcome** — could every criterion pass while the user's real need remains unmet?
2. **Baseline** — is the starting state observed rather than assumed?
3. **Independence** — can the verifier detect a bad implementation, or does it merely echo your claim?
4. **Coverage** — are primary behavior, regressions, safety, and required destinations covered proportionately?
5. **Anti-cheating** — could success be manufactured by weakening tests, narrowing data, hiding errors, changing a benchmark, or using an unapproved mock?
6. **Repeatability** — do flaky or stateful checks need a clean run or consecutive passes?
7. **Authority** — are external, public, irreversible, shared, or costly actions separately gated?
8. **Stopping** — are completion, decision-review, waiting, and blocker conditions distinguishable?

Rewrite weak criteria yourself. Ask the user only when the rewrite would choose
a consequential preference for them.

## Clarification Frontier

Borrow the useful part of a design interview without turning activation into an
interrogation:

1. Resolve discoverable facts first — never ask for something a tool can find.
2. Ask only decisions whose prerequisites are already known.
3. Ask at most **three** highest-impact questions before activation, in one
   `AskUserQuestion` call.
4. After those answers, proceed under explicit safe assumptions or declare the
   goal not ready. Do not continue an open-ended interview.
5. Prefer a safe recommended assumption when the choice is reversible and low
   risk.

`AskUserQuestion` carries the structure directly: put the recommended option
first and mark it `(Recommended)`, give each option a `description` that states
the tradeoff, and use `multiSelect` only when the choices genuinely combine.
Two to four real options; do not manufacture choices for a routine
implementation detail.

If the question arrives while a goal is already active, run `UG await
"<decision>"` first so the gate releases while the user thinks, then `UG resume`
with the answer recorded in `goal.md`.

Under `--unattended`, do not ask at all: record the recommended assumption, note
it as a decision in `goal.md`, and reserve `await` for a choice that would be
unsafe to make alone.

## Adaptive Research–Options–Plan–Execute–Review

| Phase | Work allowed | Exit evidence |
| --- | --- | --- |
| Research | Inspect canonical sources, baseline, constraints, failures, unknowns; avoid mutation. | Facts suffice to draft the contract and expose remaining decisions. |
| Options | Compare materially different approaches; recommend the least complex likely to pass. | One approach selected, or no meaningful tradeoff exists. |
| Plan | Finalize acceptance, verifier, bounded steps, ownership, approvals, write scope. | Specification is ready; in Activate mode, `UG activate` succeeds. |
| Execute | Make scoped changes, run checks, record deviations and evidence. | Proof passes, new evidence forces re-planning, or a human gate is reached. |
| Review | Compare actual outcome to intent, run independent proof, inspect regressions and authorized deviations. | Complete with evidence, return to Execute, return to Research/Plan, or enter decision review. |

Mirror the phase into state with `UG phase "<name>" --status in_progress --next
"<action>"` so the stop gate and any resumed session know where you are. A local
implementation detail may change without asking while it stays inside the
outcome, scope, risk, and approval contract; changing those boundaries returns
to Plan.

## Anti-Spin Control

Count progress only when an iteration produces at least one of: new evidence,
reduced uncertainty, an improved artifact, a changed hypothesis, or measurable
verifier movement. The engine counts the same way — three consecutive
continuations with no recorded progress auto-pause the goal — so recording
progress is not bookkeeping, it is what keeps the goal alive.

Maintain the attempt ledger for non-trivial failures:

```bash
UG attempt --failure hypothesis \
  --hypothesis "the retry wrapper swallows the 429" \
  --action "logged the raw response before the wrapper" \
  --result "429 body is empty; the real failure is a 401 upstream" \
  --lesson "check auth before rate limiting on this client"
```

Apply this ladder:

1. Classify the failure: mechanical/setup, hypothesis/implementation,
   specification, approval, or external state.
2. Retry an identical mechanical action once only after changing its setup,
   inputs, or worker packet.
3. After two consecutive verifier failures without measurable progress — or the
   third failure within one approach despite marginal progress — abandon that
   approach, return to Research and Plan, and change the hypothesis. Escalate
   one model or effort rung only when the evidence shows a reasoning gap.
4. After three distinct evidence-backed approaches fail, pause before a fourth
   for a decision review: what was tried, strongest evidence, remaining
   uncertainty, recommendation, meaningful options. Execute the recommendation
   autonomously when it stays inside the existing scope, risk, proof, and
   approval contract; ask only when the next choice changes one of those.
5. Do not create more peers because an attempt failed. Delegate only a newly
   separable evidence or implementation lane.
6. For waits, name the expected state change and a useful timeout. Do not repeat
   identical reads as progress: start the work in the background and watch it
   with `Monitor`, then `UG waiting "<what>" --signal "<how you get woken>"`. At
   timeout, preserve the observation and reclassify the wait as a new
   hypothesis, an external action, or a blocker candidate.

A decision review is not automatically a blocked goal. Keep the goal active
unless the blocker standard is actually met; preserve the smallest next action
and the evidence either way.

## Run-Local Learning and Recovery

Treat learning as adaptation within the active task, preserved where later
phases and resumed sessions can use it.

After material evidence, especially a non-trivial success, failure, or recovery:

1. Observe the verifier outcome and classify any failure before acting.
2. Update the causal hypothesis from evidence rather than restating the symptom.
3. Change the smallest appropriate layer: setup or tool use, worker packet,
   implementation, plan, or specification.
4. Re-run the strongest relevant verifier and record its delta.
5. Distill one concise lesson — `UG lesson "<what became known and what to do
   differently>"` — covering what to reuse or retire and where it affects
   remaining work.
6. Apply it to later phases, delegated packets, recovery steps, and resumption;
   remove invalidated assumptions and tasks from the plan.

You may autonomously improve methods, sequencing, setup, model or effort rung,
and bounded delegation while staying inside the contract. Learning never
authorizes weakening the outcome, acceptance conditions, proof boundary,
anti-cheating rules, approval gates, or completion standard. A lesson that
changes one of those boundaries returns to Plan and gets the same treatment as
any other contract change.

This is task-local learning. Do not edit this skill, `CLAUDE.md`, or user
memory from inside a goal run. Promote a lesson outside the active goal only
when the user separately asks or an established project workflow owns that
promotion.
