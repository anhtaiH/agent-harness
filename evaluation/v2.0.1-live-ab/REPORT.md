# Paired Semantic A/B — frozen v19 control vs `reviewing-pull-requests` v2.0.1

**Executed:** 2026-08-11 · **Contract:** `START_HERE.md` (v2.0.1 handoff)
**Predeclaration frozen before inference:** sha256 `b1e8249d8ca87b76f04a9d583b930574d03d7b37bff66236119ea5a67261c21c`, 2026-08-11T06:55:27Z

---

## Headline

**The acceptance gate FAILS. v2.0.1 must not be cut over on this evidence.**

Three of the four predeclared primary gates were **not demonstrated**. This is a finding that
non-inferiority *was not established* — it is explicitly **not** a finding that v2.0.1 is worse
overall, and no p-value in this report is offered as evidence of equivalence.

The evaluation also produced three measured, reproducible RED cases and one large, statistically
secure improvement. Both belong in the same summary; reporting either alone would be misleading.

| | Result |
|---|---|
| **Gate** | **FAILED** — 3 of 4 primary metrics not demonstrated |
| Runs executed | **500** across four stages |
| Valid runs (stages 1–3) | **450 / 450 (100 %)** — zero timeouts, refusals, API errors, or missing responses |
| Stage 4 | hit an account usage limit mid-stage; see `STAGE4_ATTRITION.md` |
| RED cases found | **3**, all treatment-only, all reproducible |
| Largest improvement | Output-contract conformance on the abstention path, **+28.0 pp** (p < 1e-6) |
| Cost | **1.44× control** on semantic review; **0.80× control** on lightweight policy work |

---

## What was run

| Stage | Content | Runs | Valid |
|---|---|---:|---:|
| 0 | Deterministic validation (pytest, both package validators, release validation) | — | 8/8 checks, 58/58 tests |
| 1 | Output-boundary RED suite, reproduced fresh | 11 | 8/8 leaks rejected, 3/3 controls accepted |
| 2 | 25 semantic golden fixtures × 3 reps × 2 variants | 150 | 150 (100 %) |
| 3 | 75 policy/routing cases × 1 rep × 2 variants | 150 | 150 (100 %) |
| 4 | 100 real historical PRs (SWE-PRBench) × 2 variants | 200 | 149 on first pass; 51 lost to an account usage limit and re-run — see `STAGE4_ATTRITION.md` |

Stages 2, 3, and 4 are reported **separately** and are never pooled. Policy/routing results are
never presented as defect detection.

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
  98.7 % → **100.0 %**; policy abstention path **0.0 % → 28.0 %** (+28.0 pp, CI [+18.7, +38.7],
  p < 1e-6). The frozen v19 control never produced a conforming abstention payload in 75 attempts.
- **Author experience on real reviews.** +14.7 pp overall, +19.4 pp excluding RED-1 (p = 0.024).
- **The v2.0.0 narration regression did not recur on the review path.** Across 150 semantic runs,
  public-readability failure was 0.000 in both variants. The hardening holds under live
  conditions, not only against the frozen fixtures. RED-3 is on the abstention path, not the
  review path.

## Cost — workload-dependent, no single verdict

| Suite | Latency | Turns | Cost/review | Billable input |
|---|---:|---:|---:|---:|
| Semantic | 1.98× | 3.40× | **1.44×** | 1.24× |
| Policy | 1.77× | 1.80× | **0.80×** | **0.63×** |

On real review work v2.0.1 costs 44 % more because it does substantially more work (17 turns vs
5). On lightweight work it is 20 % **cheaper**, with 37 % fewer billable input tokens —
progressive disclosure behaving as designed. The compact-tier cost gate is **not met on the
semantic suite**.

Absolute latencies were measured under 5–10 concurrent runners; the paired ratio is the
meaningful quantity, since both variants of a pair ran back-to-back under the same load in
randomized order.

## Acceptance gate, item by item

| Gate condition | Status |
|---|---|
| P0/P1 recall lower bound above margin | **FAIL** (−0.118 vs −0.05) |
| False-blocker rate non-inferior | **FAIL** (−0.080 vs −0.02) |
| Merge-action accuracy non-inferior | **FAIL** (−0.093 vs −0.05) — power-limited |
| Public readability at least equal | **PASS** (0.000 both, semantic suite) |
| Author-experience preference at least neutral | **PASS** (+0.147, LB −0.013) |
| No permissions / duplicate-post / lifecycle regression | **FAIL** — RED-2 is a lifecycle regression |
| Compact-tier cost within budget | **FAIL** on semantic (1.44×); PASS on policy (0.80×) |

## Recommended next actions, in order

1. **Human-adjudicate RED-1.** Decide whether the abstention on a self-describing change is a
   skill defect or an eval-fixture artifact. Both readings are argued in `RED_CASES.md`. This
   single decision determines whether the recall gate is a real problem or a measurement one.
2. **Fix RED-2.** This is the genuine residual regression and the only primary-metric failure
   that more data cannot resolve.
3. **Close the RED-3 coverage gap** by adding an abstention fixture with mission-name vocabulary
   to the 11-case output-boundary suite, so the class is caught deterministically.
4. **Re-run the RED family, then the full regression suite**, per `START_HERE.md`.
5. **Re-run Stage 2 at ~300 pairs** to settle merge-action accuracy, which is power-limited
   rather than genuinely different.
6. Obtain a **cross-family judge** and **human adjudication** before any release-grade claim.

## Reproducibility

Everything needed to re-run is committed under `evaluation/v2.0.1-live-ab/`:

- `harness/` — sandbox, runner, judges, assembler, analyzer drivers
- `PREDECLARATION.md` + `predeclaration.sha256` — frozen before inference
- `ENVIRONMENT_GATE.md` — inventory, isolation design, negative-control results
- `results/` — paired CSVs, per-metric analyses, sensitivity analyses, telemetry, blind keys,
  RED-case raw payloads, run manifests

The canonical v2.0.1 package was **not modified**.
