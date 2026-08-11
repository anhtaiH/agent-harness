# Predeclared Metrics and Non-Inferiority Margins

**Frozen:** before any experimental inference run.
**Experiment:** paired semantic A/B, frozen v19 control (`old_prompt`) vs `reviewing-pull-requests` v2.0.1 (`new_skill`).
**Protocol source:** `evaluation/LIVE_AB_PROTOCOL.md`, `evaluation/NONINFERIORITY_PROTOCOL.md`.

## Unit of analysis

The paired unit is `(case_id, repetition)`. Both variants of a pair run on identical
sanitized input, identical model, effort, tool surface, permission mode, timeout, and
sandbox. Variant execution order within each pair is randomized by the runner.

A pair is **gradable** only when both variants produced a valid run. Validity is defined by
`LIVE_AB_PROTOCOL.md`: successful process exit, no timeout, an explicit non-empty
`outputs/response.md`, not an API/runtime error envelope, not a refusal. Invalid runs are
reported in attrition and are never replaced by stdout.

Sensitivity analysis (secondary): per-case aggregation across repetitions by majority vote.

## Primary metrics and margins

Non-inferiority is claimed for a metric **only if** the lower bound of the 95% paired
bootstrap confidence interval on the treatment-minus-control effect (oriented so that
positive = treatment better) is strictly greater than the negative margin.

| # | Metric | Direction | Margin δ | Gate |
|---|---|---|---|---|
| 1 | P0/P1 blocker recall | higher better | 5 pp | must be non-inferior |
| 2 | False-blocker rate | lower better | 2 pp | must be non-inferior |
| 3 | Merge-action (decision) accuracy | higher better | 5 pp | must be non-inferior |
| 4 | Author-experience preference | higher better | 10 pp net preference | must be at least neutral |

Margins 1–3 are the values recommended in `NONINFERIORITY_PROTOCOL.md`. Margin 4 is set at
10 pp on net preference because a paired preference judgment is noisier than a binary
correctness judgment; "no material loss" is operationalized as a net-preference lower bound
above −10 pp.

## Secondary metrics (reported, not gating)

| Metric | Direction | Margin |
|---|---|---|
| Public-readability failure rate | lower better | 5 pp |
| Useful P2/P3 retention | higher better | reported only |
| Lifecycle convergence | higher better | reported only |
| Output-contract mechanical pass rate | higher better | reported only |
| Duration per review (wall ms) | lower better | reported only, per tier |
| Total tokens and USD cost per review | lower better | reported only, per tier |

## Metric definitions

- **P0/P1 blocker recall** — the review surfaces the case's ground-truth blocking concern
  (or, for clean/abstention fixtures, correctly declines to raise one) at priority P0 or P1.
  Scored 1/0 per pair-member by the blind technical judge against judge-private ground truth.
- **False-blocker rate** — the review raises a P0/P1 blocking finding that is not supported
  by the ground truth for that case. Scored 1/0 (1 = a false blocker occurred).
- **Merge-action accuracy** — the review's proposed submission type matches the
  ground-truth decision (`approve` / `request_changes` / `comment`).
- **Author-experience preference** — a separate judge that sees only the two final payloads
  (no ground truth, no case metadata) picks A, B, or tie. Ties are preserved and counted.
- **Public-readability failure** — the payload leaks orchestration narration, invalid
  priority labels, or false first-person verification claims, per the shipped mechanical
  grader in `grade_live_ab.py` and `validate_review_output.py`.

## Analysis rules

1. Ties are preserved and reported; they are never redistributed to a winner.
2. Invalid, refused, timed-out, quota-limited, API-errored and truncated runs are reported
   as attrition and excluded from gradable pairs.
3. Semantic review, policy/routing, abstention, and output-contract results are reported in
   separate tables. Policy/routing results are never reported as defect-detection wins.
4. A nonsignificant exact sign/McNemar p-value is **never** reported as evidence of
   non-inferiority. The decision rule is the confidence bound above, and only that.
5. The blind A/B key is written only after judging completes, and is stored outside every
   runner workspace.
6. If the acceptance gate fails, the failure is classified as routing, reference loading,
   candidate generation, verification, priority, filtering, writing, lifecycle, output
   boundary, or execution mode, per `START_HERE.md`.

## Acceptance gate (from START_HERE.md)

Cut over only when **all** hold:

- P0/P1 recall lower confidence bound above the predefined margin
- false-blocker rate non-inferior
- merge-action accuracy non-inferior
- public readability at least equal
- author-experience preference at least neutral
- no permissions, duplicate-post, or lifecycle regression
- compact-tier cost within the agreed budget

## Declared deviations from the ideal protocol

These are deviations forced by the environment, declared before inference, and repeated in
the final report. They are not silent substitutions.

1. **The technical judge is cross-model, not cross-family.** Only Anthropic models are
   callable in this environment. The technical judge runs on a different model
   (`claude-opus-5`) than the runners (`claude-sonnet-5`), which controls for
   runner-model self-preference but not for model-family shared bias.
2. **No human adjudication.** No human reviewer is available in this session. Judge
   disagreements are recorded and reported as an unadjudicated disagreement rate rather
   than resolved. Every disagreeing pair is preserved for later human adjudication.
