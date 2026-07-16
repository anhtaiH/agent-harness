---
name: task-packet
description: Create or refine an agent-harness task packet before non-trivial engineering work. Use when starting implementation, a bug fix, a refactor, or an investigation that will take more than a few steps - before editing code. Creates scoped goals, risk level, verification plan, and stop conditions.
---

# Task Packet

Start non-trivial work by creating a task packet (MCP `start_task`, or `harness start <repo> --prompt "..."`).

1. State the goal in one testable sentence.
2. Record repo, worktree, risk (green/yellow/red), and mode (plan/run/yolo).
3. Define scope: allowed areas, forbidden areas, non-goals.
4. Define verification: the exact commands that must pass, plus manual checks.
5. Keep stop conditions: secrets required, production actions, scope exhausted, repeated failures.
6. For yellow/red risk, write the sprint contract (`contract.md`) before any edit.

Keep the packet source-backed: cite files, tests, and docs you actually read. Never store secrets or raw tokens in task artifacts.
