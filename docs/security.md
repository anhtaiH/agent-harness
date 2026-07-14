# Security

Agent Harness is local-first, but it assumes agents make mistakes and that some content agents read is hostile. Gates are enforced in each tool's native hook system and are provable with `agent-harness verify-gates` — not just described in instructions.

## Threat model

- Agent mistakes: destructive commands, scope drift, false completion claims.
- Prompt injection via untrusted content (tool output, PR bodies, web pages, MCP tool results). The harness assumes the lethal-trifecta framing: private data, untrusted content, and external communication must never combine. Connector writes therefore require explicit task-scoped intents, and PR review output is draft-only.
- Secret leakage: into prompts, transcripts, task artifacts, memory, or exfiltrated via shell tools.

## Hard stops (all modes, including yolo)

The shared policy engine denies:

- credential and secret file access (`.env*`, ssh/aws/gh/docker/kube credentials, key files)
- remote code piped into interpreters (`curl ... | sh`, `bash <(wget ...)`)
- secret-exfiltration patterns (archiving/uploading credential paths)
- production-affecting commands (publish, deploy, `gh pr merge`, `terraform apply`, cloud deletes) without explicit human-owned scope
- force pushes to protected branches
- connector writes (GitHub/Jira/Confluence/Slack) with no matching `external_write_intent`
- prompts containing raw secrets (blocked before reaching model context)

Destructive local commands (`rm -rf`, `git reset --hard`, `git clean -xdf`) require confirmation in run mode; yolo mode allows them for the active task.

## Defense in depth

1. Tool-native permission systems remain the first line (Claude Code permissions/sandbox, Codex `sandbox_mode` + `approval_policy`, Cursor sandbox, opencode permissions). Setup seeds deny rules (`Read(**/.env)`, `Read(~/.ssh/**)`) where the tool supports them.
2. Harness hooks add the cross-tool policy layer described above.
3. Wrappers and the MCP server scrub the environment (allowlist + sensitive-name blocklist) so child agents never inherit tokens.
4. Artifact gates: task prompts, evidence, memory candidates, and MCP output are refused if they match redaction patterns (`runtime/policy/redaction-patterns.json`).
5. `doctor` scans the source bundle for configured leak patterns (`runtime/policy/leak-patterns.json` — add your employer's markers) and the runtime tree for secret material.

Verify any time:

```bash
agent-harness verify-gates   # canned payloads through every hook; asserts allow/ask/deny
agent-harness doctor         # files, MCP self-test, leak + sensitive-material scans
```

## Local state

Runtime state lives under `~/.agent-harness/<workspace>/`: task packets, evidence, profiles, worktrees, metrics, memory candidates, adapter backups/metadata. Do not commit runtime state; do not copy another user's runtime into the generic repo.

User-level config edits are marker-delimited or metadata-tracked with timestamped backups; `uninstall --restore-adapters` reverses them.

## External writes

External writes use task-scoped, TTL-bound write intents plus connector-native auth:

```text
Create a write intent for the target Confluence page, perform the connector-native update, verify by reading the page back, and record evidence.
```

The harness never asks for raw API tokens, and the pre-tool gate denies connector writes without an active intent.

## Escape hatches (explicit, auditable)

- `AGENT_HARNESS_MODE=yolo` / task mode `yolo`: converts ask→allow for local destructive commands only.
- `AGENT_HARNESS_SKIP_STOP_GATE=1`: disables the evidence stop gate for a session.
- `finish_task --force`: records finishing without passing evidence (visible in task state).
- Stale active tasks expire after 24h so an abandoned task never permanently nags.
