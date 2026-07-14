# Architecture

The harness has three layers:

1. Source repo: generic reusable CLI, runtime templates, policy engine hooks, MCP server, skills, subagents, tests, and docs.
2. Runtime: per-user mutable state under `~/.agent-harness/<workspace>/`.
3. Generated profile: source-backed project context produced from the engineer's local checkout.

Runtime state is intentionally excluded from the source repo. Tasks, worktrees, metrics, memory, profiles, and connector-derived evidence stay local.

## Core surfaces

- CLI: `bin/agent-harness` (and the installed backend `<runtime>/bin/harness`)
- MCP server: `<runtime>/mcp/server.mjs` (26 tools; control plane, not a generic shell)
- Policy engine: `<runtime>/hooks/pre-tool-policy.py` — single decision core for every tool surface
- Gate bridges: Claude settings hooks (direct), `<runtime>/hooks/cursor-bridge.py`, `<runtime>/mcp/opencode-plugin.mjs` (rendered to opencode's plugins dir), `<runtime>/mcp/pi-extension.ts` (rendered to pi's extensions dir)
- Agent wrappers: `<runtime>/bin/ah-codex`, `ah-claude`, `ah-cursor` (env scrub + task binding for headless peer lanes)
- Subagents: `<runtime>/agents/*.md` (installed to `~/.claude/agents/`; other tools reach the same lanes via `agent_run`)
- Skills: `<runtime>/skills/*/SKILL.md` (installed to `~/.claude/skills/`, `~/.codex/skills/agent-harness/`, `~/.config/opencode/skills/`, repo `.agents/skills/`)

## State model

- `config.json` — workspace, repos, MCP identity
- `tasks/<task-id>/` — packet, progress, contract, evidence, reviews, pr-review, external-writes
- `state/active-tasks.json` — repo path → active task (drives the Stop gate and session-start capsule; 24h TTL)
- `state/adapters/` — restore metadata + timestamped backups for every user-level edit
- `profiles/<workspace>/` — profile.json, policy.json, risk-rules.json, source-manifest.json
- `memory/` — inbox candidates, claims/failures JSONL, reports
- `evals/results/` — eval + gate-run JSONL
- `metrics/` — run and PR-review JSONL

## Verification chain

`doctor` (files, config, MCP self-test, leak/sensitive scans) → `verify-gates` (behavioral proof: canned payloads through every hook, asserted allow/ask/deny) → `eval run` (templates + MCP + gates, recorded to JSONL). The same checks run in CI on Ubuntu and macOS.

For the product-facing lifecycle and diagrams, see [How It Works](how-it-works.md).
