# Live Paired A/B: `reviewing-pull-requests` v2.0.0 vs frozen v19

Results of a real, paired, blind-judged semantic A/B evaluation of the
`agentic-code-review-skills-v2.0.0` release candidate against the frozen v19
code-review prompt pair. Run 2026-08-10 in preview/read-only mode.

**Start with [`artifacts/LIVE_AB_REPORT.md`](artifacts/LIVE_AB_REPORT.md).**

## Result in one paragraph

The treatment is **safe and non-inferior on correctness** (merge-decision
accuracy 88.4% vs 90.3%, McNemar p=0.29; no preview/permission/injection
regressions) and **significantly preferred on the 100-case official eval set
by two independent blind judges** (p=0.0024 and p=0.0045). It is a
**statistical tie on the 25 concrete golden defect fixtures**. It has one
**replicated regression**: public-review readability (−0.26 to −0.41 across
four independent measurements), traced to a concrete mechanism — 55% of
Stage 1 treatment outputs narrate the skill's internal wave orchestration in
the preamble, violating the skill's own private-trace boundary. The
acceptance gate is therefore **not passed as-is**; the fix is specified but
was not applied, because model quota ran out before it could be re-validated.

## Contents

| Path | Contents |
|---|---|
| `artifacts/LIVE_AB_REPORT.md` | full report, acceptance-gate assessment, RED case |
| `artifacts/LIMITATIONS.md` | every constraint affecting interpretation |
| `artifacts/ENVIRONMENT_AND_MODELS.md` | probed capability inventory |
| `artifacts/RUN_MANIFEST.json` | denominators, seeds, tool policy, SHAs |
| `artifacts/LIVE_AB_RESULTS.jsonl` | one record per usable pair, both judges |
| `artifacts/PAIRED_CASE_SCORES.csv` | per-pair per-dimension score deltas |
| `artifacts/HUMAN_ADJUDICATION_QUEUE.md` | 127 pairs needing human review |
| `artifacts/verdict-audit-stage1.txt` | adversarial audit of non-tie verdicts |
| `artifacts/CHANGELOG.md` | harness changes and integrity fixes |
| `harness/` | the runner, blind judge, escalation selector, and stats scripts |
| `raw/<stage>/` | run manifests, per-stage stats, judge verdicts and sealed A/B mappings |

Full raw run directories (prompts, CLI envelopes, responses, timings) were
retained in the session scratchpad; the resumable manifests needed to
reconstruct or continue the evaluation are in `raw/`.

## Coverage actually achieved

| Stage | Planned pairs | Usable pairs | Judged | Runner model |
|---|---:|---:|---:|---|
| 1 — 25 golden PR fixtures | 75 | 69 | 69 × 2 judges | `claude-fable-5` |
| 2 — 100 official evals | 300 | 162 | 77 / 162 | `claude-fable-5` |
| 3 — 30 real SWE-PRBench PRs | 30 | 27 | not judged | `claude-opus-5` |

Shortfalls are account usage limits and safety-classifier refusals, symmetric
across both arms. No result was extrapolated to cover a gap.

## Guarantees

- Preview/read-only throughout: **no PR comments, reviews, approvals, ticket
  writes, or pushes to any third-party repository**.
- Child agents ran with no Bash/Write/Edit/network tools and no MCP servers;
  platform tokens were stripped from their environment.
- Identical model, effort, tools, timeout, and source context per variant
  within each stage; variant order randomized per case from a fixed seed.
- Fixture ground truth was stripped from runner inputs (the bundled scripts do
  not do this) and written only after each run finished.
- The canonical skill, the frozen v19 control, and all fixtures are
  **unmodified** — verified by SHA-256 in `artifacts/RUN_MANIFEST.json`.

## Reproducing

```bash
python harness/run_ab_parallel.py \
  --evals <evals.json> --skill-dir <skill> --baseline-prompt <v19.md> \
  --workspace <ws> --runs 3 --jobs 6 --model claude-fable-5 --effort high
python harness/judge_ab.py --workspace <ws> --rubric <JUDGE_RUBRIC.md> \
  --model claude-opus-5 --tag secondary
python harness/stats_ab.py --workspace <ws> --judges primary secondary
```

Both runner and judge are resumable: completed units and verdicts are skipped.
