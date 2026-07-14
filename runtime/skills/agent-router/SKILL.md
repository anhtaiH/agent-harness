---
name: agent-router
description: Route natural-language engineering requests into the local agent harness. Use when the user describes non-trivial work in a configured repo (implement, fix, refactor, investigate, review) without naming harness mechanics - infer repo, risk, and mode, then drive the harness yourself instead of asking the user for backend commands.
---

# Agent Router

When the user describes engineering work in a harness-configured repo:

1. Never ask the user to run backend paths or MCP commands; you drive the harness.
2. If harness MCP tools are visible, call them; otherwise use the runtime CLI (`harness`, `agent-harness`, or `ah`).
3. Start (`start_task`) or resume (`resume_task` / session-start capsule) a task packet first.
4. Infer repo, kind, risk, and mode from the request; default mode is `run`, use `yolo` only when the user grants it.
5. If the user wants the work done end-to-end without steering ("just handle it", "run it autonomously", multi-step feature/fix), hand off to the conductor: `orchestrate_plan` then `orchestrate_run` — it manages roles, gates, fix loops, and evidence itself. Report its final JSON (finished vs blocked) back to the user.
6. Otherwise implement in the harness worktree with exactly one writer.
7. For yellow/red risk, run independent review lanes (harness-reviewer / harness-security subagents, or `agent_run` peer lanes) before finalizing.
8. For external org writes (GitHub/Jira/Confluence/Slack), create an `external_write_intent` first — the policy gate blocks connector writes without one.
9. Finish through evidence: `write_evidence` -> `evidence_doctor` -> `finish_task`.
