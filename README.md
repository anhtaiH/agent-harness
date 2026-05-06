# Agent Harness

Agent Harness is a local control plane for agentic engineering. It gives Codex, Claude, Cursor, and similar tools the same task packets, worktrees, evidence gate, memory inbox, PR-review flow, peer-review loop, and connector-write guardrails.

The user-facing workflow is natural language. You ask an agent to do work; the agent starts or resumes a harness task, uses the MCP/tools itself, and finishes with evidence.

## Install

Run this from inside the repo you want agents to work on:

```bash
npx --yes github:anhtaiH/agent-harness setup
```

Setup detects the current git repo, chooses a workspace name, creates a runtime under `~/.agent-harness/<workspace>/`, copies a self-contained source bundle into that runtime, installs runtime dependencies, creates safe shims, generates a local profile from the repo, and runs a doctor check.

For unattended setup:

```bash
npx --yes github:anhtaiH/agent-harness setup --yes
```

For a named workspace:

```bash
npx --yes github:anhtaiH/agent-harness setup --workspace my-product --yes
```

## First Prompt

After setup, open Codex, Claude, or Cursor and try:

```text
Use the agent harness for this repo. Start a task packet, inspect the checkout, and report what is ready for agentic work.
```

For real work:

```text
Use the agent harness to fix ENG-123 in yolo mode. Keep the implementation in a harness worktree, run verification, get an independent review, and finish with evidence.
```

For PR review:

```text
Review PR 12345 quickly with the harness. Draft only high-confidence comments and do not post to GitHub.
```

## Daily Commands

These are for humans when they want status or troubleshooting:

```bash
agent-harness doctor
agent-harness where
agent-harness open
agent-harness examples
agent-harness upgrade
agent-harness uninstall --restore-adapters
```

Agents should use MCP tools or the runtime backend themselves. Humans should not need to type backend paths during normal work.

## What It Does

- Creates source-backed task packets before non-trivial work.
- Uses harness-managed worktrees for implementation.
- Requires evidence before completion.
- Runs independent review lanes for higher-risk work.
- Builds PR review packets, classifies risk, and drafts private comments only.
- Keeps memory local as source-backed candidates until a human promotes it.
- Allows yolo mode for broad local shell autonomy while keeping hard stops for secrets and production-affecting actions.
- Uses task-scoped connector-native write intents for Confluence, Jira, Slack, and GitHub maintenance writes.

## Safety Model

Runtime state is local by default. The generic repo does not ship project-specific knowledge, personal memory, task history, worktrees, metrics, generated caches, or connector-derived evidence.

Hard stops remain:

- credential and secret reads
- token exfiltration patterns
- production-affecting actions without explicit task scope
- automatic PR review comment posting from the PR-review flow

External org writes are allowed through task-scoped connector-native tools. The harness does not require raw token environment variables.

## Learn More

- [Getting Started](docs/getting-started.md)
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
npm test
```

The test suite exercises no-clone setup, runtime self-containment, profile generation, task/evidence flows, PR-review smoke paths, write intents, eval smoke checks, and uninstall dry runs.
