# Orchestration

`harness orchestrate` turns a task packet into an autonomous, gated multi-role run. Humans set intent (the packet) and review outcomes; specialized agents do the middle. The conductor itself is deterministic Python — no model decides a state transition.

## Shape

The design is the local translation of three 2026 systems:

- OpenAI's Symphony spec: a work ledger is the control plane; an orchestrator polls ready work, gives each agent an isolated workspace, restarts stalls, and hands finished work to human review.
- Steve Yegge's Gas Town: named roles with narrow contracts (coordinator with the only global view, workers in isolated worktrees, a witness per rig, a merge-serializing refinery, a watchdog patrol) over the beads ledger.
- GPT-5.6 Sol Ultra: dynamic decomposition — a planner decides the role fan-out per task instead of a fixed pipeline.

Mapping here: the conductor is the coordinator (deterministic, not an LLM); `plan.json` + `ledger.jsonl` are the work ledger; role agents are the fleet; the policy hooks and evidence doctor are the gates; you are the Overseer.

## Roles

Role contracts live in `<runtime>/roles/*.md` and end with strict output formats the conductor parses:

| Role | Writes | Gate parsed from output |
| --- | --- | --- |
| planner | plan only | JSON step array (validated: known roles, unique ids, acyclic deps, step cap) |
| researcher | nothing | non-empty `FINDINGS:` |
| worker | code (one writer at a time) | `RESULT:` block; `BLOCKED:` fails the step |
| qa | nothing (runs checks) | first line `QA: PASS` / `QA: FAIL` |
| reviewer | nothing | first line `VERDICT: APPROVE`(+`-WITH-NITS`) / `REQUEST-CHANGES` |
| security | nothing | first line `VERDICT: NO-BLOCKING-FINDINGS` / `BLOCKING-FINDINGS` |
| synthesizer | task artifacts only | evidence sections (validated by the evidence doctor) |

Read-only roles that are simultaneously ready run in parallel (bounded); writers serialize — one writer at a time, in the harness worktree when one exists.

## Lifecycle

```bash
harness start --prompt "Fix ENG-123" --risk yellow          # human intent
harness orchestrate plan latest                              # planner decomposes (deterministic fallback plan if unparseable)
harness orchestrate run latest                               # conductor loop
harness orchestrate status latest                            # ledger + step states
```

`orchestrate run` loops: pick ready steps → dispatch role agents (via the env-scrubbed ah-* wrappers, so every tool call passes the policy gates) → parse verdicts → advance. On a failed gate (QA FAIL, REQUEST-CHANGES, BLOCKING-FINDINGS) it bounces the responsible worker and everything downstream — a bounded fix loop with the failing findings injected into the worker's retry prompt. When all steps are done, the synthesizer's sections become `evidence.md`, the evidence doctor validates them, and the task finishes.

## Budgets and safety

- `--max-iterations` (default 20), `--max-attempts` per fix origin (default 2), `--step-timeout` (default 600s), `--max-steps` plan cap (default 12).
- Exhausted budgets end the run `blocked` with an actionable `next` — never a forced finish. A blocked run is a report to the human, not a failure to hide.
- Crash-safe: state lives in `plan.json`/`ledger.jsonl`; a step left `running` by a dead conductor is re-queued on the next run (watchdog).
- Every role agent runs under the same policy gates as interactive sessions: secrets, remote-exec piping, prod actions, and un-intended connector writes are denied inside orchestration too.
- `--dry-run` exercises the full state machine with canned verdicts (used by the test suite; `AGENT_HARNESS_ORCH_FAIL_STEPS` forces failures to test the fix loop and blocking).

## Choosing agents

The conductor drives whichever peer CLI is installed (`codex`, `claude`, `cursor`), picked automatically or pinned with `--agent` / `config.orchestration.agent`. Where the host tool has native subagents (Claude Code) the reviewer/verifier/security lanes can also run interactively via the shipped subagent definitions; the conductor path works everywhere, headless.
