# Agent Harness

Agent Harness is a personal, local control plane for agentic engineering — a meta-harness you install once per machine, on top of the coding agents you already use. It gives Claude Code, Codex, Cursor, opencode, and pi the same task packets, worktrees, evidence gate, policy guardrails, memory inbox, draft-only PR review flow, and connector-write guardrails, without touching your work repo's tracked files.

It is built for engineers who cannot (or should not) add harness config to their employer's repo: everything lives in `~/.agent-harness/<workspace>/` plus small, reversible, marker-delimited edits to your own user-level tool config.

## Install (give this to your agent)

The install interface is a prompt. Paste this into whichever coding agent you trust with shell access:

```text
Read https://raw.githubusercontent.com/anhtaiH/agent-harness/main/INSTALL.md and follow it exactly to install the Agent Harness for the repo we are in. Use the deterministic setup script it names, then run doctor --json and verify-gates --json, and report both results plus which app adapters were installed or skipped. Do not claim success unless doctor and verify-gates both return ok:true. Finish by telling me the rollback command.
```

The agent is the interface; deterministic scripts do the work. [INSTALL.md](INSTALL.md) walks the agent through preflight, `setup --yes --json`, verification, a smoke task, and the rollback command.

### Install (human, direct)

```bash
npx --yes github:anhtaiH/agent-harness setup            # interactive
npx --yes github:anhtaiH/agent-harness setup --yes      # unattended
npx --yes github:anhtaiH/agent-harness setup --workspace my-product --yes
```

Setup detects the current git repo, creates a runtime under `~/.agent-harness/<workspace>/`, copies a self-contained source bundle, installs dependencies, creates shims, generates a repo profile, installs app adapters for the tools it finds, and runs `doctor`.

## What actually gets enforced

Guardrails here are wired into each tool's native hook/permission system — not just described in instructions — and `agent-harness verify-gates` proves they fire by piping canned payloads through every hook and asserting the decision:

| Gate | Behavior |
| --- | --- |
| Pre-tool policy | Denies credential/secret file access, `curl \| sh`-style remote code execution, secret exfiltration patterns, production-affecting commands (publish/deploy/merge/infra), protected-branch force pushes; asks before destructive local commands outside yolo mode |
| Connector-write gate | Denies GitHub/Jira/Confluence/Slack write tools unless a task-scoped `external_write_intent` exists |
| Prompt secret scan | Blocks prompts containing raw credentials before they reach model context |
| Stop / evidence gate | Blocks ending a session while the active task's evidence is missing or incomplete (loop-safe, TTL-bound, escapable by finishing the task) |
| Session start | Injects the active-task capsule so new sessions resume instead of restarting |
| Drift check | Throttled reminder when the tracked checkout changes during a task |

Run the proof any time:

```bash
agent-harness verify-gates
```

## Tool support

| Surface | Instructions | MCP | Policy gates | Skills | Subagents |
| --- | --- | --- | --- | --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` block + repo-local `CLAUDE.local.md` | `claude mcp add --scope user` | Hooks in `~/.claude/settings.json` (PreToolUse, UserPromptSubmit, Stop, SessionStart, PostToolUse) + `permissions.deny` seeds | `~/.claude/skills/` | `~/.claude/agents/` (reviewer, verifier, security) |
| Codex CLI | `~/.codex/AGENTS.md` block | `~/.codex/config.toml` block | Env-scrubbed `ah-codex` wrapper + sandbox guidance | `~/.codex/skills/agent-harness/` | via `agent_run` peer lanes |
| Cursor | repo-local `.cursor/rules/*.mdc` (git-excluded) | `~/.cursor/mcp.json` | `~/.cursor/hooks.json` (beforeShellExecution, beforeMCPExecution) + `cli-config.json` deny seeds | — | via `agent_run` peer lanes |
| opencode | `~/.config/opencode/AGENTS.md` block | `opencode.json` `mcp` entry | Plugin bridge (`tool.execute.before`) | `~/.config/opencode/skills/` | via `agent_run` peer lanes |
| pi | `~/.pi/agent/APPEND_SYSTEM.md` block | — (pi is CLI-first by design) | `tool_call` extension bridge | repo `.agents/skills/` (git-excluded) | via `agent_run` peer lanes |
| Gemini CLI / others | manual snippets under `<runtime>/state/adapter-snippets/` | snippet | shared CLI (`harness`) | — | — |

Every adapter edit is marker-delimited or sha/metadata-tracked; `agent-harness uninstall --restore-adapters` reverses all of it.

## First prompts

```text
Use the agent harness for this repo. Start a task packet, inspect the checkout, and report what is ready for agentic work.
```

```text
Use the agent harness to fix ENG-123 in yolo mode. Keep the implementation in a harness worktree, run verification, get an independent review, and finish with evidence.
```

```text
Review PR 12345 quickly with the harness. Draft only high-confidence comments and do not post to GitHub.
```

## Daily commands (humans)

```bash
agent-harness doctor          # health check: files, MCP self-test, leak scan
agent-harness verify-gates    # prove the guardrails fire
agent-harness where           # what is installed, where
agent-harness open            # dashboard
agent-harness examples        # prompt ideas
agent-harness upgrade         # refresh runtime from the package
agent-harness uninstall --restore-adapters
```

Agents should use MCP tools or the runtime backend themselves; humans should not need to type backend paths during normal work.

## Safety model

Runtime state is local by default. The generic repo ships no project knowledge, personal memory, task history, or connector-derived evidence, and `doctor` scans both source and runtime for leak patterns (`runtime/policy/leak-patterns.json`) and secret material (`runtime/policy/redaction-patterns.json`).

Hard stops in every mode: credential/secret reads, token exfiltration, remote-code piping, production-affecting actions without explicit task scope, automatic PR-review posting, and connector writes without a task-scoped intent. Yolo mode widens local shell autonomy only.

External org writes use task-scoped, TTL-bound write intents with connector-native auth — the harness never asks for raw token env vars.

## Learn more

- [Getting Started](docs/getting-started.md)
- [App Integrations](docs/app-integrations.md)
- [How It Works](docs/how-it-works.md)
- [Human-Agent Contract](docs/human-agent-contract.md)
- [Best Practices](docs/best-practices.md)
- [Security](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Research Notes](docs/research-notes.md)
- [Product Principles](docs/product-principles.md)

## Development

```bash
npm ci
npm test                      # setup, task/evidence flows, adapters, gates, restore
./bin/agent-harness verify-gates
```

CI runs the full suite on Ubuntu and macOS. The test suite exercises no-clone setup, runtime self-containment, profile generation, task/evidence flows, PR-review smoke paths, write intents, gate verification, adapter installs (Claude settings hooks, Cursor hooks, opencode, pi), and uninstall/restore.
