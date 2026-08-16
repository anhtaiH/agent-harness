# Ultragoal for Claude Code

Turn a plain-English request into a goal Claude Code keeps working on until a
real verifier passes — across failures, restarts, `/clear`, and compaction —
with as little human input as the work honestly allows.

Adapted from the Codex `ultragoal` skill. The judgment (self-authored
acceptance criteria, real-surface proof, cost-aware routing, risk-scaled
review, anti-spin control) is preserved. The activation machinery is rebuilt on
Claude Code primitives, because Claude Code has no native goal object.

## Install

**Personal (all your projects):**

```bash
unzip ultragoal.zip -d ~/.claude/skills/
python3 ~/.claude/skills/ultragoal/scripts/ultragoal.py selftest
```

**Project (shared with the repo):**

```bash
unzip ultragoal.zip -d .claude/skills/
python3 .claude/skills/ultragoal/scripts/ultragoal.py selftest
```

The result must be `~/.claude/skills/ultragoal/SKILL.md` — one directory named
`ultragoal`, not a nested folder. `selftest` runs the whole lifecycle in a
temp directory and prints one line per check; all of them should say `ok`.

Requirements: Python 3.8+ and `sh` on PATH. No third-party packages. Claude
Code picks up new skills within the session, but if `~/.claude/skills/` did not
exist before, restart Claude Code once.

Nothing is installed globally until you activate a goal. On the first
`activate` in a repository, the skill adds a `SessionStart` hook and one
permission-allow rule to that repository's `.claude/settings.local.json`, and
adds that file to `.git/info/exclude` if it is not already ignored. Undo with:

```bash
python3 ~/.claude/skills/ultragoal/scripts/install_hooks.py --uninstall
```

## Use

```
/ultragoal fix the flaky checkout tests and keep going until the suite is clean
```

That is the whole interface. Claude researches the codebase, drafts the
contract (outcome, acceptance conditions, verifier, stopping rules), audits its
own draft, asks at most three high-impact questions if a decision is genuinely
yours to make, then activates and works.

Other forms:

| You type | What happens |
| --- | --- |
| `/ultragoal <request>` | design, audit, activate, execute |
| `/ultragoal design <request>` | goal packet only, nothing armed |
| `/ultragoal critique this goal` | tighten an existing goal or draft |
| `/ultragoal --unattended <request>` | never ask; record assumptions instead |
| `/ultragoal status` | where the goal stands |
| `/ultragoal resume` | reconcile and continue |
| `/ultragoal pause` | stand down now |

Overrides work in plain language: `do not delegate`, `use Haiku for the search`,
`optimize for speed`, `full review`.

## What activation actually does

It writes a **goal bundle** and arms three hooks:

```
<repo>/.claude/goals/<slug>/
  goal.md        the contract
  plan.md        phases, current state, next action
  state.json     lifecycle the hooks read
  journal.jsonl  evidence and attempt ledger
  evidence/      recorded verifier logs with real exit codes
```

1. **Stop gate.** While the goal is active, Claude's turn cannot end. The hook
   re-injects the contract, current phase, next action, unmet acceptance
   conditions, and last verifier result, so the work continues instead of
   trailing off with a summary.
2. **Session resume.** A `SessionStart` hook restores the goal after a restart,
   `/clear`, or compaction. The goal outlives the context window.
3. **Enforced proof.** `complete` is refused unless every acceptance condition
   is met *and* the primary verifier has a recorded passing run. Checks go
   through `ultragoal.py verify -- <command>`, which executes them and stores
   the real exit code. "Tests pass" with nothing run is rejected.

A fourth, narrow hook guards the proof surface: while a goal is active, it
denies force-pushes and `--no-verify`, denies deleting the goal bundle, and
asks before removing or skipping tests or editing the acceptance and verifier
sections of `goal.md`. Turn it off per goal with `ultragoal.py config --guard off`.

## How it stops

The gate is bounded, and every limit pauses rather than stopping silently:

- **40 continuations** by default (`--max-continues`).
- **3 consecutive continuations with no recorded progress** — evidence, a
  verifier run, an acceptance change, a phase change, or a ledgered attempt.
- **An optional wall-clock deadline** (`--deadline-minutes`).
- **You**, at any moment: press Esc, or run `/ultragoal pause`.

Claude also releases the gate itself, deliberately, in four other ways:
`complete` (proof satisfied), `block` (evidence-backed external blocker),
`await` (a decision that is genuinely yours), and `waiting` (an external
process, with the wake signal recorded).

## Running hands-off

The gate keeps Claude working; permissions decide whether it needs you.

```bash
claude --permission-mode acceptEdits          # no edit prompts
claude -p "/ultragoal <request>"              # headless, one shot
```

For longer runs, `/loop` re-enters on an interval or self-paced, and a
scheduled task can fire `/ultragoal resume`. Cloud sessions and routines start
fresh each time, so commit the goal bundle if you want them to pick it up.

## Command reference

`UG` = `python3 ~/.claude/skills/ultragoal/scripts/ultragoal.py`. Claude drives
these; you rarely need them, but they are useful for inspecting a run.

```bash
UG list                       # every goal in this repo
UG status                     # full state of the open goal
UG report                     # status plus completion readiness
UG pause / UG resume          # stand down / re-arm
UG complete                   # close it (proof enforced)
UG config --guard off --max-continues 80
UG selftest                   # end-to-end health check
```

The journal is plain JSONL — `jq . .claude/goals/<slug>/journal.jsonl` shows
every verifier run, attempt, lesson, and gate decision in order.

## Uninstall

```bash
python3 ~/.claude/skills/ultragoal/scripts/install_hooks.py --uninstall  # per repo
rm -rf ~/.claude/skills/ultragoal
```

Goal bundles under `.claude/goals/` are yours; delete them separately.

## Files

```
ultragoal/
  SKILL.md                                    the skill Claude loads
  README.md                                   this file
  references/activation-and-durability.md     state machine, hooks, resume
  references/verification.md                  proof ladder and proof surfaces
  references/routing-and-delegation.md        Light/Medium/Heavy, subagents, worktrees
  references/review-assurance.md              Compact/Focused/Full review tiers
  references/specification-and-control-loop.md readiness gate, clarification, anti-spin
  scripts/ultragoal.py                        state engine, hooks, selftest
  scripts/install_hooks.py                    settings installer / uninstaller
```

`SKILL.md` loads on invocation; the references load only when the situation
calls for them.
