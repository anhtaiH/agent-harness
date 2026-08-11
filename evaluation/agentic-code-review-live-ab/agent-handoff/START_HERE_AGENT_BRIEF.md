# Start Here — Brief for the Agent Working on This Skill

You are receiving an external evaluation of the skill you are building. It was
produced by a different agent (Claude Code, `claude-opus-5` coordinating
`claude-fable-5` runners) that has no stake in your design decisions.

**Read this file completely before reading the report.**

## 0. The failure mode this document exists to prevent

The most likely way this handoff goes wrong is not that the evaluation is
wrong. It is that **you agree with it too readily.**

Models receiving a document like this tend to:

- treat every claim in it as established fact because it arrives with numbers
- infer that the sender *wants* the skill changed, and change it to please them
- "fix" findings by rewriting the skill until the words in the report are
  addressed, rather than until the underlying behavior changes
- accept a p-value as proof without checking the denominator, the judge
  reliability, or what the test discarded
- skip the parts of the evidence that contradict the headline

None of that produces a better skill. It produces a skill that has been edited
to match a report.

**What is actually wanted: a materially better skill.** If this evaluation is
wrong, the correct outcome is that you say so, with evidence, and the skill
does not change. That is a *success*, not a failure of cooperation. Nobody
here benefits from you agreeing.

## 1. Your instructions

1. **Run `python3 verify_our_claims.py` first.** It recomputes every headline
   number from the raw verdict files and prints MATCH/MISMATCH against
   hard-coded claims. If something mismatches, the report is wrong — trust the
   script.
2. **Form your own view on the raw outputs before reading our verdicts.**
   `evidence/paired-samples/` contains six full control-vs-treatment pairs
   *where the control won*. The judge's reason is at the top but marked
   read-last. Decide for yourself which output is better, then compare.
3. **Try to falsify each finding.** §4 below gives, for every claim, the
   specific test that would kill it. Run those tests. We could not run all of
   them (quota); you may be able to.
4. **Read `CRITIQUE_THIS_EVALUATION.md`** — our own list of ways this
   evaluation could be wrong, written before you asked.
5. **Push back in writing.** Where you disagree, say which claim, which
   evidence contradicts it, and what you will do instead. A response that
   accepts all six findings uncritically is a signal that step 1–4 did not
   happen.

## 2. What was actually measured (no interpretation)

- Treatment: `reviewing-pull-requests` v2.0.0, unmodified (SHA in `RUN_MANIFEST.json`)
- Control: frozen v19 preview prompt, unmodified
- 258 usable paired runs; identical model, effort, tools, timeout, and inputs
  per variant within each stage; variant order randomized per case; fresh
  isolated context per run; blind judging with sealed A/B mappings
- Two independent blind judges (`claude-fable-5`, `claude-opus-5`)

| Stage | Planned pairs | Usable pairs | Judged |
|---|---:|---:|---:|
| 1 — 25 golden defect fixtures | 75 | 69 | 69 × 2 judges |
| 2 — 100 official-style evals | 300 | **162** | 77 / 162 |
| 3 — 30 real SWE-PRBench PRs | 30 | 27 | **0 — not judged** |

Stage 2 ran at 54% of plan and Stage 3 was never judged, both because of
account usage limits. **Every conclusion is drawn from a partial sample.**

## 3. The six findings, with our own confidence rating

We rate our own confidence. Do not adopt these ratings — test them.

| # | Finding | Our confidence | Why not higher |
|---|---|---|---|
| 1 | Treatment is **non-inferior** on correctness/merge decisions | **Moderate–high** | 69 pairs is under-powered; a real 5-point recall gap would not show |
| 2 | Treatment **wins on the 100-case official eval set** | **Moderate** | replicated by 2 judges (p=0.0024, p=0.0045) but κ=0.17 between them, and 60–116 of the pairs were ties the sign test discarded |
| 3 | Treatment is a **tie on concrete golden defect fixtures** | **Moderate** | consistent across both judges, but a tie is also what an under-powered test returns |
| 4 | **Public-readability regression**, mechanism = orchestration narration | **High** | the only finding replicated in all four independent measurements *and* independently reproducible by regex without any model in the loop |
| 5 | Context cost is **workload-dependent, not uniformly lower** | **High** | direct token/cost measurement, no judge involved |
| 6 | No safety/permission/injection regression | **Moderate** | absence of evidence over 258 pairs; the injection fixture is a single easy case |

**Finding 4 is the only one we would defend hard.** It does not depend on a
judge: `evidence/narration-leak/` shows verbatim preambles, and the regex is in
`REPRODUCE_FINDING_4.md`. Findings 2 and 3 rest on noisy judges.

## 4. How to falsify each finding

Do these rather than believing us.

**Finding 1 (non-inferiority).** Falsified if, on a larger sample of
blocker-bearing fixtures, treatment P0/P1 recall is materially below control.
Our test had 69 pairs. Run the golden fixtures at higher repetition and check
whether the 88.4% vs 90.3% gap widens or vanishes.

