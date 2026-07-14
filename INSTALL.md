# Agent Harness — Agent Install Instructions

These instructions are written for a coding agent (Claude Code, Codex, Cursor, opencode, pi, or similar) with permission to run shell commands. A human gave you this file because they want the Agent Harness installed for the repo they are working in. Follow the steps exactly; every step is deterministic and idempotent, and the scripts do the real work — do not improvise file edits that the setup script already performs.

## What you are installing

A local, per-user control plane under `~/.agent-harness/<workspace>/` that gives coding agents shared task packets, an evidence gate, policy hooks (secret/exfiltration/production guards), draft-only PR review, and an MCP server. It does not modify tracked files in the repo (repo-local adapter files are added to `.git/info/exclude`), and every user-level config edit is marker-delimited or metadata-tracked so `uninstall --restore-adapters` can undo it.

## Preflight (read-only)

1. Confirm you are inside the target git repo: `git rev-parse --show-toplevel`. If not, ask the human which repo to install for.
2. Confirm requirements: `node --version` (>= 20), `npm --version`, `python3 --version` (>= 3.10), `git --version`.
3. If `~/.agent-harness/` already contains a runtime for this workspace, prefer `agent-harness upgrade` over a fresh setup, or rerun setup (it is idempotent for managed state).

## Install (deterministic)

Run from the repo root:

```bash
npx --yes github:anhtaiH/agent-harness setup --yes --json
```

Notes:
- The `--json` result is your ground truth. Do not claim success unless `"ok": true`.
- If dependency install fails, the JSON includes `fix` and `retry` fields; follow them (`--skip-deps` is a degraded CLI-only fallback — report it as such).
- Setup auto-detects installed tools (Claude Code, Codex, Cursor, opencode, pi) and only writes adapters for the ones present. It never overwrites unmanaged user config; conflicts are reported as `skipped` with a reason and a manual snippet under `<runtime>/state/adapter-snippets/`.

## Verify (required — this is your evidence)

Run all three and capture output:

```bash
agent-harness doctor --json
agent-harness verify-gates --json
agent-harness where --json
```

If the shims are not on PATH yet, use the absolute runtime backend printed by setup (`<runtime>/bin/harness doctor --json`, etc.).

Success criteria you must confirm before reporting done:
1. `doctor` returns `"ok": true` (MCP self-test passed, runtime files executable, no leak/sensitive findings).
2. `verify-gates` returns `"ok": true` with every case passed — this proves the guardrails actually fire (secret reads denied, `curl | sh` denied, force-push to main denied, stop-without-evidence blocked, benign commands allowed).
3. `where` lists the adapters that were installed for the tools present on this machine.

## Smoke test (recommended)

Start and finish one task end-to-end:

```bash
agent-harness start --prompt "Harness install smoke test" --task-id install-smoke --risk green --mode run --json
agent-harness evidence write install-smoke --summary "Installed and verified the agent harness." --positive-proof "doctor + verify-gates JSON ok:true" --positive-result PASS --negative-proof "verify-gates deny cases all denied" --negative-result PASS --commands-run "setup, doctor, verify-gates" --json
agent-harness evidence doctor install-smoke --json
agent-harness finish install-smoke --json
```

## Report back to the human

Summarize: workspace name, runtime path, which tool adapters were installed/skipped (and why), doctor result, verify-gates pass count, and the one prompt to try next (setup printed it as `next_prompt`). Include the exact rollback command below.

## Rollback

```bash
agent-harness uninstall --restore-adapters
```

This removes the runtime, managed shims, managed instruction blocks, hook registrations, installed skills/subagents (only if unmodified), and MCP registrations, restoring prior user config. If anything reports `"restored": false`, show the human the listed path and reason.
