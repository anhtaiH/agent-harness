---
name: evidence-gate
description: Produce and validate final task evidence before claiming completion. Use when a harness task is about to finish, when the user asks "are you done", or when the Stop gate blocks with missing/incomplete evidence. Completion without passing evidence_doctor is not completion.
---

# Evidence Gate

Before claiming any harness task is done:

1. Positive proof: the command or inspection that shows the new behavior works. Paste real output, not summaries.
2. Negative proof: the regression or failure-mode check you ran (or explicitly considered) and its result.
3. Commands run: the honest list, including failures.
4. Skipped checks: what you did not run, why, and the residual risk.
5. Diff risk notes: what could break and the mitigation.
6. Memory candidates: only durable, source-backed lessons.

Then run `evidence_doctor` (MCP) or `harness evidence doctor <task-id>`; fix every failure it reports, and only then call `finish_task`. If the Stop gate blocked you, this is the checklist it is enforcing.
