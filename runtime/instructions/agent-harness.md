# Agent Harness Instructions

Use this harness for non-trivial agentic engineering work in the configured workspace. This file is the long-form contract; the short block installed into your tool's instruction file points here.

## Source Of Truth

1. Current code and tests.
2. Command evidence.
3. Task packet and evidence artifacts.
4. Generated workspace profile.
5. Curated local memory.
6. Chat history.

## Autonomous Orchestration

For multi-step work the human wants done end-to-end (not steered), prefer the conductor: `orchestrate_plan` then `orchestrate_run` (MCP) or `harness orchestrate run <task>`. It decomposes the packet into role steps (researcher/worker/qa/reviewer/security/synthesizer), gates every transition on parsed verdicts, retries through bounded fix loops, and finishes through the evidence doctor — or ends `blocked` with a report for the human. Use plain task flow below for small or interactive work.

## Task Flow

- Start or resume a task through MCP (`start_task` / `resume_task`) or the runtime CLI (`bin/harness`).
- Use a task packet for non-trivial work; fill Scope and Verification before editing.
- Use exactly one writer for implementation.
- Use a harness-managed worktree for implementation unless the packet explicitly says otherwise.
- Record progress checkpoints at meaningful boundaries (`record_progress`).
- Run independent review lanes for risky implementation: `harness-reviewer`, `harness-verifier`, and `harness-security` subagents where supported, or cross-tool peer lanes via `agent_run`.
- Finish only after `evidence.md` passes the evidence doctor (`evidence_doctor` then `finish_task`).

## Gates (enforced, not advisory)

Setup wires these into your tool's native hook/permission system; `harness verify-gates` proves they fire:

- Pre-tool policy: denies credential/secret file access, remote-code piping (`curl | sh`), secret exfiltration patterns, production-affecting commands, protected-branch force pushes, and connector writes without a write intent; destructive local commands ask first outside yolo mode.
- Prompt secret scan: blocks prompts containing raw credentials before they reach model context.
- Stop gate: blocks ending a session while the active task's evidence is missing or incomplete (escape: finish or abandon the task explicitly; `AGENT_HARNESS_SKIP_STOP_GATE=1`).
- Session start: injects the active-task capsule so resumed sessions continue instead of restarting.
- Drift check: warns when the tracked checkout drifts while a task is active (throttled).

## Autonomy

- `plan` mode: read-only exploration and packet writing.
- `run` mode (default): conservative guardrails; destructive commands require confirmation.
- `yolo` mode: broad local shell autonomy for the active task; hard stops for secrets, exfiltration, production actions, and un-intended connector writes remain.

## External Writes

For Confluence, Jira, Slack, and GitHub maintenance writes:

1. Create an `external_write_intent` (task-scoped, TTL-bound).
2. Perform the connector-native write; never ask for raw token env vars.
3. Read back or otherwise verify when possible.
4. Record evidence.

The pre-tool gate denies connector writes with no matching intent.

## Project Knowledge

Project-specific context comes from the generated profile under `profiles/<workspace>/`. Treat local memory as candidate knowledge until a human promotes it into project-owned docs (AGENTS.md, docs/). Never copy secrets or personal data into memory or task artifacts; the redaction gate rejects them.
