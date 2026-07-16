# Getting Started

## 1. Install

The recommended path: let your coding agent install it. Paste into Claude Code, Codex, Cursor, opencode, or pi (a session with shell access):

```text
Read https://raw.githubusercontent.com/anhtaiH/agent-harness/main/INSTALL.md and follow it exactly to install the Agent Harness for the repo we are in. Report doctor --json and verify-gates --json results when done.
```

Or run it yourself from the repo you want agents to work on:

```bash
npx --yes github:anhtaiH/agent-harness setup
```

Use `--yes` for unattended setup. Use `--workspace <name>` when one machine has multiple projects.

Setup creates a local runtime, detects installed tools (Claude Code, Codex, Cursor, opencode, pi), wires policy gates into each tool's native hook system, installs skills/subagents where supported, registers MCP, installs shims, generates a local profile, and runs `doctor`.

After a successful setup, open your agent in the repo and ask for work in natural language. You should not need to paste runtime paths into the agent.

## 2. Ask An Agent

Start with a simple inspection prompt:

```text
Use the agent harness for this repo. Start a task packet, inspect the checkout, and report what is ready for agentic work.
```

Then use normal task prompts:

```text
Use the agent harness to implement ENG-123. Work in a harness worktree, verify the change, and finish with evidence.
```

```text
Review PR 12345 with the harness. Run the fast path first, draft only high-confidence comments, and do not post to GitHub.
```

```text
Resume my latest harness task and tell me the next recommended action.
```

## 3. Check Health

```bash
agent-harness doctor
agent-harness verify-gates
agent-harness where
agent-harness open
```

`doctor` checks files, config, and the MCP server. `verify-gates` proves the guardrails fire (canned secret reads, `curl | sh`, force pushes, and stop-without-evidence payloads must come back denied). `where` shows the runtime, source bundle, configured repos, dashboard, adapter snippets, and installed app adapters. `open` prints the dashboard path or opens it with `--browser`.

## 4. Upgrade Or Remove

```bash
agent-harness upgrade
agent-harness uninstall --restore-adapters
```

Uninstall removes the local runtime, managed shims, and managed app-adapter blocks. It does not edit tracked project files.
