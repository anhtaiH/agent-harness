---
name: harness-self-check
description: Run and interpret the local agent harness self-check.
---

# Harness Self Check

Run this after harness changes or adapter changes.

- Prefer MCP `self_check`.
- Fallback to the runtime backend `bin/harness self-check`.
- Fix missing runtime files, failed MCP self-test, source leak findings, or sensitive artifact findings before reporting completion.
