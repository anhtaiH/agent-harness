# Stage 3 — Policy / Routing Suite (reported separately)

**These are instruction-following and output-contract results. They are NOT defect-detection
results and must never be reported as improved bug finding.** The suite is flagged
`eligible_for_semantic_headlines: false` in the package, and that flag is honoured here.

**Suite:** 75 policy/routing cases × 1 repetition × 2 variants = **150 runs, 75 paired cases**

## Attrition

| Item | Count |
|---|---:|
| Planned runs | 150 |
| Completed runs | 150 |
| **Valid runs** | **150 (100 %)** |
| Invalid runs | **0** |
| Gradable pairs | 75 of 75 |
| Permission denials | 0 |

## A harness finding that limits this stage

The 75 policy cases carry `"files": []` — they supply **no PR content at all**, only an abstract
prompt such as *"Review this pull request and show me a preview. It is a docs typo change in
Markdown."*

Run live through `run_live_ab.py`, both variants therefore do the correct thing: they decline
and ask for the PR, branch, or diff. Neither can classify a review tier, activate a specialist,
or reach a merge decision, because there is nothing to review.

Consequence: the technical rubric — built for the concrete semantic fixtures — scored
0 on every correctness field for both variants and returned **tie on 75 of 75 pairs**.

**That all-tie result is uninformative, not evidence of equivalence.** It measures a rubric
mismatch, not agent behaviour. Reporting it as "policy parity" would be exactly the error the
protocol warns against.

The routing, tier, specialist-activation, and lifecycle behaviour these cases were written for
is exercised by the package's deterministic path (`simulate_routing.py`, 680 scenarios), which
**passed in full during Stage 0**. Live agent runs against empty inputs are the wrong
instrument for that question.

## What this stage *did* measure validly

With no PR content, every payload is an abstention. That makes this suite an unintentionally
good test of the **unavailable-input output contract** — and there the shipped validator gives
a clear, paired answer.

### Output-contract conformance, shipped validator

| Suite | n | Control pass | Treatment pass | Effect | 95 % CI | Decision |
|---|---:|---:|---:|---:|---|---|
| Policy (abstention path) | 75 | **0.000** | **0.280** | **+0.280** | [+0.187, +0.387] | **non-inferior**, p < 1e-6 |
| Semantic (for comparison) | 75 | 0.987 | **1.000** | +0.013 | [+0.000, +0.040] | non-inferior |

The frozen v19 control produced a conforming preview payload in **0 of 75** abstention cases.
v2.0.1 produced one in 21 of 75. This is the single largest and most statistically secure
improvement measured anywhere in this evaluation.

It is also an honest half-result: **72 % of v2.0.1's abstention payloads still fail the
package's own validator**, almost always by emitting prose outside the required single
`~~~markdown` fence. The `## Review unavailable` contract is specified in
`references/execution-modes.md` but is not reliably produced under live conditions.

### Author-experience preference

| Metric | n | Control | Treatment | Effect | 95 % CI | Margin | Decision |
|---|---:|---:|---:|---:|---|---:|---|
| Author preference | 75 | 0.120 | 0.040 | −0.080 | [−0.173, +0.000] | 0.10 | not demonstrated |

Ties: 63 of 75. The author judge mildly prefers the control's abstention wording. This is the
opposite of the semantic suite, where the treatment was clearly preferred (+19.4 pp). A
plausible reading is that v2.0.1's abstention text is longer and more procedural, which reads
worse when there is no review to justify it — but this is interpretation, not measurement.

### Judge agreement

| Item | Value |
|---|---|
| Pairs with both verdicts | 75 |
| Agreement | 63 / 75 = 84.0 % |
| Disagreements | 12 (unadjudicated — no human available) |

## RED-3 — Orchestration vocabulary leaks into an abstention payload

One treatment payload (`066-01-large_cohesive_module-initial_preview`, run 1) failed the
process-narration check that the control passed. The payload tells the author:

> "Once I have the actual code change, I'll build the context packet, run the review, and
> return a preview … covering **intent/behavior, contracts/safety, proof/operations, and
> structure/history** for the module."

That is the skill's internal four-mission first-wave vocabulary plus the internal "context
packet" artifact, surfaced to the author. It is the same defect *class* that v2.0.1 was built
to eliminate, appearing on a path the 11-case output-boundary suite does not cover: the
frozen suite's `clean-unavailable.md` control does not contain mission-name vocabulary, so
nothing in the deterministic gate rejects this.

| Field | Value |
|---|---|
| Frequency | 1 of 75 treatment payloads (1.3 %); control 0 of 75 |
| Classification | **output boundary**, on the unavailable/abstention path |
| Caught by shipped validator? | Yes — but only via the outer-fence rule, not the narration rule |
| Caught by the 11-case RED suite? | **No** — coverage gap |

**Suggested coverage addition (not applied):** extend the output-boundary fixtures with an
abstention payload that names first-wave missions and internal artifacts, so this class is
rejected deterministically rather than discovered by live sampling.

## Cost and latency — the contrasting result

Medians per case, n = 75 per variant.

| Metric | Control | Treatment | Ratio |
|---|---:|---:|---:|
| Wall-clock latency | 18.6 s | 33.1 s | 1.77× |
| Agent turns | 5 | 9 | 1.80× |
| **Cost per case** | **$0.253** | **$0.203** | **0.80×** |
| **Billable input tokens** | **27,618** | **17,307** | **0.63×** |
| Total suite cost | $18.75 | $16.30 | 0.87× |

On this lightweight workload v2.0.1 is **cheaper** than the frozen control — 0.80× cost and
0.63× billable input tokens — which is progressive disclosure behaving as designed: the skill
does not load reference material it does not need. That is the opposite of the semantic suite,
where the treatment cost 1.44× more because it genuinely did more work (17 turns vs 5).

The compact-tier cost picture is therefore workload-dependent, and a single cost verdict for
v2.0.1 would be misleading in either direction.
