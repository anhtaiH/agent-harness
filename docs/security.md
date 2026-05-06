# Security

Agent Harness is local-first, but it still assumes agents can make mistakes.

## Local State

Runtime state lives under `~/.agent-harness/<workspace>/`. It contains task packets, evidence, generated profiles, worktrees, metrics, memory candidates, dashboard files, and connector-derived context gathered during tasks.

Do not commit runtime state. Do not copy another user’s runtime into the generic repo.

## Hard Stops

The default policy denies:

- credential and secret file reads
- token exfiltration patterns
- raw credential environment passthrough
- production-affecting actions without explicit task scope
- automatic PR-review comment posting

Yolo mode relaxes local shell constraints for the active task/worktree, but it does not relax secret or production hard stops.

## External Writes

External writes use task-scoped write intents:

```text
Create a write intent for the target Confluence page, perform the connector-native update, verify by reading the page back, and record evidence.
```

The harness expects connector-native auth from the agent surface. It does not ask for raw API tokens.

## Project Knowledge

Profiles are generated locally from the user’s checkout and accessible context. The generic package does not ship company-specific docs, Slack content, Jira data, PR history, or personal memory.

## Reporting

Use `agent-harness doctor` to scan runtime files, MCP tooling, generated source, and local artifacts for obvious problems. Use `agent-harness where` to inspect exactly what a runtime points at.
