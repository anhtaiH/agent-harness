# App Integrations

The intended post-install experience is simple: open Codex, Claude, or Cursor in the configured repo and describe the task. The agent should discover the harness, start or resume a task, and use MCP/tools without asking the human to run backend commands.

## What Setup Installs

Setup writes three kinds of integration state.

| Surface | Installed behavior | Mutation policy |
| --- | --- | --- |
| Codex | Managed user-instruction block plus a user MCP server entry | Existing instruction text is preserved; only the managed block is replaced on rerun |
| Claude | Managed user-memory block, tool-native MCP registration when `claude` is installed, plus ignored repo-local guidance | Existing user memory is preserved; project guidance is added to `.git/info/exclude` |
| Cursor | Ignored repo-local rule plus a user MCP server entry when no Cursor MCP config exists | Existing Cursor MCP config is skipped unless setup is run with `--force` |

Setup also writes adapter snippets under the runtime so a user can install manually if an app changes its config format.

## Safe Mutation Rules

- Managed edits are wrapped in `agent-harness:<workspace>:...` markers.
- Rerunning setup replaces only those managed blocks.
- Existing non-harness shims are skipped unless `--force` is passed.
- Existing Cursor MCP config is not merged unless `--force` is passed.
- Repo-local app files are added to `.git/info/exclude`; they should not appear in `git status`.
- `agent-harness uninstall --restore-adapters` removes managed blocks, managed local files, managed shims, and Claude MCP registration where possible.

## What The Human Does After Setup

Usually nothing in app settings. Use natural-language prompts:

```text
Use the agent harness for this repo. Start a task packet, inspect the checkout, and report what is ready for agentic work.
```

```text
Use the agent harness to implement ENG-123 in yolo mode. Work in a harness worktree, verify the change, run an independent review, and finish with evidence.
```

```text
Review PR 12345 quickly with the harness. Run the fast lane selection first, draft only high-confidence comments, and do not post to GitHub.
```

## If It Does Not Just Work

Run:

```bash
agent-harness where
agent-harness doctor
```

`where` shows the runtime, repo mapping, dashboard, adapter snippets, and installed app-adapter status. If an app cannot see MCP, paste the matching adapter snippet into that app's MCP settings or rerun setup with `--force` after reviewing what it will merge.

Use `--no-register` for a runtime-only install when testing the package or when a machine has highly customized app configuration.
