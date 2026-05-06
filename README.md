# Agent Harness

An opt-in local harness for agentic engineering work across Codex, Claude, Cursor, and similar tools.

The harness separates reusable source from mutable per-user runtime:

- source repo: this checkout
- runtime: `~/.agent-harness/<workspace>/`
- workspace profile: generated locally from the engineer's repo checkout and available context

The core gives agents a task packet, worktree, MCP control plane, evidence gate, memory inbox, peer-review loop, PR-review shell, write-intent gate, and local metrics. Project-specific knowledge is plugged in as a generated profile instead of being hardcoded into the generic harness.

## Install

```bash
pnpm install # or npm install
./bin/agent-harness install --workspace webflow --repo /path/to/webflow-checkout
```

This creates `~/.agent-harness/webflow`, installs runtime files, writes a local config, generates a profile from the supplied checkout, and runs a self-check. It does not copy task history, worktrees, metrics, private memory, or generated caches from another user.

If that runtime path already contains an unmanaged local harness, install refuses to overwrite it. Use `--runtime-root /tmp/agent-harness-webflow-pilot` for a safe pilot, or `--force` only after backing up local state.

For a dry install into a temporary runtime:

```bash
./bin/agent-harness install --workspace demo --repo /path/to/repo --runtime-root /tmp/agent-harness-demo --no-register
```

## Daily Use

Agents should call the MCP tools or the runtime backend themselves. The user-facing workflow is natural language:

- `Use the harness to fix ENG-123 in yolo mode.`
- `Review PR 12345 quickly and draft only high-confidence comments.`
- `Write a Confluence update for this task using connector-native auth.`
- `Resume my latest harness task.`

Manual backend commands remain available for debugging:

```bash
~/.agent-harness/webflow/bin/harness status
~/.agent-harness/webflow/bin/harness self-check
```

## Profile Model

The source repo is generic. Project knowledge is generated at install or refresh time from the local checkout:

- `AGENTS.md`
- CODEOWNERS
- project agent docs/rules when present
- git metadata
- optional connector evidence gathered during a task

Stable lessons stay local as source-backed memory candidates until a human promotes them into the project-owned agent docs.

## Safety Model

- Default tasks use conservative guardrails.
- Yolo mode is available per task and allows broad local shell autonomy in the active task/worktree.
- Hard stops remain for sensitive file reads, token exfiltration, production-affecting actions, and unsafe PR-review posting.
- Confluence, Jira, Slack, and GitHub maintenance writes use task-scoped connector-native write intents. The harness does not require raw token env vars.

## Test

```bash
./tests/run.sh
```
