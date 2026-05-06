# Agent Harness Instructions

Use this harness for non-trivial agentic engineering work in the configured workspace.

## Source Of Truth

1. Current code and tests.
2. Command evidence.
3. Task packet and evidence artifacts.
4. Generated workspace profile.
5. Curated local memory.
6. Chat history.

## Task Flow

- Start or resume a task automatically through MCP when available.
- Use a task packet for non-trivial work.
- Use exactly one writer for implementation.
- Use a harness-managed worktree for implementation unless the packet explicitly says otherwise.
- Run independent review lanes for risky implementation.
- Finish only after `evidence.md` passes the evidence doctor.

## Autonomy

- Default mode keeps conservative local guardrails.
- Yolo mode is available for trusted task-scoped local autonomy.
- Hard stops remain for sensitive file reads, token exfiltration, production-affecting actions, and unsafe PR review posting.

## External Writes

For Confluence, Jira, Slack, and GitHub maintenance writes:

1. Create an `external_write_intent`.
2. Perform the connector-native write.
3. Read back or otherwise verify when possible.
4. Record evidence.

Do not ask users for raw token env vars.

## Project Knowledge

Project-specific context comes from the generated profile under `profiles/<workspace>/`. Treat local memory as candidate knowledge until a human promotes it into project-owned docs.
