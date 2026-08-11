# Paired Semantic A/B — frozen v19 control vs `reviewing-pull-requests` v2.0.1

**Executed:** 2026-08-11 · **Contract:** `START_HERE.md` (v2.0.1 handoff)
**Predeclaration frozen before inference:** sha256 `b1e8249d8ca87b76f04a9d583b930574d03d7b37bff66236119ea5a67261c21c`, 2026-08-11T06:55:27Z

---

## Headline

**The acceptance gate FAILS. v2.0.1 must not be cut over on this evidence.**

Three of the four predeclared primary gates were **not demonstrated** on Stage 2. That alone is a
finding that non-inferiority *was not established*, not that v2.0.1 is worse; no p-value in this
report is offered as evidence of equivalence.

**Stage 4 goes further.** On 100 real historical PRs judged against human maintainer comments, two
metrics are not merely undemonstrated but **measurably inferior** — their 95 % confidence intervals
exclude zero, so the direction holds without reference to any margin:

- **Human-comment recall** 0.442 → 0.337, CI [−0.198, −0.023]
- **Technical preference** 0.410 → 0.160, CI [−0.390, −0.110]

And v2.0.1's clearest Stage 2 win **reverses**: author-experience preference goes from +0.147 on
golden fixtures to **−0.070 on real PRs**.

| | Result |
|---|---|
| **Gate** | **FAILED** — 3 of 4 predeclared primary metrics not demonstrated (Stage 2) |
| **Real-PR evidence** | **2 metrics measurably inferior**, margin-free (Stage 4) |
| Runs executed | **500** paired runs across stages 2–4, plus the 11-case Stage 1 suite |
| Valid runs | **500 / 500 (100 %)** after Stage 4 recovery — zero timeouts, refusals, or missing responses |
| RED cases found | **3**, all treatment-only, all reproducible |
| Largest improvement | Output-contract conformance on the abstention path, **+28.0 pp** (p < 1e-6) |
| Cost | **1.44×** control on semantic review; **1.24×** on real PRs; **0.80×** on lightweight policy work |

The evaluation also produced one large, statistically secure improvement and a perfect
output-contract record on real PRs. Both belong in the same summary; reporting either side alone
would be misleading.

---

## What was run

| Stage | Content | Runs | Valid |
|---|---|---:|---:|
| 0 | Deterministic validation (pytest, both package validators, release validation) | — | 8/8 checks, 58/58 tests |
| 1 | Output-boundary RED suite, reproduced fresh | 11 | 8/8 leaks rejected, 3/3 controls accepted |
| 2 | 25 semantic golden fixtures × 3 reps × 2 variants | 150 | 150 (100 %) |
| 3 | 75 policy/routing cases × 1 rep × 2 variants | 150 | 150 (100 %) |
| 4 | 100 real historical PRs (SWE-PRBench) × 2 variants | 200 | 200 (100 %) after recovery — 51 lost to an account usage limit, all 51 re-run successfully; see `STAGE4_ATTRITION.md` |

Stages 2, 3, and 4 are reported **separately** and are never pooled. Policy/routing results are
never presented as defect detection.

**Stage 4 is supporting evidence, not gate-bearing.** The frozen predeclaration defines the gate
on the Stage 2 rubric; the PRBench rubric and its margins were written afterward. Non-inferiority
*decisions* in Stage 4 therefore carry no gate authority — but its two **margin-free** inferiority
findings (confidence intervals excluding zero) do not depend on any post-hoc margin and stand on
their own. Detail in `PRBENCH_RESULTS.md`.

## Environment gate — met, and measured

The one condition that would have forced a stop is runner isolation. It is **met**, and proven
by negative control rather than asserted. Full detail in `ENVIRONMENT_GATE.md`.

The shipped runner executes agents with `cwd=run_dir` but full inherited environment and **no OS
sandbox**, so sibling variant outputs and the answer-bearing eval set were reachable by absolute
path — exactly what `LIVE_AB_PROTOCOL.md` warns about when it says filesystem layout is not a
security boundary. A per-run mount namespace was built to close this:

- the run directory is bind-mounted at its **original absolute path**, so absolute paths in the
  generated prompt resolve identically inside and outside the sandbox — no prompt rewriting
- `tmpfs` erases `/srv/ab` (all other runs and the sibling variant), `/tmp/claude-0` (eval source,
  judge-private ground truth, blind mappings), `/home/user`, and `/root/.claude` from the namespace
- all capabilities are dropped (`CapEff: 0000000000000000`); `mount` returns permission denied

