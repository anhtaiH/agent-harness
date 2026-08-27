# Troubleshooting

## Setup Cannot Find A Repo

Run setup from inside a git repo or pass a repo path:

```bash
env npm_config_ignore_scripts=true npx --yes github:anhtaiH/agent-harness#v0.3.0 setup --repo /path/to/repo
```

## Dependency Install Fails

On Linux, setup verifies non-interactive package-manager privilege before changing the system. If it reports that privilege is unavailable, run `sudo -v` interactively and retry, install the listed tools yourself, or use `--toolchain none`.

Run:

```bash
npm --version
env npm_config_ignore_scripts=true npx --yes github:anhtaiH/agent-harness#v0.3.0 setup --yes
```

For a CLI-only install while debugging npm:

```bash
env npm_config_ignore_scripts=true npx --yes github:anhtaiH/agent-harness#v0.3.0 setup --yes --skip-deps
```

MCP features require Node dependencies, so use `--skip-deps` only as a temporary fallback.

## Agent Cannot See The Harness

Check:

```bash
agent-harness where
agent-harness doctor
agent-harness examples
```

If the app does not load MCP automatically, use the adapter snippets printed by `where`. The agent can still use the local shim commands as a fallback.

If setup skipped an adapter, `where` will show why. Common causes:

- the app CLI is not installed
- an existing MCP config was left unchanged to avoid unsafe merging
- a non-harness shim already exists in the target shim directory

Review the output, then rerun setup with `--force` only when you are comfortable replacing managed harness entries or merging a server entry into existing app config.

## Toolchain Install Is Incomplete

Run `agent-harness doctor --json` and inspect `toolchain.missing` plus the recorded actions. Setup uses the detected package manager first, then only pinned npm/Python packages or checksum-verified release archives for missing portable tools. It never pipes downloaded code into a shell. Re-run `setup --dry-run --json` before retrying on a different package-manager configuration.

Semble, Serena, Headroom, and unauthenticated Context7 are configured for supported clients. Playwright is intentionally lazy. Harness itself defaults to the compact MCP profile; use the `legacy` profile only when a workflow requires the full historical tool surface.

## A Shim Was Not Installed

Setup skips existing non-harness files instead of overwriting them. Re-run with a different shim directory:

```bash
env npm_config_ignore_scripts=true npx --yes github:anhtaiH/agent-harness#v0.3.0 setup --yes --shim-dir /path/to/bin
```

Use `--force` only when you are replacing a managed harness shim.

## Gates Do Not Fire (Or Fire Too Much)

Prove behavior first:

```bash
agent-harness verify-gates
```

All cases must pass. If a real session still is not gated:

- Claude Code: check `~/.claude/settings.json` contains the harness `hooks` entries (rerun setup if a tool update reset them; hooks changes require a new session).
- Cursor: check `~/.cursor/hooks.json` lists `cursor-bridge.py` once under `preToolUse`.
- opencode: check `~/.config/opencode/plugins/agent-harness.js` exists; run `opencode run --print-logs` to see plugin errors.
- pi: check `~/.pi/agent/extensions/agent-harness.ts` exists.

If the Stop gate blocks a session you consider done: finish properly (`write_evidence` → `evidence_doctor` → `finish_task`), or abandon explicitly (`finish_task --force`), or set `AGENT_HARNESS_SKIP_STOP_GATE=1` for that session. Active tasks expire after 24h, so a forgotten task never nags forever.

## Remove The Runtime

```bash
agent-harness uninstall
```

This removes managed shims, managed app-adapter blocks, managed repo-local adapter files, and runtime state. It does not edit tracked repo files.

## PR Review Produced No Useful Comments

That can be the correct result. The PR-review flow is tuned for precision. Ask the agent to show private evidence and discarded findings, then decide whether to escalate:

```text
Read the PR review packet and discarded findings. If the draft is empty, explain whether that is because the PR is low risk, evidence was missing, or lanes were not run.
```
