# Stage 4 — 100 Real Historical PRs (SWE-PRBench)

**Suite:** 100 real merged PRs × 1 repetition × 2 variants = **200 runs, 100 paired cases**
**Control:** frozen v19 preview prompt · **Treatment:** `reviewing-pull-requests` v2.0.1
**Ground truth:** human maintainer review comments from the original PR threads
**Judges:** blind technical (`claude-opus-5`, sees ground truth) + blind author-experience
(`claude-opus-5`, sees only the two final payloads)

---

## Status of this stage: supporting evidence, **not** gate-bearing

`PREDECLARATION.md` (sha256 `b1e8249d…`, frozen 2026-08-11T06:55:27Z) defines the acceptance
gate on the **Stage 2** rubric: P0/P1 blocker recall, false-blocker rate, merge-action accuracy,
author-experience preference. It does **not** define the PRBench rubric used here
(`human_recall`, `any_fabricated`, CONFIRMED/PLAUSIBLE/FABRICATED).

That rubric and its margins (0.05 / 0.02, assigned by analogy to the Stage 2 margins) were
written **after** the predeclaration was frozen. Choosing a margin after seeing the metric it
will be applied to is exactly what makes a non-inferiority claim unfalsifiable, so:

- **the acceptance gate remains decided by Stage 2 alone**, and
- every non-inferiority *decision* in the table below is reported for completeness but carries
  no gate authority.

**One class of conclusion here does survive the predeclaration gap:** where the 95 % paired
confidence interval excludes **zero**, the direction of the difference is established without
reference to any margin. Two metrics do that, and they are the substantive result of this stage.

## Concealment gate — met at two independent layers

Continuation to real PRs was conditional on human findings being concealed from runners.
Both layers were verified before Stage 4 inference:

1. **Input stripping.** The shipped SWE-PRBench importer leaves `pr_url`, `repo`, `task_id`,
   `base_commit`, and `head_commit` in *runner-visible* input. These were stripped. Runners
   receive the diff and PR description only — no identifier that names the upstream PR.
2. **Egress denial.** The agent proxy returns `403 GitHub access to this repository is not
   enabled for this session` for every repository in the corpus, while a control fetch to
   `example.com` returns 200. Even a runner that guessed the repository could not retrieve the
   human review thread.

Runner isolation is the same per-run mount namespace proven by negative control in
`ENVIRONMENT_GATE.md`: judge-private ground truth, sibling variant outputs, and the corpus
source are absent from the runner's filesystem view, not merely unreadable.

## Attrition

| Item | Count |
|---|---:|
| Planned runs | 200 |
| Valid runs (final) | **200 (100 %)** |
| Invalid runs (final) | **0** |
| Runs lost on first pass to an account usage limit | 51 |
| Retried, recovered | **51 / 51 (100 %)** |
| Gradable pairs | **100 / 100** |
| Pairs with both judge verdicts | **100** |
| Permission denials | 0 |

The usage-limit incident and its recovery are documented in `STAGE4_ATTRITION.md`. Retried
records are flagged `retried: true` in `runs.jsonl`; no successful run was discarded or repeated.

Latency and cost below include retried runs, which executed at 5-way rather than 10-way
concurrency. The paired ratio remains the meaningful quantity.

## Results

Effect is oriented so **positive = treatment better**. `human_recall` is scored on the 86 PRs
whose ground truth contains at least one human maintainer review comment; the other 14 have no
human comments and cannot contribute to a recall measure.

| Metric | n | Control | Treatment | Effect | 95 % CI | Margin | p | Decision |
|---|---:|---:|---:|---:|---|---:|---:|---|
| Human-comment recall | 86 | 0.442 | 0.337 | **−0.105** | **[−0.198, −0.023]** | 0.05 | 0.035 | **inferior** |
| Technical preference | 100 | 0.410 | 0.160 | **−0.250** | **[−0.390, −0.110]** | 0.10 | 0.0013 | **inferior** |
| Any fabricated finding | 100 | 0.070 | 0.110 | −0.040 | [−0.120, +0.040] | 0.02 | 0.481 | not demonstrated |
| Author-experience preference | 100 | 0.350 | 0.280 | −0.070 | [−0.220, +0.080] | 0.10 | 0.450 | not demonstrated |
| Public-readability failure | 100 | 0.020 | 0.000 | +0.020 | [+0.000, +0.050] | 0.05 | 0.500 | non-inferior |
| Output-contract pass | 100 | 0.970 | 1.000 | +0.030 | [+0.000, +0.070] | 0.05 | 0.250 | non-inferior |