A canary probe confirmed sibling outputs, judge ground truth, the eval set, host repo, and host
skills are **absent** from the runner's filesystem view, not merely permission-denied.

Both variants ran with identical model (`claude-sonnet-5`), effort (`high`), tool surface,
permission mode, timeout, and sandbox. `--safe-mode` removed host CLAUDE.md, skills, hooks,
plugins, and MCP. **Zero permission denials across all 500 runs.**

### Declared limitations — not substituted

1. **No cross-family judge exists in this environment.** Only Anthropic models are callable. The
   technical judge is cross-*model* (`claude-opus-5` judging `claude-sonnet-5` runners), which
   controls for runner self-preference but not for shared model-family bias.
   `LIVE_AB_PROTOCOL.md` asks for a different model *family*; that requirement is **not met**.
2. **No human adjudication.** 32 semantic and 12 policy judge disagreements are reported
   **unadjudicated** and preserved verbatim for later human review.
3. **Per-tool call counts** are not exposed by the CLI result envelope; tool telemetry is limited
   to permission denials and per-model token usage.
4. **Stage 3's technical rubric was mis-specified** for its own suite (see `POLICY_RESULTS.md`).
5. **Stage 4's margins were not predeclared.** The frozen predeclaration covers the Stage 2
   rubric only. Stage 4's non-inferiority decisions are reported without gate authority; its
   margin-free inferiority findings are unaffected. See `PRBENCH_RESULTS.md`.
6. **Stage 4 ran one repetition per case**, not three. The paired design still controls for case
   difficulty, but per-case run-to-run variance is not estimated.
7. **A defect in the shipped evaluation harness** silently dropped judge ground truth for case
   IDs containing non-alphanumeric characters, affecting 2 of 100 real PRs. Found, diagnosed,
   and repaired without modifying the canonical package; both cases are in the reported 100.
   Full mechanism and recommended upstream fixes in `PRBENCH_RESULTS.md`.

---

## Stage 2 — semantic A/B (the result of record)

Full tables in `SEMANTIC_RESULTS.md`.

| Metric | Control | Treatment | Effect | 95 % CI | Margin | Decision |
|---|---:|---:|---:|---|---:|---|
| P0/P1 blocker recall | 0.980 | 0.941 | −0.039 | [−0.118, +0.039] | 0.05 | **not demonstrated** |
| False-blocker rate | 0.013 | 0.040 | −0.027 | [−0.080, +0.027] | 0.02 | **not demonstrated** |
| Merge-action accuracy | 0.907 | 0.907 | +0.000 | [−0.093, +0.093] | 0.05 | **not demonstrated** |
| Author-experience preference | 0.173 | 0.320 | +0.147 | [−0.013, +0.307] | 0.10 | non-inferior |
| Public-readability failure | 0.000 | 0.000 | +0.000 | [+0.000, +0.000] | 0.05 | non-inferior |

Ties were preserved throughout: 47 technical ties and 38 author ties, never redistributed.

### Power vs. genuine difference

Two of the three failures are **not** fixable with more data:

| Metric | Point estimate | Margin | Pairs needed | Diagnosis |
|---|---:|---:|---:|---|
| Merge-action accuracy | 0.000 | 0.05 | ~300 | pure power — exactly tied |
| P0/P1 blocker recall | −0.039 | 0.05 | ~2,450 | power, estimate near margin |
| False-blocker rate | −0.027 | 0.02 | **unachievable** | genuine — estimate already past margin |
| Useful P2/P3 retention | −0.053 | 0.05 | **unachievable** | genuine — estimate already past margin |

## Stage 4 — 100 real historical PRs

Full tables in `PRBENCH_RESULTS.md`. Ground truth is the human maintainer review comments from
the original PR threads. Concealment was verified at two independent layers before inference:
identifiers stripped from runner-visible input, and the agent proxy returning 403 for every
repository in the corpus (control fetch to `example.com` returned 200).

| Metric | n | Control | Treatment | Effect | 95 % CI | Decision |
|---|---:|---:|---:|---:|---|---|
| Human-comment recall | 86 | 0.442 | 0.337 | **−0.105** | **[−0.198, −0.023]** | **inferior** |
| Technical preference | 100 | 0.410 | 0.160 | **−0.250** | **[−0.390, −0.110]** | **inferior** |
| Any fabricated finding | 100 | 0.070 | 0.110 | −0.040 | [−0.120, +0.040] | not demonstrated |
| Author-experience preference | 100 | 0.350 | 0.280 | −0.070 | [−0.220, +0.080] | not demonstrated |
| Public-readability failure | 100 | 0.020 | 0.000 | +0.020 | [+0.000, +0.050] | non-inferior |
| Output-contract pass | 100 | 0.970 | **1.000** | +0.030 | [+0.000, +0.070] | non-inferior |

