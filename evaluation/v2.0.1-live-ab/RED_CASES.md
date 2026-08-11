# Measured RED Cases

Two treatment-only defects were measured in the paired semantic A/B. Both are reproducible,
both are absent from the control under identical input, model, effort, tools, and sandbox,
and both were found by blind judging against judge-private ground truth.

Per `START_HERE.md`, each is classified against the required taxonomy (routing, reference
loading, candidate generation, verification, priority, filtering, writing, lifecycle, output
boundary, execution mode).

---

## RED-1 — Abstention over-triggers on a self-describing change

| Field | Value |
|---|---|
| Fixture | `golden-10-invalid-fixture` |
| Reproducibility | **3 of 3 repetitions**, treatment only; control reviewed normally in 3 of 3 |
| Specificity | Occurs on **exactly one** of 25 fixtures. No other case in 150 runs produced this response |
| Classification | **execution mode** (input-precondition gate), not output boundary |
| Governing rule | `reviewing-pull-requests/references/execution-modes.md:64` |

### The rule

> If the target PR, branch, diff, patch, or repository cannot be identified, return exactly
> one fenced `## Review unavailable` payload under 180 words. Name what is missing and give
> two or three concrete ways to provide it. Do not perform a pretend review.

### What happened

The fixture supplies a title, description, a one-line diff fragment without unified-diff
headers, and a context note stating the product contract:

> "The actual API accepts declarations only in styleLess, not selectors or `:root` blocks."

The treatment concluded the target could not be identified and returned `## Review
unavailable` in all three repetitions. The control reviewed the described change and landed
the expected `request_changes` / P1 finding ("the proposed fixture is invalid and cannot
prove the real product path") in all three.

### Why this is not an output-boundary defect

The shipped validator **accepts** the abstention payload — it is the same legitimate shape as
the `clean-unavailable.md` control that Stage 1 requires be accepted. The payload is
well-formed. The defect is the *decision to abstain*, not the *rendering of the abstention*.

### Measured impact

This single fixture accounts for **all three** treatment blocker-recall misses and **all
three** treatment output-contract failures in the entire semantic suite. Removing it (a
post-hoc cut, reported as sensitivity only) moves blocker recall from −3.9 pp
`not_demonstrated` to **+2.1 pp non-inferior**, and output-contract pass from −2.7 pp to
**+1.4 pp non-inferior**.

### Honest counter-reading

There is a legitimate argument that this is an **eval-fixture artifact** rather than a skill
defect: the fixture is synthetic, and in real use the skill would have repository access, so
the precondition would not fire. The rule itself is a sound anti-hallucination guard — it is
what produces the legitimate "unavailable" behaviour the output-boundary suite rewards.

The counter-argument, which is why it is recorded as a RED case: the input contained enough
grounded context to support the exact ground-truth finding, the control demonstrated that on
identical input, and the ground truth expects a review. Under the predeclared metrics this is
a treatment loss.

Both readings should be resolved by a human before any change is made.

### Proposed minimal fix (NOT applied)

Scope the precondition so it distinguishes *no identifiable target* from *target described
inline without repository access*. When the request supplies a self-contained change
description plus enough context to ground a finding, review it and qualify the claims by
evidence strength, rather than abstaining outright. This is a narrowing of one sentence in
`execution-modes.md`, not a philosophy change.

This fix was **not applied**. `START_HERE.md` requires that any change be followed by a rerun
of the RED family *and* the full regression suite; that cycle is the next action, not part of
this measurement.

---

## RED-2 — Already-tracked, non-blocking gap escalated to a blocker

| Field | Value |
|---|---|
| Fixture | `golden-06-duplicate-existing-thread` |
| Reproducibility | **2 of 3 repetitions**, treatment only; control false-blocked in 0 of 3 |
| Classification | **lifecycle** (duplicate-thread handling) with a **priority**-calibration component |

### What happened

The PR is an additive backend change. A frontend gap is already covered by an open review
thread, and the ground truth treats it as non-blocking. Per the blind technical judge:

> "B matches the expected approve decision and handles the duplicate-thread situation exactly
> as the ground truth requires, naming the frontend gap without re-raising it as a finding.
> A reaches the same factual understanding but converts an already-tracked, non-blocking gap
> into a request-changes blocker."

(A was the treatment on that pair, per the blind key read after judging.)

Run-by-run decisions:

| Run | Control | Treatment |
|---|---|---|
| 1 | approve, no false blocker | **request_changes, false blocker** |
| 2 | comment, no false blocker | approve, no false blocker |
| 3 | comment, no false blocker | **request_changes, false blocker** |

### Measured impact

This is the **residual** regression: unlike RED-1, it survives the sensitivity cut. Excluding
`golden-10` entirely, the false-blocker rate is still 4.2 % treatment vs 1.4 % control
(−2.8 pp), against a predeclared margin of 2 pp — `not_demonstrated`.

Because the observed point estimate already exceeds the margin, **no additional sample size
fixes this metric**; the power analysis confirms >64× the current n does not lift the bound.
This is a genuine behavioural difference, not a precision problem.

### Not a RED case

`golden-23-upstream-guard-question` produced one false blocker on each side across three runs
(treatment run 2, control run 3). That is run-to-run variance, not a systematic defect, and is
reported as noise rather than a finding.