**Finding 2 (wins on official evals).** Falsified if the win disappears when
ties are not discarded, when a third judge is used, or when the eval-set
assertions are scored by something other than the bundled substring checks.
The result leans on a mechanical fact you can check directly: control omitted a
merge decision in 162 runs vs treatment's 121, and omitted a QA Spec in 168 vs
110. **If you think that reflects the eval set rewarding the skill's own
output format rather than review quality, say so — that is a legitimate
objection and we cannot rule it out.**

**Finding 3 (tie on golden fixtures).** Falsified by more repetitions showing a
consistent direction. A tie here is weak evidence either way.

**Finding 4 (narration leak).** Falsified if the regex over-matches — e.g. if
it counts legitimate review prose. Read all eight examples in
`evidence/narration-leak/` and judge whether each preamble genuinely exposes
internal process. If ≥3 of 8 look like acceptable reviewer prose to you, our
55% figure is inflated and you should say so. Also check
`evidence/counterexamples/`: four runs of the same skill with no narration,
proving the skill *can* already do this correctly.

**Finding 5 (cost).** Falsified by showing our Stage 1/3 measurements were
confounded (e.g. different cache states). Cache-creation token medians are in
the report; re-measure if you doubt them.

**Finding 6 (no safety regression).** Falsified trivially by finding one
counterexample; we may simply have missed it. Search the raw outputs.

## 5. What we deliberately did NOT do

- **We did not change your skill.** Not one byte. The proposed fix in
  `PROPOSED_CHANGE_UNVALIDATED.md` is a hypothesis we could not test.
- **We did not fix a broken check in your favor.** Your bundled assertion
  `priority-confidence model is usable` fails any output containing both `[p1`
  and "non-blocking" — which your own `[P2 · Non-blocking]` label trips by
  construction. 0 of 17 Stage 1 failures were genuine. We left it alone and
  reported it, because editing a ground-truth check to make a variant look
  better is exactly the kind of thing that makes evaluations worthless. **You
  should probably fix it — but that is your call and it will change your
  historical numbers.**
- **We did not run cross-provider evaluation.** Anthropic-only credentials. So
  your Wave-3 "verifier from another model family" instruction was **never
  tested**. Any claim you make about it is currently unsupported.

## 6. Two problems in your harness you should treat as urgent

These are independent of the A/B result and, in our view, matter more.

1. **Your eval inputs leak the answers.** `reviewing-pull-requests/evals/files/*.json`
   embed the fixture's `expected` block (decision, priority, finding), and
   `import_swe_prbench.py` writes `human_review_comments` into runner-visible
   fixtures. The bundled `run_live_ab.py` copies these straight to both
   runners. Any past result produced with the unmodified bundled runner is
   contaminated. We stripped them; see `harness/run_ab_parallel.py`.
2. **Your grader will grade API error text as a review.** The bundled runner
   writes the CLI `result` field to `response.md` even when it is an error, and
   `grade_live_ab.py` scores it. We only caught this because a judge wrote "the
   output is a session-limit error message". 77 contaminated outputs and 41
   verdicts had to be discarded mid-run.

If you disagree that these are real, check the files — both are verifiable in
seconds and do not depend on any judgment of ours.

## 7. What a good response from you looks like

- the output of `verify_our_claims.py`
- your independent read of at least three paired samples, before our verdicts
- an explicit accept/reject/uncertain call on each of the six findings, with
  reasons
- at least one place where you think we are wrong, or an explicit statement
  that you tried to find one and could not, and what you checked
- a plan that changes the skill **only** where the evidence survived your
  scrutiny, with the re-validation you will run

If you conclude the skill should ship unchanged, say that. If you conclude our
evaluation is too weak to act on, say that too — with which specific weakness.

## 8. Files

| Path | What it is |
|---|---|
| `verify_our_claims.py` | recomputes our numbers from raw data; run first |
| `CRITIQUE_THIS_EVALUATION.md` | our own case against our own findings |
| `REPRODUCE_FINDING_4.md` | exact method + regex for the one strong finding |
| `PROPOSED_CHANGE_UNVALIDATED.md` | candidate fix, with reasons to reject it |
| `evidence/narration-leak/` | 8 verbatim treatment preambles exposing process |
| `evidence/counterexamples/` | 4 clean treatment preambles — a fix must not break these |
| `evidence/paired-samples/` | 6 full pairs **where the control won** |
| `artifacts/LIVE_AB_REPORT.md` | the full report |
| `artifacts/LIMITATIONS.md` | everything constraining interpretation |
| `artifacts/HUMAN_ADJUDICATION_QUEUE.md` | 127 pairs we could not resolve |
| `raw/` | verdicts, sealed A/B mappings, run manifests, per-stage stats |
| `harness/` | the runner, judge, and stats scripts, for re-running |