Ties preserved: 43 technical, 37 author.

**Why the first two rows say "inferior" and not "not demonstrated."** Both confidence intervals
exclude zero, so the direction is established without reference to the post-hoc margin. Discordant
pairs: recall **12 control-only vs 3 treatment-only**; technical preference **41 vs 16**. Under a
Bonferroni correction for the six metrics (α = 0.0083) technical preference survives (p = 0.0013)
and recall does not (p = 0.035) — recall is reported as directional with that caveat, supported by
its agreement with the independent Stage 2 recall deficit.

**Treatment says less.** 47 → 37 confirmed findings and 307 → 239 plausible ones: 22 % fewer
findings per review. Fabrication is statistically indistinguishable (7 % vs 11 %, p = 0.48), so
this is filtering, not invention — and on this corpus the filtering costs more true findings than
it saves false ones. That reproduces Stage 2's useful-P2/P3 retention deficit on an independent,
real-world corpus.

**The author-experience win does not reproduce.** +0.147 on golden fixtures becomes **−0.070 on
real PRs**. Neither estimate is individually significant and the intervals overlap, so this is not
proof the Stage 2 result was an artifact — but it removes the basis for claiming an
author-experience improvement in general. Golden fixtures are authored alongside the skill; real
PRs are not.

Judge agreement was **57 %** (43 disagreements), reported unadjudicated and preserved verbatim.

## The three RED cases

Full detail, evidence, and proposed minimal fixes in `RED_CASES.md`. Raw payloads in
`results/red-case-outputs/`.

| # | Defect | Fixture | Reproducibility | Classification |
|---|---|---|---|---|
| **RED-1** | Abstains entirely on a self-describing change the control reviews correctly | `golden-10-invalid-fixture` | **3/3**, treatment only | **execution mode** |
| **RED-2** | Escalates an already-tracked, non-blocking gap into a request-changes blocker | `golden-06-duplicate-existing-thread` | **2/3**, treatment only | **lifecycle** + priority |
| **RED-3** | Leaks internal first-wave mission vocabulary into an abstention payload | `066-01-large_cohesive_module` | 1/75 treatment, 0/75 control | **output boundary** |

**RED-1 explains the entire recall deficit.** A post-hoc sensitivity cut excluding that one
fixture (exploratory, *not* the result of record) moves blocker recall to **+2.1 pp non-inferior**,
merge-action accuracy to **+4.2 pp non-inferior**, and output-contract pass to **+1.4 pp
non-inferior**.

**RED-2 survives that cut.** False-blocker rate remains 4.2 % vs 1.4 % (−2.8 pp) against a 2 pp
margin. This is the genuine residual regression, and no sample size fixes it.

**RED-3 is a coverage gap in the frozen suite.** The 11-case output-boundary fixtures contain no
abstention payload carrying mission-name vocabulary, so nothing rejects this class
deterministically. It was found only by live sampling.

No change was made to the canonical skill. `START_HERE.md` requires that any fix be followed by a
rerun of the RED family *and* the full regression suite; that cycle is the next action, not part
of this measurement.

## What improved

- **Output-contract conformance.** Measured with the package's own validator: semantic suite
  98.7 % → **100.0 %**; real PRs 97.0 % → **100.0 %**; policy abstention path **0.0 % → 28.0 %**
  (+28.0 pp, CI [+18.7, +38.7], p < 1e-6). The frozen v19 control never produced a conforming
  abstention payload in 75 attempts. This is the one improvement that holds across every suite.
- **Author experience on golden fixtures.** +14.7 pp overall, +19.4 pp excluding RED-1
  (p = 0.024). **This does not generalize** — the same metric is −7.0 pp on 100 real PRs. The
  improvement should be described as fixture-specific until a real-PR measurement supports it.
- **The v2.0.0 narration regression did not recur on the review path.** Across 150 semantic runs,
  public-readability failure was 0.000 in both variants. The hardening holds under live
  conditions, not only against the frozen fixtures. RED-3 is on the abstention path, not the
  review path.

## Cost — workload-dependent, no single verdict

| Suite | Latency | Turns | Cost/review | Billable input |
|---|---:|---:|---:|---:|
| Semantic (golden fixtures) | 1.98× | 3.40× | **1.44×** | 1.24× |
| **Real PRs (SWE-PRBench)** | 1.23× | 2.26× | **1.24×** | 1.14× |
| Policy / routing | 1.77× | 1.80× | **0.80×** | **0.63×** |

