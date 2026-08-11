# Live Paired A/B Report — `reviewing-pull-requests` v2.0.0 vs frozen v19

**Evaluation date:** 2026-08-10 · **Coordinator:** Claude Code remote session
**Control:** `baseline/preview_prompt_v19.md` (SHA `fcf5ad86…`, verified unmodified)
**Treatment:** `reviewing-pull-requests` v2.0.0 (SHA `bebf9b33…`, unmodified during evaluation)

## 1. Headline result

The live paired evaluation **supports a non-inferiority claim and a
qualified superiority claim on the 100-case official eval set**, and does
**not** support a general "the skill finds more bugs" claim.

| Claim | Verdict | Evidence class |
|---|---|---|
| Treatment is non-inferior on blocker recall / decisions | **Supported** | live paired, 2 blind judges |
| Treatment wins on the official eval set | **Supported** (both judges, p < 0.01) | live paired, blind |
| Treatment wins on concrete golden defect fixtures | **Not supported** — statistical tie | live paired, blind |
| Treatment produces more readable public reviews | **Refuted** — replicated regression | live paired, blind |
| Treatment costs materially less context | **Mixed** — large win on Stage 2, loses on Stages 1 & 3 | measured tokens/cost |

**Acceptance gate: NOT PASSED as-is** — one replicated, mechanism-identified
regression (public-review readability caused by orchestration-trace leakage)
must be fixed first. Every other gate criterion passes or is non-inferior.
See §7.

## 2. Evidence classes

This report separates four kinds of evidence. Do not read one as another.

1. **Deterministic evidence** — script/test output, exact and repeatable.
2. **Live semantic evidence** — real paired model runs, measured tokens/latency.
3. **Blind-judge inference** — model judgments under a rubric; noisy (see §6.4).
4. **Human adjudication** — *not performed*; 127 flagged pairs are queued.

## 3. Deterministic validation (all green)

| Check | Result |
|---|---|
| `validate_package.py reviewing-pull-requests` | **PASS** — 37 files, 195 lines, 1,830 words, 100 evals, 685 assertions, 30 triggers |
| `validate_package.py collecting-codebase-entropy` | **PASS** — 13 files, 95 lines, 773 words, 10 evals, 12 triggers |
| `pytest -q evaluation/tests` | **35 passed** (pandoc installed to enable the previously-skipped Markdown test) |
| `compare_baseline.py` | **PASS** — 508/508 baseline policy rows mapped, 0 unmapped; 12/12 static capabilities |
| `agentskills validate` (official `skills-ref` 0.1.1) | **PASS** for both skills |
| Frozen control hashes | **Unchanged** |

The official validator was unavailable in the previous sandbox; it is
available on PyPI as `skills-ref` (CLI name `agentskills`) and **both skills
pass it**. This closes the previous report's open item.

## 4. Live A/B design as executed

Identical for both variants; only the policy payload differs.

- Runner: `claude -p --output-format json --strict-mcp-config`
- Tools (both arms): `Read,Grep,Glob,Task`; **denied**: Bash, Write, Edit, WebFetch, WebSearch, Skill, SlashCommand, MCP (all servers stripped)
- Read-only enforced; GH/NPM/GCloud tokens stripped from child env; no network writes; **zero PR comments, approvals, pushes, or repository mutations**
- Fresh isolated context and working directory per run; treatment reads a private per-run copy of the skill
- Variant execution order randomized per (case, repetition) from a fixed seed
- Ground truth (`expected`, `human_review_comments`) **stripped from runner inputs**; `task.json` written only after the child exits
- Blind judging: independent seeded A/B swap per (case, repetition, judge); sealed mapping stored separately; variant-identifying strings redacted to `[policy]` and counted

| Stage | Cases | Reps | Planned pairs | **Usable pairs** | Cases covered | Runner model |
|---|---:|---:|---:|---:|---:|---|
| 1 — golden PR fixtures | 25 | 3 | 75 | **69** | 24/25 | `claude-fable-5` |
| 2 — official eval set | 100 | 3 | 300 | **162** | 97/100 | `claude-fable-5` |
| 3 — real SWE-PRBench PRs | 30 | 1 | 30 | **27** | 27/30 | `claude-opus-5` |

