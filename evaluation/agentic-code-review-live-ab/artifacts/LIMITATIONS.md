# Limitations

Everything here constrains how the results in `LIVE_AB_REPORT.md` may be read.
Nothing was substituted silently; each item was probed and recorded.

## 1. Coverage shortfalls (exact denominators)

| Stage | Planned pairs | Usable pairs | Coverage | Cause |
|---|---:|---:|---:|---|
| 1 — golden fixtures | 75 | 69 | 92% | safety-classifier refusal of `authz-bypass` for **both** arms (12 refusals) |
| 2 — official evals | 300 | 162 | 54% | account usage limits (`session limit` / `Fable 5 limit`) |
| 3 — real PRs | 30 (spec asks ≥100) | 27 | 90% of the reduced set | usage limits; scope reduced to 30 stratified PRs to fit remaining quota |

- 62 of Stage 2's 600 planned runs were never attempted.
- Losses are **symmetric across arms** (Stage 2 failures: 105 treatment vs 103 control), so pairing integrity holds; the risk is reduced power, not directional bias.
- Stage 1's missing fixture (`authz-bypass`) is a P1 authorization case — a category where the treatment was otherwise strong; its absence slightly *disfavors* neither arm since both were refused.

## 2. No provider diversity

Only Anthropic first-party models were reachable. Every runner, blind judge,
adversarial auditor, and verifier was a Claude model. Consequences:

- The skill's Wave-3 instruction ("independent verifier **from another model
  family**") and its public-editor equivalent were **never exercised as designed**.
- Multiple parallel subagents ran, but parallelism is not provider diversity.
- Judge independence is only partial: the primary judge (`claude-fable-5`) is
  the *same model* that generated both arms' outputs in Stages 1–2. Self-family
  preference cannot be excluded. The secondary judge (`claude-opus-5`) is a
  different model and reproduced the same directional Stage 2 result, which
  mitigates but does not eliminate this.

## 3. Judge reliability

- Inter-judge agreement: Stage 1 κ = 0.40 (fair), Stage 2 κ = 0.17 (slight).
- 51 pairs had outright judge disagreement; 127 pairs were flagged for human
  adjudication. **No human adjudication was performed.**
- Blind-judge scores are inference, not ground truth. The Stage 2 result is
  credible mainly because two independent judges reached significance in the
  same direction, not because either judge is individually reliable.

## 4. Stage 3 is weaker evidence than Stages 1–2

- Run on `claude-opus-5` (both arms) because `claude-fable-5` quota was
  exhausted. Model identity holds *within* Stage 3; Stage 3 is **not**
  comparable to Stages 1–2 run-for-run.
- **Not blind-judged** — quota ran out before judging. Stage 3 contributes
  efficiency and mechanical-assertion evidence only; no semantic conclusion is
  drawn from it.
- 30 PRs, 1 repetition, versus the specification's ≥100 real PRs across 11
  named risk categories. The 30 are difficulty-stratified
  (12 Type1_Direct / 12 Type2_Contextual / 6 Type3_Latent_Candidate,
  197 human ground-truth comments) but do not cover all named categories.
- Human review comments were stripped from runner inputs, but **no
  human-comment-overlap recall metric was computed** (that requires the
  unrun blind-judge pass).

## 5. Known measurement artifact in the bundled grader

`evaluation/scripts/grade_live_ab.py` fails the assertion
`priority-confidence model is usable` for any output containing both `[p1`
and the substring `non-blocking`. The treatment's prescribed label taxonomy
(`[P1 · Change request]` alongside `[P2 · Non-blocking]`) trips this by
construction. Precise re-analysis of all 17 Stage 1 failures found **0
genuine** P1-labelled-non-blocking contradictions. The check was deliberately
**not modified** — altering a ground-truth check to favor a variant is out of
bounds — so the reported Stage 1/3 mechanical deltas are pessimistic for the
treatment by roughly this amount.

## 6. Contamination that was detected and removed

API error text (usage-limit and safety-refusal messages) was initially written
into `response.md` by the harness and reached the grader. Detected via judge
comments ("output is a session-limit error message"). Remediation:

- 77 contaminated outputs purged from the gradable set (11 refusal + 66 limit).
- 41 verdicts computed against contaminated pairs invalidated; sealed A/B
  mappings deterministically rebuilt from their seeds.
- Runner hardened so error text is never written as a response.

All reported numbers are post-purge. Verdicts produced before the fix but
against clean pairs were retained.

## 7. Harness deviations from the bundled scripts

Documented in `CHANGELOG.md`. The substantive ones:

- Parallel runner replaces the bundled serial runner (identical prompts,
  layout, manifest fields, randomization); needed because the serial runner
  would take tens of hours for 750 runs.
- Child agents have **no Write tool**, so the review is captured from the CLI
  JSON envelope rather than written by the child to an output directory.
- Ground truth (`expected`, `human_review_comments`) is stripped from
  runner-visible inputs. **The bundled scripts do not do this** and would hand
  both runners the fixture's expected decision, priority, and finding. Any
  earlier result produced with the unmodified bundled runner should be treated
  as contaminated.

## 8. Statistical caveats

- Repetition counts are uneven after losses (Stage 2 cases have 1–3 usable
  repetitions), so case-level majority aggregation is under-powered; pair-level
  sign tests are the primary statistic.
- Bootstrap CIs are clustered by case to respect repeated measures, but with
  few repetitions per case the clustering correction is weak.
- No multiple-comparison correction was applied across the 12 rubric
  dimensions; individual dimension CIs should be read as exploratory except
  `public_readability`, which replicates across four independent measurements.
- Stage 1 (69 pairs) is under-powered to detect small recall differences; a
  true 5-point recall gap would likely not reach significance here.

## 9. Environment constraints

- Detached background processes do not survive turn boundaries in this
  environment; batches were run as bounded foreground windows, which
  fragmented execution and cost wall-clock time.
- GitHub access is scoped to `anhtaih/agent-harness`; no arbitrary-repository
  PR reads were possible, so Stage 3 used the public SWE-PRBench dataset export
  rather than live PR APIs.
- **No remote mutations of any kind** were performed: no PR comments, reviews,
  approvals, ticket writes, or pushes to third-party repositories.