On semantic review work v2.0.1 costs 44 % more; on real PRs, 24 % more ($95.48 vs $77.18 for the
stage). On lightweight policy work it is 20 % **cheaper**, with 37 % fewer billable input tokens —
progressive disclosure behaving as designed. The compact-tier cost gate is **not met** on either
review suite.

The real-PR figure is the one to plan against, and it is the least favourable reading of the
trade: 24 % more cost and 2.26× the turns while producing 22 % fewer findings and recalling fewer
of the maintainer's actual concerns.

Absolute latencies were measured under 5–10 concurrent runners; the paired ratio is the meaningful
quantity, since both variants of a pair ran back-to-back under the same load in randomized order.


## Acceptance gate, item by item

Decided on Stage 2, where the margins were genuinely predeclared. The Stage 4 column is
corroborating evidence, not a second gate.

| Gate condition | Status (Stage 2) | Stage 4 corroboration |
|---|---|---|
| P0/P1 recall lower bound above margin | **FAIL** (−0.118 vs −0.05) | worse — human-comment recall **inferior**, CI excludes zero |
| False-blocker rate non-inferior | **FAIL** (−0.080 vs −0.02) | fabrication not significantly different (p = 0.48) |
| Merge-action accuracy non-inferior | **FAIL** (−0.093 vs −0.05) — power-limited | not measured on this rubric |
| Public readability at least equal | **PASS** (0.000 both) | **PASS** (0.000 vs 0.020) |
| Author-experience preference at least neutral | **PASS** (+0.147, LB −0.013) | **reverses** to −0.070 |
| No permissions / duplicate-post / lifecycle regression | **FAIL** — RED-2 is a lifecycle regression | — |
| Compact-tier cost within budget | **FAIL** on semantic (1.44×); PASS on policy (0.80×) | **FAIL** on real PRs (1.24×) |

Stage 4 does not rescue a single failing gate condition, and it turns the one clear pass
(author experience) into a wash.

## Recommended next actions, in order

1. **Investigate the recall and finding-volume deficit as one problem.** Stage 4 shows treatment
   raising 22 % fewer findings, confirming 21 % fewer against human comments, and losing
   discordant recall pairs 12-to-3. Stage 2 showed the same shape in useful-P2/P3 retention. The
   most probable single cause is over-aggressive filtering or verification gating, not a
   candidate-generation failure — treatment's findings are diff-supported when it makes them
   (fabrication is flat). Classify per `START_HERE.md` before changing anything.
2. **Human-adjudicate RED-1.** Decide whether the abstention on a self-describing change is a
   skill defect or an eval-fixture artifact. Both readings are argued in `RED_CASES.md`.
3. **Fix RED-2.** The genuine residual regression, and the only Stage 2 primary-metric failure
   that more data cannot resolve.
4. **Close the RED-3 coverage gap** by adding an abstention fixture with mission-name vocabulary
   to the 11-case output-boundary suite, so the class is caught deterministically.
5. **Re-run the RED family, then the full regression suite**, per `START_HERE.md`.
6. **Re-run Stage 2 at ~300 pairs** to settle merge-action accuracy, which is power-limited
   rather than genuinely different.
7. **Predeclare a Stage 4 rubric and margins before the next real-PR run**, then repeat at ≥3
   repetitions per case so this stage can carry gate authority instead of only corroborating.
8. **Fix the harness ID-slugging defect** (`PRBENCH_RESULTS.md`) before the next real-world
   corpus run, along with the unchecked judge exit code and the per-role report overwrite.
9. Obtain a **cross-family judge** and **human adjudication** before any release-grade claim.

## Reproducibility

Everything needed to re-run is committed under `evaluation/v2.0.1-live-ab/`:

- `harness/` — sandbox, runner, judges, assembler, analyzer drivers
- `PREDECLARATION.md` + `predeclaration.sha256` — frozen before inference
- `ENVIRONMENT_GATE.md` — inventory, isolation design, negative-control results
- `SEMANTIC_RESULTS.md`, `POLICY_RESULTS.md`, `PRBENCH_RESULTS.md`, `RED_CASES.md`,
  `STAGE4_ATTRITION.md` — per-stage detail
- `results/` — paired CSVs, per-metric analyses, sensitivity analyses, telemetry, blind keys,
  RED-case raw payloads, run manifests

The canonical v2.0.1 package was **not modified**.
