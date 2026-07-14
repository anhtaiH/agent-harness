---
name: orchestrator
description: Run a harness task autonomously end-to-end with the role-based conductor. Use when the user wants work completed without steering - "just do it", "run it autonomously", a multi-step feature/fix/refactor - after a task packet exists. Plans role steps, executes with gates and fix loops, finishes through evidence or reports blocked.
---

# Orchestrator

Drive the deterministic conductor instead of doing every step yourself:

1. Ensure a task packet exists (`start_task`); the packet's Scope and Verification sections steer every role.
2. `orchestrate_plan` (MCP) or `harness orchestrate plan <task>` — a planner agent decomposes the task into researcher/worker/qa/reviewer/security/synthesizer steps; unparseable plans fall back to a safe default.
3. `orchestrate_run` — the conductor executes: parallel read-only lanes, one writer at a time, QA must report PASS, reviewer must APPROVE, security must find nothing blocking; failed gates bounce the worker through a bounded fix loop with the findings attached.
4. Read the final JSON: `finished: true` means evidence passed the doctor and the task closed; `blocked` lists the steps needing a human decision — report them with the ledger paths, never force-finish.
5. `orchestrate_status` shows the plan state and recent ledger events at any time; reruns resume from the ledger (crash-safe).

Budgets (`--max-iterations`, `--max-attempts`, `--step-timeout`) keep runs bounded; every role agent still runs under the policy gates.
