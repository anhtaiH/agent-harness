# Troubleshooting

## Setup Cannot Find A Repo

Run setup from inside a git repo or pass a repo path:

```bash
npx --yes github:anhtaiH/agent-harness setup --repo /path/to/repo
```

## Dependency Install Fails

Run:

```bash
npm --version
npx --yes github:anhtaiH/agent-harness setup --yes
```

For a CLI-only install while debugging npm:

```bash
npx --yes github:anhtaiH/agent-harness setup --yes --skip-deps
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

## A Shim Was Not Installed

Setup skips existing non-harness files instead of overwriting them. Re-run with a different shim directory:

```bash
npx --yes github:anhtaiH/agent-harness setup --yes --shim-dir /path/to/bin
```

Use `--force` only when you are replacing a managed harness shim.

## Remove The Runtime

```bash
agent-harness uninstall --restore-adapters
```

This removes managed shims and runtime state. It does not edit tracked repo files.

## PR Review Produced No Useful Comments

That can be the correct result. The PR-review flow is tuned for precision. Ask the agent to show private evidence and discarded findings, then decide whether to escalate:

```text
Read the PR review packet and discarded findings. If the draft is empty, explain whether that is because the PR is low risk, evidence was missing, or lanes were not run.
```