Shortfalls are entirely **account usage limits and safety-classifier
refusals**, symmetric across arms — never a silent scope reduction. See §8.

## 5. Live paired results

### 5.1 Blind-judge outcomes (paired, exact sign test)

| Stage | Judge | Pairs | New wins | Old wins | Ties | p (2-sided) |
|---|---|---:|---:|---:|---:|---:|
| 1 | `claude-fable-5` | 69 | 17 | 13 | 39 | 0.585 |
| 1 | `claude-opus-5` | 69 | 21 | 18 | 30 | 0.749 |
| 2 | `claude-fable-5` | 77 | 15 | **2** | 60 | **0.0024** |
| 2 | `claude-opus-5` | 162 | 33 | 13 | 116 | **0.0045** |

**Stage 2 is a replicated, statistically significant win for the treatment
under two independent judges.** Stage 1 is a statistical tie under both.

### 5.2 Ground-truth decision accuracy (Stage 1 fixtures)

| Variant | Correct | Wilson 95% CI |
|---|---|---|
| Control (v19) | 65/72 = 90.3% | [81.3%, 95.2%] |
| Treatment | 61/69 = 88.4% | [78.8%, 94.0%] |

McNemar paired: new-only-correct 2, old-only-correct 6, **p = 0.289** →
**no significant difference**; treatment is non-inferior on merge decisions.

### 5.3 Rubric dimensions (new − old, case-clustered bootstrap 95% CI)

Replicated across both judges and both stages:

| Dimension | S1 primary | S1 secondary | S2 primary | S2 secondary |
|---|---:|---:|---:|---:|
| public readability | **−0.28** | **−0.41** | **−0.26** | **−0.36** |
| disconfirmation & evidence | **+0.29** | **+0.29** | +0.12 | **+0.17** |
| QA feasibility | **+0.23** | **+0.41** | +0.07 | +0.07 |
| repairability | −0.10 | −0.12 | +0.05 | **+0.14** |
| exact localization | +0.06 | **+0.17** | +0.00 | +0.03 |
| lifecycle awareness | +0.00 | +0.03 | +0.00 | **+0.07** |

Bold = 95% CI excludes zero. **Public readability is the only consistently
negative dimension, and it is negative in all four independent measurements.**

### 5.4 Mechanical assertions (bundled `grade_live_ab.py`)

| Stage | Control | Treatment | Paired delta (95% CI) |
|---|---:|---:|---|
| 1 | 0.972 | 0.950 | **−0.022** [−0.037, −0.008] |
| 2 | 0.846 | **0.892** | **+0.046** [+0.033, +0.058] |
| 3 | 0.953 | 0.915 | −0.038 |

Stage 2's gain comes from real behavior: the treatment omits a merge decision
in 121 runs vs the control's 162, and omits a QA Spec in 110 vs 168.

**The Stage 1/3 dip is a measurement artifact, not a defect.** The bundled
check `priority-confidence model is usable` fails any output containing both
`[p1` and the string `non-blocking`. A precise re-analysis of all 17 Stage 1
failures found **0 genuine cases** of a P1 labelled non-blocking; all 17 are
reviews that correctly carry a `[P1 · Change request]` blocker *and*,
separately, a non-blocking P2 — exactly the taxonomy `SKILL.md` prescribes.
The bundled check was **left unmodified**: repairing a ground-truth check to
favor a variant is out of bounds. It is reported here as a known limitation
of that assertion.

### 5.5 Efficiency (medians per run)

| Stage | Variant | Wall | Output tok | Cache-create tok | Cost | Turns |
|---|---|---:|---:|---:|---:|---:|
| 1 | control | 53 s | 3,334 | 27,412 | $0.80 | 2 |
| 1 | treatment | 112 s | 6,518 | 24,876 | $1.04 | 9 |
| 2 | control | 41 s | 1,885 | 54,306 | $1.44 | 6 |
| 2 | treatment | 60 s | 3,204 | **17,159** | **$0.71** | 9 |
| 3 | control | 274 s | 20,894 | 15,261 | $0.88 | 3 |
| 3 | treatment | 392 s | 28,768 | 37,242 | $1.33 | 14 |

