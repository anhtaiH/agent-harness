# Agent Harness — Agent Install Instructions

These instructions are written for a coding agent (Claude Code, Codex, Cursor, opencode, pi, or similar) with permission to run shell commands. A human gave you this file because they want the Agent Harness installed for the repo they are working in. Follow the steps exactly; every step is deterministic and idempotent, and the scripts do the real work — do not improvise file edits that the setup script already performs.

## What you are installing

A local, per-user control plane under `~/.agent-harness/<workspace>/` that gives coding agents shared task packets, an evidence gate, policy hooks, draft-only PR review, a compact MCP server, and a portable credential-free engineering toolchain. It does not modify tracked files in the repo, and every user-level config edit is marker-delimited or metadata-tracked so `uninstall` can undo it.

## Preflight (read-only)

1. Confirm you are inside the target git repo: `git rev-parse --show-toplevel`. If not, ask the human which repo to install for.
2. Confirm bootstrap requirements: `node --version` (>= 20), `npm --version`, `python3 --version` (>= 3.10), `git --version`.
3. If `~/.agent-harness/` already contains a runtime for this workspace, use the versioned `upgrade` command below; the installed shim can replay its current version but cannot acquire a newer release itself.
4. Run `env npm_config_ignore_scripts=true npx --yes github:anhtaiH/agent-harness#v0.3.0 setup --dry-run --json` and inspect the package-manager, pinned-package, and checksum-verified fallback actions. Do not replace these with remote-code piping.

## Install (deterministic)

Run from the repo root:

```bash
env npm_config_ignore_scripts=true npx --yes github:anhtaiH/agent-harness#v0.3.0 setup --yes --json
```

Notes:
- The `--json` result is your ground truth. Do not claim success unless `"ok": true`.
- The default `--toolchain full` installs Git, ripgrep, ugrep, fd, ast-grep, jq, yq, GitHub CLI, uv, rtk, pinned Semble/Serena/Headroom, and credential-free Context7 configuration. Use `--toolchain none` only when the human explicitly wants to retain their own toolchain.
- Package clients receive a minimal credential-free environment. npm lifecycle scripts and automatic Python downloads are disabled; Python tools are exact-version/time-bounded, wheel-only except Serena's `proxy-tools` dependency, whose exact source URL and SHA-256 are pinned in the shipped override.
- Playwright stays lazy to avoid permanent MCP context. For browser work, run `agent-harness playwright -- <playwright-mcp args>`; Harness fetches `@playwright/mcp@0.0.79`, verifies its pinned SHA-512, and only then executes the local tarball with npm lifecycle scripts disabled.
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
1. `doctor` returns `"ok": true` **and** `"warnings": []`. A warning like "MCP self-test skipped" or "node unavailable" means the install is degraded (CLI-only) — report that honestly, do not claim a full install.
2. `verify-gates` returns `"ok": true` with every case passed — this proves the guardrails actually fire (secret reads denied, `curl | sh` denied, force-push to main denied, stop-without-evidence blocked, benign commands allowed).
3. `where` lists the adapters and toolchain receipt, with no missing full-profile tools.

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
agent-harness uninstall
```

This removes the runtime, managed shims, managed instruction blocks, hook registrations, installed skills/subagents (only if unmodified), and MCP registrations, restoring prior user config. If anything reports `"restored": false`, show the human the listed path and reason.

The default rollback retains CLI tools because they may now be shared by other projects. If the human explicitly wants tools removed too, use `agent-harness uninstall --remove-owned-tools`; it removes only receipt-owned, hash-matching local binaries and reports global/package-manager tools as retained rather than guessing ownership.
