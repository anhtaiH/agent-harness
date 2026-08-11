# Stage 2 — Paired Semantic A/B Results

**Suite:** 25 semantic golden fixtures × 3 repetitions × 2 variants = **150 runs, 75 paired cases**
**Control:** frozen v19 preview prompt · **Treatment:** `reviewing-pull-requests` v2.0.1
**Margins:** predeclared and frozen before inference (`PREDECLARATION.md`, sha256 `b1e8249d…`)

## Attrition

| Item | Count |
|---|---:|
| Planned runs | 150 |
| Completed runs | 150 |
| **Valid runs** | **150 (100 %)** |
| Invalid (timeout / refusal / API error / missing response / truncated) | **0** |
| Gradable pairs | 75 of 75 |
| Pairs with both judge verdicts | 75 |
| Permission denials across all runs | 0 |

Runs were balanced 75 / 75 per variant. Variant order within each pair was randomized by the
shipped runner. No run was replaced, retried, or substituted with stdout.

## Primary analysis — predeclared, this is the result of record

Effect is oriented so **positive = treatment better**. Non-inferiority is claimed only when the
lower bound of the 95 % paired bootstrap CI exceeds the negative margin.

| Metric | n | Control | Treatment | Effect | 95 % CI | Margin | Decision |
|---|---:|---:|---:|---:|---|---:|---|
| P0/P1 blocker recall | 51 | 0.980 | 0.941 | −0.039 | [−0.118, +0.039] | 0.05 | **not demonstrated** |
| False-blocker rate | 75 | 0.013 | 0.040 | −0.027 | [−0.080, +0.027] | 0.02 | **not demonstrated** |
| Merge-action accuracy | 75 | 0.907 | 0.907 | +0.000 | [−0.093, +0.093] | 0.05 | **not demonstrated** |
| Author-experience preference | 75 | 0.173 | 0.320 | +0.147 | [−0.013, +0.307] | 0.10 | non-inferior |
| Public-readability failure | 75 | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | 0.05 | non-inferior |
| Technical preference | 75 | 0.213 | 0.160 | −0.053 | [−0.187, +0.080] | 0.10 | not demonstrated |
| Useful P2/P3 retention | 75 | 0.467 | 0.413 | −0.053 | [−0.160, +0.053] | 0.05 | not demonstrated |
| Output-contract pass | 75 | 0.987 | 0.960 | −0.027 | [−0.080, +0.027] | 0.05 | not demonstrated |

Blocker recall is scored on the 51 pairs whose ground truth contains a blocking concern;
clean and abstention fixtures are excluded from that metric by definition and appear in
false-blocker instead.

### Acceptance gate: **FAILED**

Three of the four predeclared primary gates are not demonstrated. Under
`NONINFERIORITY_PROTOCOL.md` this is **not** a finding that v2.0.1 is worse — it is a finding
that non-inferiority **was not established**. No p-value in this table is offered as evidence
of equivalence; every one of the nonsignificant results above remains `not demonstrated`
precisely because significance is not the decision rule.

## Why each gate failed — power vs. genuine difference

Sample size needed for the CI lower bound to clear the margin, holding observed discordance
constant:

| Metric | Point estimate | Margin | Pairs needed | Diagnosis |
|---|---:|---:|---:|---|
| Merge-action accuracy | 0.000 | 0.05 | ~300 | **pure power** — exactly tied, CI merely too wide |
| P0/P1 blocker recall | −0.039 | 0.05 | ~2,450 | power, but the estimate sits close to the margin |
| False-blocker rate | −0.027 | 0.02 | **not achievable** | **genuine difference** — estimate already exceeds the margin |
| Useful P2/P3 retention | −0.053 | 0.05 | **not achievable** | **genuine difference** — estimate already exceeds the margin |

This distinction matters for what to do next. Merge-action accuracy would be settled by a
larger run. The false-blocker gate would not: more data cannot lift a bound whose point
estimate is already past the margin.

## Sensitivity analysis — post-hoc, exploratory, NOT the result of record

All three blocker-recall misses and all three output-contract failures came from a single
fixture, `golden-10-invalid-fixture`, reproducing 3/3 (see `RED_CASES.md`, RED-1). Excluding
that fixture is a **post-hoc cut made after seeing the data**. It is reported to localize the
failure, and it does not license any cut-over claim.

| Metric | n | Control | Treatment | Effect | 95 % CI | Decision |
|---|---:|---:|---:|---:|---|---|
| P0/P1 blocker recall | 48 | 0.979 | **1.000** | +0.021 | [+0.000, +0.062] | non-inferior |
| Merge-action accuracy | 72 | 0.903 | 0.944 | +0.042 | [−0.042, +0.125] | non-inferior |
| Output-contract pass | 72 | 0.986 | **1.000** | +0.014 | [+0.000, +0.042] | non-inferior |
| Author-experience preference | 72 | 0.139 | 0.333 | +0.194 | [+0.042, +0.347] | non-inferior (p = 0.024) |
| Public-readability failure | 72 | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | non-inferior |
| **False-blocker rate** | 72 | 0.014 | 0.042 | **−0.028** | [−0.083, +0.028] | **still not demonstrated** |
| Useful P2/P3 retention | 72 | 0.472 | 0.431 | −0.042 | [−0.153, +0.069] | still not demonstrated |
| Technical preference | 72 | 0.181 | 0.167 | −0.014 | [−0.153, +0.125] | still not demonstrated |

Read carefully, this says one localized abstention bug explains the entire recall and
output-contract deficit — and that **the false-blocker regression is not explained by it** and
survives as a separate, genuine finding (RED-2).

## Judge agreement and adjudication

| Item | Value |
|---|---|
| Pairs with both technical and author verdicts | 75 |
| Agreement between the two judges | 43 / 75 = **57.3 %** |
| Disagreements | 32 |
| Human adjudication performed | **none — unavailable in this environment** |

The two judges answer different questions (ground-truth correctness vs. author experience), so
disagreement is expected rather than alarming — and the direction of disagreement is itself a
result: the technical judge mildly prefers the control (16 vs 12, 47 ties) while the
author-experience judge clearly prefers the treatment (24 vs 13, 38 ties). All 32 disagreeing
pairs are preserved verbatim for later human adjudication.

**Ties were preserved throughout** and are reported in every count: 47 technical ties and 38
author ties were never redistributed to a winner.

## Cost and latency (secondary, reported not gating)

Medians per review, n = 75 per variant.

| Metric | Control | Treatment | Ratio |
|---|---:|---:|---:|
| Wall-clock latency | 42.9 s | 85.0 s | **1.98×** |
| Agent turns | 5 | 17 | **3.40×** |
| Cost per review | $0.312 | $0.450 | **1.44×** |
| Output tokens | 3,336 | 6,725 | 2.02× |
| Billable input tokens | 30,403 | 37,677 | 1.24× |
| Total suite cost | $24.72 | $34.08 | 1.38× |

Absolute latencies were measured under 5–10 concurrent runners and should not be read as
single-user timings. The **paired ratio** is the meaningful quantity: both variants of a pair
ran back-to-back under the same load, in randomized order.

The compact-tier cost gate in `START_HERE.md` is therefore **not met on the semantic suite**:
treatment costs 1.44× control per review. See the policy suite for the contrasting result.

## What did not regress

The measured v2.0.0 defect that motivated v2.0.1 **did not recur**. Across 150 live runs,
public-readability failure was **0.000 in both variants** — no reviewer/wave/coordinator/editor
/quality-gate narration leaked into any payload, and no false first-person verification claim
appeared. The output-boundary hardening holds under live conditions, not just against the
frozen 11-case fixture suite.