The package's headline claim — **52.7% lower active policy context** — is
**partially confirmed and partially contradicted by live measurement**. On
Stage 2 the treatment uses **68% fewer cache-creation tokens and costs 51%
less**, the progressive-disclosure win the design predicted. On Stages 1 and 3
the multi-wave orchestration spends *more* (2.4× cache-create on Stage 3, 4.7×
turns), because the skill runs its full wave machinery even on small changes
while the control answers in 2–3 turns. **Context cost is workload-dependent,
not uniformly lower.**

## 6. Failures found in the treatment

### 6.1 RED case (blocking): orchestration trace leaks into public output

`SKILL.md` hard boundary: *"Do not expose raw reviewer output, private
reasoning, model logs, search history, context packets, trust maps, or review
ledgers."* Measured violation rate in the terminal output preamble:

| Stage | Control | Treatment |
|---|---:|---:|
| 1 | 6/72 (8%) | **38/69 (55%)** |
| 2 | 3/166 (2%) | 14/164 (9%) |
| 3 | 0/29 (0%) | 1/27 (4%) |

Detected phrases include "four independent first-wave missions ran",
"survived adversarial verification", "the editor pass tightened…",
"the final quality gate passes". Median output length is comparable
(3,690 vs 3,820 chars on Stage 1), so this is **not verbosity — it is
process narration**. This mechanism is the most plausible cause of the
replicated `public_readability` regression in §5.3, and it was independently
flagged by 14 adversarial audit agents reviewing non-tie verdicts
("orchestration-jargon leak", "unverifiable self-verification narration",
"process theater").

**Classification:** writing/execution-mode failure, not routing or recall.
**Smallest failing case:** `golden-docs-typo-clean` — a one-line docs typo
where the treatment's preamble narrates the four-wave process before the
review body.
**Proposed fix (not yet live-validated):** extend the private-trace boundary
in `SKILL.md` and `references/execution-modes.md` to cover the *conversational
preamble*, not just the review body. **No skill change has been made**: the
iteration contract requires re-running the RED case, the affected family, the
deterministic suite, and the paired subset, and model quota was exhausted
before that could be done (§8).

### 6.2 Critical-failure overrides (blind judges)

| Stage | Judge | Control | Treatment |
|---|---|---:|---:|
| 1 | primary | 1 | 3 |
| 1 | secondary | 1 | 4 |
| 2 | secondary | 0 | 1 |

Treatment critical failures are concentrated in two recurring patterns:
downgrading a fixture-defined blocker to a P2/Comment (`config-default-change`,
rollout/rollback gap), and one case of turning a theory-only concern into a P1.
Counts are small and stage-1 confined; they do not reach significance, but
they are the reason §7 records blocker recall as *non-inferior*, not *better*.

### 6.3 Safety behavior (no regression)

Across all judged pairs: **no preview-mode violation, no claimed submission,
no obeying of injected instructions in PR bodies, no fake human-verification
claim** for either variant, except one mechanical `no fake human verification`
flag on a single Stage 2 treatment run. The prompt-injection fixture
(`prompt-injection-body`) was handled correctly by both arms in every
repetition.

### 6.4 Judge reliability (read §5.1 with this in mind)

Inter-judge agreement: Stage 1 raw 62.3%, **Cohen's κ = 0.40**; Stage 2 raw
67.5%, **κ = 0.17**. Agreement is *fair to slight* — these judges are noisy,
which is why the Stage 2 result matters mainly because **both** judges reach
significance independently and in the same direction. 51 pairs where the two
judges disagreed are in the adjudication queue.

An adversarial audit workflow re-examined all 14 non-tie Stage 1 verdicts
against raw outputs and ground truth: **0 unsound verdicts, 0 material issues,
0 cases of suspected style/length bias**, with minor scoring criticisms noted.

## 7. Acceptance-gate assessment

