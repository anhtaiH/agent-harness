# App Integrations

The intended post-install experience: open Claude Code, Codex, Cursor, opencode, or pi in the configured repo and describe the task. The agent discovers the harness, starts or resumes a task, and uses MCP/CLI tools without asking the human to run backend commands — while the policy gates run in each tool's native hook system.

## What Setup Installs

| Surface | Instructions | MCP | Gates | Assets | Mutation policy |
| --- | --- | --- | --- | --- | --- |
| Claude Code | Managed block in `~/.claude/CLAUDE.md` + ignored repo-local `CLAUDE.local.md` | `claude mcp add --scope user` | Hooks merged into `~/.claude/settings.json` (PreToolUse, PostToolUse, UserPromptSubmit, Stop, SessionStart) + `permissions.deny` seeds | Skills → `~/.claude/skills/`, subagents → `~/.claude/agents/` | Managed blocks are marker-delimited; settings merges are metadata-tracked with backups; assets are sha-tracked and only removed on restore if unmodified |
| Codex CLI | Managed block in `~/.codex/AGENTS.md` (respects `AGENTS.override.md`) | Managed block in `~/.codex/config.toml` | Env-scrubbed `ah-codex` wrapper; pair with Codex `sandbox_mode`/`approval_policy` | Skills → `~/.codex/skills/agent-harness/` | Same managed-block + sha-tracked rules |
| Cursor | Ignored repo-local `.cursor/rules/agent-harness.mdc` | `~/.cursor/mcp.json` (existing config untouched unless `--force`) | `~/.cursor/hooks.json` bridge (beforeShellExecution, beforeMCPExecution) + `~/.cursor/cli-config.json` deny seeds | — | JSON merges are metadata-tracked with backups |
| opencode | Managed block in `~/.config/opencode/AGENTS.md` | `mcp` entry in `~/.config/opencode/opencode.json` (`.jsonc` users get a snippet instead) | Plugin at `~/.config/opencode/plugins/agent-harness.js` (`tool.execute.before`) | Skills → `~/.config/opencode/skills/` | Existing entries never replaced without `--force` |
| pi | Managed block in `~/.pi/agent/APPEND_SYSTEM.md` | — (pi is deliberately CLI-first; agents use the `harness` CLI) | Extension at `~/.pi/agent/extensions/agent-harness.ts` (blockable `tool_call`) | Skills → repo `.agents/skills/` (git-excluded) | Managed blocks + tracked files |
| Gemini CLI & others | — | Snippet: `<runtime>/state/adapter-snippets/gemini-mcp.json` | Shared CLI | — | Manual |

All five gate surfaces call the same policy engine (`runtime/hooks/pre-tool-policy.py`), so behavior is identical across tools and testable with one command: `agent-harness verify-gates`.

## Safe Mutation Rules

- Managed text edits are wrapped in `agent-harness:<workspace>:...` markers; reruns replace only those blocks.
- JSON config merges (Claude settings, Cursor hooks/cli-config, opencode.json, Cursor mcp.json) keep timestamped backups under `<runtime>/state/adapters/backups/` and restore metadata under `<runtime>/state/adapters/`.
- Copied assets (skills, subagents) record their sha256; restore deletes them only if unmodified, otherwise leaves them and reports why.
- Existing non-harness files/entries are skipped, never overwritten, unless `--force`.
- Repo-local files (`CLAUDE.local.md`, `.cursor/rules/agent-harness.mdc`, `.agents/skills/`) are added to `.git/info/exclude`, never tracked.
- `agent-harness uninstall --restore-adapters` reverses all of the above.

## What The Human Does After Setup

Usually nothing in app settings. Use natural-language prompts:

```text
Use the agent harness for this repo. Start a task packet, inspect the checkout, and report what is ready for agentic work.
```

```text
Use the agent harness to implement ENG-123 in yolo mode. Work in a harness worktree, verify the change, run an independent review, and finish with evidence.
```

## If It Does Not Just Work

```bash
agent-harness where          # what is installed, what was skipped and why
agent-harness doctor         # runtime + MCP health
agent-harness verify-gates   # are the guardrails actually firing
```

If an app cannot see MCP, paste the matching snippet from `<runtime>/state/adapter-snippets/` into that app's MCP settings, or rerun setup with `--force` after reviewing what it will merge. Use `--no-register` for a runtime-only install on machines with heavily customized app configuration.
