# Human-Agent Contract

Agent Harness is designed for autonomous work with explicit ownership boundaries.

## Human Owns

- Intent: what outcome matters and what is out of scope.
- Permission: yolo mode, external writes, risky actions, and final posting decisions.
- Final judgment: merge readiness, public comments, and organization-facing communication.
- Memory promotion: deciding which local memory candidates become project-owned knowledge.
- Escalation: stopping or redirecting the agent when the task goal changes.

## Agent Owns

- Starting or resuming the harness task automatically.
- Gathering compact context from code, tests, project docs, and available connectors.
- Keeping implementation in a harness-managed worktree when the task changes code.
- Running the checks that match the risk.
- Calling independent review lanes for non-trivial work.
- Writing evidence before declaring completion.
- Recording reusable lessons as memory candidates with sources.

## Shared Rules

- Natural-language prompts are the primary interface.
- The agent should not ask the human to type backend paths for normal work.
- Evidence is required for completion.
- PR review output is private draft material until a human decides to own and post it.
- External org writes require a task-scoped write intent and read-back verification when possible.
