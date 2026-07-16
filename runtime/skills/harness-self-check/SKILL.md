---
name: harness-self-check
description: Run and interpret agent-harness health checks. Use after setup or upgrade, after editing adapters or hooks, when MCP tools are missing, or when gates behave unexpectedly. Covers doctor, self_check, and verify-gates.
---

# Harness Self Check

Three checks, in escalating depth:

1. `doctor` (CLI) / `self_check` (MCP): runtime files present and executable, config valid, MCP server self-test passes, no sensitive material in artifacts, no leak-pattern hits in source.
2. `harness verify-gates`: proves the guardrails fire — pipes canned payloads (secret reads, curl|bash, force-push, connector writes without intent, stop-without-evidence) through every hook and asserts allow/ask/deny. All cases must pass.
3. `agent-harness where`: shows what is installed where (runtime, adapters, hooks wiring, snippets) when an app cannot see the harness.

Fix every failure before reporting completion: missing files -> rerun setup/upgrade; MCP failures -> check node + dependency install; gate failures -> the hooks or policy files were modified, restore or fix them.