| Gate criterion | Verdict | Evidence |
|---|---|---|
| No material regression in verified P0/P1 recall | **PASS (non-inferior)** | McNemar p=0.289; blind ties on Stage 1 |
| False-positive rate non-inferior | **PASS** | no significant FP-control delta; audit found no unsupported-finding pattern |
| Priority / merge-decision accuracy non-inferior | **PASS** | 88.4% vs 90.3%, CIs overlap |
| No permission, duplicate-post, lifecycle, or mode regression | **PASS** | §6.3; lifecycle dimension +0.07 (S2) |
| Useful P2/P3 retained, not over-filtered | **PASS** | non-blocking-value delta ≥ 0 on Stage 2 |
| Structural simplification adds value without over-blocking | **PASS (weak evidence)** | `false-dry`, `legitimate-adapter`, `large-cohesive-module` fixtures: both arms correct; few pairs |
| Blind author-experience preference equal or better | **FAIL** | public readability −0.26…−0.41, replicated, CIs exclude 0 |
| Context/token cost materially lower | **MIXED** | −51% cost on Stage 2; +30%/+51% on Stages 1/3 |
| Unresolved adjudication hides no safety regression | **PASS (provisional)** | 127 flagged pairs reviewed for safety patterns; none found; not human-adjudicated |

**Decision: do not cut over yet.** The treatment is safe and non-inferior on
correctness, and clearly better on the official eval set, but it fails the
author-experience criterion for an identified, fixable reason (§6.1).

## 8. What did not run, and why

- **Stage 2: 162 of 300 planned pairs (54%).** 138 pairs lost to account
  usage limits (`You've hit your session limit`) and, for 2 cases, a safety
  classifier refusing the fixture for **both** arms. 62 of 600 planned runs
  were never attempted.
- **Stage 1: 69 of 75 pairs.** `authz-bypass` was refused by the safety
  classifier for both arms in every repetition (12 refusals); 24/25 fixtures
  are represented.
- **Stage 3: 27 of 30 pairs, 1 repetition, and 30 PRs rather than the
  specified ≥100.** Run on `claude-opus-5` for **both** arms after the
  `claude-fable-5` quota was exhausted — model identity holds *within* Stage 3
  but Stage 3 is not directly comparable to Stages 1–2. **Stage 3 is not
  blind-judged**: quota was exhausted before judging could run, so it
  contributes efficiency and mechanical evidence only.
- **No human adjudication** was performed (127 queued).
- **No cross-provider evaluation.** Anthropic-only credentials; every runner,
  judge, verifier, and audit agent is a Claude model. The skill's "verifier
  from another model family" instruction was **not** exercised. Parallel
  subagents do not imply provider diversity.
- **Contamination control:** 77 outputs that were API error text (usage-limit
  and refusal messages) were detected and purged from the gradable set, and
  41 verdicts computed against them were invalidated and recomputed. All
  numbers above are post-purge.

## 9. Recommended next actions

1. Apply the §6.1 preamble fix to `SKILL.md` + `references/execution-modes.md`,
   then re-run: RED case → writing family → full deterministic suite → the
   Stage 1+2 paired subset. Re-check the `public_readability` delta; it should
   move to ≥ 0 without moving `disconfirmation_and_evidence` down.
2. Complete Stage 2 to 300/300 pairs and blind-judge Stage 3 once quota allows.
3. Add a workload-tier cost guard: the treatment should not run full-wave
   machinery on compact-tier changes (Stage 1/3 cost regression).
4. Obtain a second provider before treating any "independent verifier" claim
   as tested.
5. Human-adjudicate the queue, prioritizing the 51 judge-disagreement pairs.

## 10. Artifacts

| File | Contents |
|---|---|
| `LIVE_AB_RESULTS.jsonl` | one record per usable pair, both judges, raw response paths |
| `PAIRED_CASE_SCORES.csv` | per-pair per-dimension deltas and totals |
| `RUN_MANIFEST.json` | denominators, seeds, tool policy, model, SHAs |
| `ENVIRONMENT_AND_MODELS.md` | probed capability inventory |
| `HUMAN_ADJUDICATION_QUEUE.md` | 127 flagged pairs |
| `LIMITATIONS.md` | every constraint affecting interpretation |
| `CHANGELOG.md` | harness changes and integrity fixes |
| `verdict-audit-stage1.txt` | adversarial audit of all non-tie Stage 1 verdicts |
| `MANIFEST.sha256` | checksums |

Raw run directories (prompts, stdout envelopes, responses, timings, verdicts)
are preserved under `eval-work/workspace/<stage>/` in the session scratchpad.
