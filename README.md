# Agent Harness

Agent Harness is a portable, local control plane for agentic engineering — a meta-harness you install once per machine, on top of the coding agents you already use. It gives Claude Code, Codex, Cursor, opencode, and pi the same task packets, worktrees, evidence gate, policy guardrails, memory inbox, draft-only PR review flow, and connector-write guardrails, without touching your work repo's tracked files.

It is built for engineers who cannot (or should not) add harness config to their employer's repo: everything lives in `~/.agent-harness/<workspace>/` plus small, reversible, marker-delimited edits to your own user-level tool config.

It is **not** an agent and not a service: it runs no models, hosts nothing, and only wraps the coding agents you already run.

**Mental model.** You install once per machine. The **source repo** (this repo) is copied into a **runtime** (`~/.agent-harness/<workspace>/`) that holds all mutable state (tasks, evidence, memory, metrics). **Adapters** are small reversible edits telling each coding tool the runtime exists. **Gates** are hook scripts in the runtime that every tool calls (proven by `verify-gates`). **Orchestration** drives multi-role runs over a task. Layers: [docs/architecture.md](docs/architecture.md); diagrams: [docs/how-it-works.md](docs/how-it-works.md).

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

Setup detects the current git repo and platform, creates a runtime under `~/.agent-harness/<workspace>/`, installs the credential-free engineering toolchain, copies a self-contained source bundle, creates shims, generates a repo profile, installs app adapters for the tools it finds, and runs `doctor`. Use `setup --dry-run --json` to inspect every package action, or `--toolchain none` to opt out.

The full profile includes Git, ripgrep, ugrep, fd, ast-grep, jq, yq, GitHub CLI, uv, rtk, pinned Semble, Serena, and Headroom. Context7 uses its unauthenticated endpoint. Playwright is documented but stays lazy until browser work needs it. Package-manager installs are preferred; the small fallback set uses pinned packages or checksum-verified release archives.

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

## Autonomous orchestration

For work you want done end-to-end rather than steered, the harness ships a deterministic conductor in the shape of OpenAI's Symphony spec and Gas Town-style role fleets, with Sol-led dynamic decomposition:

```bash
harness start --prompt "Fix ENG-123" --risk yellow
harness orchestrate run latest
```

A planner agent decomposes the packet into role steps (researcher → worker → QA → reviewer [+ security on risky tasks] → synthesizer); the conductor executes them from a file-based ledger with hard gates between transitions — QA must report `PASS`, the reviewer must `APPROVE`, security must find nothing blocking — bounded fix loops on failure, parallel read-only lanes, one writer at a time, and a crash-safe resume. Codex runs use recorded role-aware Sol/Terra/Luna routes and escalate retries to Sol; other peer clients are unchanged. Success ends in doctor-validated evidence and `finish_task`; exhausted budgets end `blocked` with a report instead of a forced finish. See [docs/orchestration.md](docs/orchestration.md).

## Tool support

| Surface | Instructions | MCP | Policy gates | Skills | Subagents |
| --- | --- | --- | --- | --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` block + repo-local `CLAUDE.local.md` | `claude mcp add --scope user` | Hooks in `~/.claude/settings.json` (PreToolUse, UserPromptSubmit, Stop, SessionStart, PostToolUse) + `permissions.deny` seeds | `~/.claude/skills/` | `~/.claude/agents/` (reviewer, verifier, security) |
| Codex CLI | `~/.codex/AGENTS.md` block | `~/.codex/config.toml` block | Env-scrubbed `ah-codex` wrapper + sandbox guidance | `~/.codex/skills/agent-harness/` | via `agent_run` peer lanes |
| Cursor | global `~/.cursor/rules/agent-harness.mdc` | `~/.cursor/mcp.json` | one `preToolUse` bridge in `~/.cursor/hooks.json`; CLI permissions remain user-owned | — | via `agent_run` peer lanes |
| opencode | `~/.config/opencode/AGENTS.md` block | `opencode.json` `mcp` entry | Plugin bridge (`tool.execute.before`) | `~/.config/opencode/skills/` | via `agent_run` peer lanes |
| pi | `~/.pi/agent/APPEND_SYSTEM.md` block | — (pi is CLI-first by design) | `tool_call` extension bridge | repo `.agents/skills/` (git-excluded) | via `agent_run` peer lanes |
| Gemini CLI / others | manual snippets under `<runtime>/state/adapter-snippets/` | snippet | shared CLI (`harness`) | — | — |

Every adapter edit is marker-delimited or sha/metadata-tracked; `agent-harness uninstall` reverses all of it. Tools that setup installed are retained by default; `agent-harness uninstall --remove-owned-tools` removes only receipt-owned tools.

Harness MCP starts in the nine-tool `compact` lifecycle/orchestration profile. Set `AGENT_HARNESS_MCP_PROFILE=legacy` on the Harness server only when the full legacy surface is needed; the measured schema-size gate requires at least a 60% reduction.

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
agent-harness doctor          # health check: files, MCP self-test, leak scan, stale-task/size warnings
agent-harness verify-gates    # prove the guardrails fire
agent-harness where           # what is installed, where
agent-harness retro           # friction report: forced finishes, top gate denials, recurring failures
agent-harness clean           # prune old finished tasks/backups under a retention policy (--dry-run first)
agent-harness open            # dashboard
agent-harness examples        # prompt ideas
agent-harness upgrade         # refresh runtime + re-sync adapters from the package
agent-harness uninstall       # removes runtime and restores adapters by default (--keep-adapters to opt out)
agent-harness uninstall --remove-owned-tools # also remove only receipt-owned toolchain installs
```

Agents should use MCP tools or the runtime backend themselves; humans should not need to type backend paths during normal work.

## Safety model

Runtime state is local by default. The generic repo ships no project knowledge, personal memory, task history, or connector-derived evidence, and `doctor` scans both source and runtime for leak patterns (`runtime/policy/leak-patterns.json`) and secret material (`runtime/policy/redaction-patterns.json`).

Hard stops in every mode: credential/secret reads, token exfiltration, remote-code piping, production-affecting actions without explicit task scope, automatic PR-review posting, and connector writes without a task-scoped intent. Yolo mode widens local shell autonomy only.

External org writes use task-scoped, TTL-bound write intents with connector-native auth — the harness never asks for raw token env vars.

## Learn more

- [Getting Started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [Orchestration](docs/orchestration.md)
- [App Integrations](docs/app-integrations.md)
- [How It Works](docs/how-it-works.md)
- [Human-Agent Contract](docs/human-agent-contract.md)
- [Best Practices](docs/best-practices.md)
- [Security](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Research Notes](docs/research-notes.md)
- [Product Principles](docs/product-principles.md)

## Development

Local verification is the release gate; CI (when available) is best-effort duplication, never the authority.

```bash
npm ci
npm test                      # setup, task/evidence flows, adapters, gates, orchestration, restore
npm run benchmark:mcp         # prove compact MCP schema bytes are >=60% below legacy
npm run preflight             # the full local gate: syntax checks, verify-gates,
                              # the suite from a fresh clone of HEAD, and a second
                              # suite run under a simulated macOS TMPDIR
./bin/agent-harness verify-gates
```

The test suite exercises no-clone setup, runtime self-containment, profile generation, task/evidence flows, PR-review smoke paths, write intents, gate verification, adapter installs (Claude settings hooks, Cursor hooks, opencode, pi), orchestration (dynamic plans, fix loops, bounded blocking), and uninstall/restore. Run `npm run preflight` before merging anything.
