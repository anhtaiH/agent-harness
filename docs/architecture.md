# Architecture

The harness has three layers:

1. Source repo: generic reusable CLI, runtime templates, MCP server, hooks, skills, tests, and docs.
2. Runtime: per-user mutable state under `~/.agent-harness/<workspace>/`.
3. Generated profile: source-backed project context produced from the engineer's local checkout.

Runtime state is intentionally excluded from the source repo. Tasks, worktrees, metrics, memory, profiles, and connector-derived evidence stay local.

## Core Surfaces

- CLI: `bin/agent-harness`
- Runtime backend: `<runtime>/bin/harness`
- MCP server: `<runtime>/mcp/server.mjs`
- Agent wrappers: `<runtime>/bin/ah-codex`, `<runtime>/bin/ah-claude`, `<runtime>/bin/ah-cursor`

## Profile API

A generated profile includes:

- `profile.json`
- `policy.json`
- `risk-rules.json`
- `source-manifest.json`
- `specialists/`

Profiles are source-backed. They can be regenerated without losing tasks or evidence.

For the product-facing lifecycle and diagrams, see [How It Works](how-it-works.md).