Ties were preserved: 43 technical ties and 37 author ties, never redistributed.

### The two margin-free findings

**Human-comment recall and technical preference are not "non-inferiority not demonstrated" —
they are measured inferiority.** In both cases the entire 95 % confidence interval lies below
zero, so the finding does not depend on the margin that was chosen after the fact:

- **Recall.** Control surfaces the human maintainer's concern on 44.2 % of PRs, treatment on
  33.7 %. Discordant pairs run **12 control-only against 3 treatment-only** — a 4:1 split.
- **Technical preference.** The blind technical judge, holding the real review thread, prefers
  control on 41 PRs and treatment on 16, with 43 ties. Discordant pairs **41 to 16**.

Applying a Bonferroni correction for the six metrics tested (α = 0.0083), **technical preference
survives** (p = 0.0013) and **recall does not** (p = 0.035). Recall's confidence interval still
excludes zero at the uncorrected 95 % level, and its point estimate, direction, and discordant
split all agree with the Stage 2 recall deficit. It is reported as a directional finding with
that multiplicity caveat attached, not as an independently confirmed result.

### Author preference reverses against Stage 2

This is the most important cross-stage signal in the evaluation.

| Suite | Control | Treatment | Effect |
|---|---:|---:|---:|
| Stage 2 — 25 golden fixtures | 0.173 | 0.320 | **+0.147** |
| Stage 4 — 100 real PRs | 0.350 | 0.280 | **−0.070** |

v2.0.1's clearest Stage 2 win — author experience — **does not reproduce on real PRs**. Neither
estimate is individually significant, and the intervals overlap, so this is not proof that the
Stage 2 result was an artifact. But it removes the basis for claiming an author-experience
improvement generally: the one suite drawn from real-world review work points the other way.

The golden fixtures are authored alongside the skill; real PRs are not. Where a metric moves in
opposite directions across those two populations, the real-PR direction is the one that
describes production behavior.

### Finding volume — treatment says less

| | Control | Treatment |
|---|---:|---:|
| Confirmed findings (match a human comment) | 47 | 37 |
| Plausible findings (diff-supported, no human match) | 307 | 239 |
| Mean findings per review | 3.54 | 2.76 |

Treatment raises **22 % fewer findings** and confirms 21 % fewer against human ground truth.
This is filtering, not fabrication: the fabricated-finding rate is statistically
indistinguishable (7 % vs 11 %, p = 0.48). Treatment is more conservative, and on this corpus
that conservatism costs more true findings than it saves false ones.

This is consistent with the Stage 2 picture — RED-1's abstention, the useful-P2/P3 retention
deficit — reproduced on an independent, real-world corpus with human ground truth.

## Cost

| Measure | Control | Treatment | Ratio |
|---|---:|---:|---:|
| Wall-clock per review | 206.3 s | 254.6 s | 1.23× |
| Turns per review | 9.2 | 20.7 | **2.26×** |
| Cost per review | $0.772 | $0.955 | **1.24×** |
| Output tokens | 19,116 | 21,817 | 1.14× |
| Billable input tokens | 54,224 | 61,984 | 1.14× |
| Stage total | $77.18 | $95.48 | 1.24× |

On real PRs v2.0.1 costs **24 % more** and takes **2.26× the turns** while producing fewer
confirmed findings. The semantic-suite ratio was 1.44×; the true premium on production-like
work sits between the two, and in neither case is it accompanied by a measured quality gain.

## Judge agreement

| Item | Value |
|---|---:|
| Pairs with both verdicts | 100 |
| Technical and author judges agree | 57 |
| Disagree | **43 (43 %)** |

