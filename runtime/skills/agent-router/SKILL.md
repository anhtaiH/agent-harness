---
name: agent-router
description: Route natural-language engineering work into the local agent harness automatically.
---

# Agent Router

Use this whenever the user describes non-trivial work in Codex, Claude, Cursor, or a compatible agent surface.

1. Do not ask the user to run backend paths.
2. If MCP tools are visible, call them directly.
3. Start or resume a harness task.
4. Infer repo, task kind, risk, and mode.
5. For implementation, use the harness worktree and keep one writer.
6. For risky work, run peer review lanes before final evidence.
7. For external org writes, create an `external_write_intent` before connector-native writes.
8. Finish through evidence and `finish_task`.
