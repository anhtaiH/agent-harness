# Getting Started

## 1. Run Setup

From the repo you want agents to work on:

```bash
npx --yes github:anhtaiH/agent-harness setup
```

Use `--yes` for unattended setup. Use `--workspace <name>` when one machine has multiple projects.

Setup creates a local runtime, detects installed tools, installs managed app adapters when safe, writes adapter snippets, installs shims, generates a local profile, and runs `doctor`.

After a successful setup, the normal next step is to open Codex, Claude, or Cursor in the repo and ask for work in natural language. You should not need to paste runtime paths into the agent.

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
agent-harness where
agent-harness open
```

`where` shows the runtime, source bundle, configured repos, dashboard, adapter snippets, and installed app adapters. `open` prints the dashboard path or opens it with `--browser`.

## 4. Upgrade Or Remove

```bash
agent-harness upgrade
agent-harness uninstall --restore-adapters
```

Uninstall removes the local runtime, managed shims, and managed app-adapter blocks. It does not edit tracked project files.