Disagreement is high and is reported **unadjudicated** — no human reviewer is available in this
environment. The two judges answer different questions (technical correctness against ground
truth versus author experience from the payload alone), so disagreement is expected rather than
anomalous, but 43 % is high enough that neither preference metric should be read as a settled
quality ranking. All 43 disagreeing pairs are preserved verbatim for later human adjudication.

## Limitations specific to this stage

1. **Margins not predeclared** — see the top of this document. The gate stays with Stage 2.
2. **Single repetition per case.** Stages 2 used 3 reps; Stage 4 uses 1. Per-case variance is
   not estimated, so a case-level result may reflect run-to-run noise. The paired design still
   controls for case difficulty, which is the dominant variance component.
3. **Same-family judge.** `claude-opus-5` judging `claude-sonnet-5` controls for runner
   self-preference but not for shared model-family bias. `LIVE_AB_PROTOCOL.md` asks for a
   different model family; that requirement is **not met** and no substitute was invented.
4. **Human comments are an incomplete oracle.** A maintainer comment records what one reviewer
   chose to raise on that day, not the complete set of defects. A finding scored PLAUSIBLE may
   be a real defect no human happened to mention. `human_recall` therefore measures agreement
   with a human reviewer, not absolute defect detection — which is why fabrication is tracked
   separately rather than inferred from non-matching findings.
5. **No human adjudication** of the 43 judge disagreements.

## Harness defect found during this stage

**Silent ground-truth loss for case IDs containing non-alphanumeric characters.** This is a
defect in the shipped v2.0.1 evaluation harness, not in either prompt variant.

| Location | Behaviour |
|---|---|
| `run_live_ab.py:51` | `slug()` maps any character outside `[alnum-_]` to `-` |
| `run_live_ab.py:196, :246` | workspace run dir and judge-private key use the **slugged** ID |
| `run_live_ab.py:218` | `runs.jsonl` records the **raw** ID |
| `grade_live_ab.py:99, :132` | resolves the judge-private ground-truth path from the **raw** ID |

For any case whose ID contains a dot, the grader looks for ground truth at a path that was never
written:

```
written by runner : eval-swe-prbench-discord-py__10307/ground-truth.json
sought by grader  : eval-swe-prbench-discord.py__10307/ground-truth.json
```

The technical judge then receives a nonexistent ground-truth file. Two of the 100 PRs were
affected — `discord.py__10307` and `transformers.js__1436` — because real repository names carry
dots. No shipped golden or policy fixture ID is affected, which is why Stages 1–3 ran clean; the
defect only surfaces on a real-world corpus.

Two aggravating factors made it near-invisible:

1. `grade_live_ab.py:74–75` captures the judge command's `returncode` into the report but
   **never checks it**. The wrapper's `exit 65` and its stderr message were recorded and ignored.
2. The grader writes one `grade-report.json` per shard, so running it once per judge role means
   the **second role's `judge_execution` record overwrites the first's**. The author pass, which
   needs no ground truth and succeeded, erased the technical pass's exit-65 evidence. The only
   surviving symptom was the absence of a verdict file.

**Resolution.** The ground-truth *content* was intact throughout — the payloads carry the correct
raw `case_id` and their human comments merged correctly (3 and 6 comments respectively); only the
directory spelling differed. The ground truth was placed at the path the grader resolves and the
two technical verdicts were re-run. Both cases are included in the 100 reported pairs. The
canonical v2.0.1 package was **not modified**.

Recommended upstream fixes, in order of value:

1. Record the slugged ID in `runs.jsonl`, or slug on read in `grade_live_ab.py` — either makes
   the two paths agree by construction.
2. Raise on a nonzero judge exit code, or at minimum surface a `judge_failed` count in the
   grade-report summary.
3. Key `judge_execution` by role, so a second judge pass cannot overwrite the first's record.

## Reproducibility

- `results/prbench/paired/` — paired CSVs, `assembly-manifest.json`, `paired-rows.json`
- `results/prbench/analysis/` — per-metric bootstrap analyses
- `results/prbench/telemetry.json` — per-variant latency, turns, tokens, cost
- `results/blind-keys/prbench/` — blind A/B mappings, written only after judging completed
