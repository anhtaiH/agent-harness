# Stage 4 — Attrition Incident and Recovery

Stage 4 (100 real historical PRs from SWE-PRBench, 200 runs) was the only stage in this
evaluation to suffer attrition. This records what happened, how it was diagnosed, and what was
done, because `LIVE_AB_PROTOCOL.md` requires failed runs to remain visible rather than be
quietly replaced.

## What happened

| Item | Value |
|---|---|
| Planned runs | 200 |
| Runs invalid on first execution | **51 (25.5 %)** |
| Error reason (all 51) | `nonzero_exit` |
| Timeouts | 0 |
| Split across variants | 26 `new_skill` / 25 `old_prompt` |
| Cases with **both** variants failed | 23 |
| Cases with one variant failed | 5 |
| Gradable pairs after failures | 72 of 100 |
| Judge verdicts written | 144 files, **all error stubs** |

## Diagnosis

The failure surface pointed away from anything experimental:

1. **All 51 failures landed in a four-minute window** — 09:13 (14), 09:14 (24), 09:15 (11),
   09:16 (2). A defect in inputs, prompts, or the skill would not cluster in time.
2. **Balanced across variants** (26 vs 25), so it cannot bias the A/B comparison.
3. **Evenly spread across all ten shards** (2–8 failures each).
4. **Not explained by input size** — median diff on failed cases 8.1 KB vs 9.2 KB on clean
   cases; the largest diff in the corpus (69 KB) ran fine.
5. **Not reproducible.** Re-executing a "fast-fail" case afterwards ran normally past 100 s
   instead of exiting at ~2.8 s.
6. **Earlier stages were untouched** — 0 invalid runs in 450 runs at 5-way concurrency.

The judge telemetry then gave the direct cause:

> `"You've hit your session limit · resets 11:50am (UTC)"`

An account-level usage limit. It ended the 51 in-flight runs and then caused **every** Stage 4
judge call to fail, which is why all 144 verdict files were `{"error": "no verdict written"}`.

The "both variants failed" pattern is a consequence, not a signal: the two variants of a case
run back-to-back inside the same shard, so a burst window catches both.

## Why this is an environment event, not a result

The limit is a property of the account running the evaluation, not of either prompt variant.
It struck a contiguous time window, hit both variants equally, and vanished on retry. Treating
these as review failures would be a measurement error, and reporting Stage 4 numbers computed
from the 72 surviving pairs while all judge verdicts were error stubs would have been worse —
the assembler correctly refused to produce metrics from them.

## Recovery

After confirming the limit had reset (a probe returned normally), the 51 invalid runs were
**re-executed individually** and Stage 4 was re-graded.

The retry re-runs the *same* command against the *same* already-generated `prompt.md`, `inputs/`,
and `runtime-skill/` directory, so a retried run differs from its original only in wall-clock
time. Retried records are flagged `retried: true` in `runs.jsonl` so attrition remains auditable
after recovery. Validity is re-evaluated with the shipped runner's own rules — successful exit,
no timeout, explicit non-empty response, not an error envelope, not a refusal.

Stage 4 was **not** re-run wholesale: the 149 runs that completed before the limit are kept
as-is, so no successful run was discarded or repeated.

### Recovery outcome

| Item | Value |
|---|---|
| Runs retried | 51 |
| Runs recovered | **51 (100 %)** |
| Shards fully recovered | 10 of 10 |
| Final valid runs | **200 / 200** |
| Final invalid runs | **0** |
| Final balance | 100 `old_prompt` / 100 `new_skill` |
| Final gradable pairs | **100 / 100** |

Every single retried run succeeded. A 100 % recovery rate on the same inputs, with the same
commands, is the strongest available confirmation that the original failures carried no
information about either variant: nothing about the input, the prompt, or the skill changed
between the failed attempt and the successful one — only the account's quota state.

Stage 4 therefore reports the **full 100-PR corpus** with zero attrition in the final dataset,
while the incident itself remains recorded here.

## Reporting rule applied

Stage 4 results are reported with:

- the original 51-run attrition stated up front, with its cause
- the count of retried runs and how many recovered
- the final gradable-pair count against the 100 planned
- latency and cost statistics computed **excluding** retried runs where the retry ran under
  materially different load, since the original stage ran at 10-way concurrency and the retry at
  5-way

## Harness note for future runs

Two changes would make this class of event cheaper to survive:

1. `run_live_ab.py` treats a usage-limit exit as `nonzero_exit`, indistinguishable from a real
   agent failure. A distinct `quota_exhausted` reason — detectable from the CLI's own
   `terminal_reason: api_error` plus the limit message — would let a stage pause and resume
   instead of burning through the remaining cases.
2. `grade_live_ab.py` writes a verdict file even when the judge produced nothing, so a fully
   failed judging pass looks superficially complete. The stub is honest, but the grader should
   surface a non-zero "judge failed" count in its summary rather than leaving it to downstream
   assembly to notice.
