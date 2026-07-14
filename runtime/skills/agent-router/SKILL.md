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
5. Implement in the harness worktree with exactly one writer.
6. For yellow/red risk, run independent review lanes (harness-reviewer / harness-security subagents, or `agent_run` peer lanes) before finalizing.
7. For external org writes (GitHub/Jira/Confluence/Slack), create an `external_write_intent` first — the policy gate blocks connector writes without one.
8. Finish through evidence: `write_evidence` -> `evidence_doctor` -> `finish_task`.
