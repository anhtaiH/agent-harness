# Ultragoal: Codex → Claude Code port report

## Summary

`ultragoal` turns a plain-English request into a goal the agent keeps working on
until a real verifier passes. The Codex version leaned on a native goal
primitive — `create_goal`, `get_goal`, `update_goal` — that the runtime enforced
outside the model. Claude Code has no such primitive, so the port supplies one.

Everything that made the original good is judgment: the agent drafts its own
acceptance criteria instead of demanding them from the user, proof must observe
the surface the user actually experiences, routing and review scale with risk
rather than task size, and a spinning loop is detected and stopped. All of that
is preserved.

What changed is the machinery underneath. Activation is no longer a tool call;
it is a durable bundle on disk plus three hooks that make the goal enforceable
from outside the model's discretion.

## Install and first use

```bash
unzip ultragoal.zip -d ~/.claude/skills/
python3 ~/.claude/skills/ultragoal/scripts/ultragoal.py selftest
```

Result must be `~/.claude/skills/ultragoal/SKILL.md`. Use `.claude/skills/`
instead to share it with a repository. Requires Python 3.8+ and `sh`; no
third-party packages.

```
/ultragoal fix the flaky checkout tests and keep going until the suite is clean
```

Claude researches the code, drafts the contract, audits its own draft, asks at
most three questions if a decision is genuinely the user's, then activates and
works until the verifier passes or a bounded limit stops it.

| You type | What happens |
| --- | --- |
| `/ultragoal <request>` | design, audit, activate, execute |
| `/ultragoal design <request>` | goal packet only, nothing armed |
| `/ultragoal critique this goal` | tighten an existing goal or draft |
| `/ultragoal --unattended <request>` | never ask; record assumptions instead |
| `/ultragoal status` / `resume` / `pause` | operate an open goal |

## The core problem and the replacement

A goal primitive has to do three things: persist an objective past a single
turn, expose a lifecycle other machinery can read, and keep the agent coming
back until the objective is met. Codex got all three from its runtime. In Claude
Code they come from three different places.

**Persistence → a goal bundle on disk.**

```
<repo>/.claude/goals/<slug>/
  goal.md        the contract: outcome, acceptance, verifier, approvals
  plan.md        phases, current state, strongest next action
  state.json     machine-readable lifecycle the hooks read
  journal.jsonl  append-only evidence and attempt ledger
  evidence/      recorded verifier logs with real exit codes
```

**Lifecycle → `scripts/ultragoal.py`**, a stdlib-only state engine. It is the
`create_goal`/`get_goal`/`update_goal` analogue, and it is what the hooks read.

**"Keep coming back" → hooks.** This is the part with no Codex counterpart, and
it is what makes the port work rather than merely translate.

## The three hooks

### 1. Stop gate — the autonomy engine

Declared in `SKILL.md` frontmatter, so it arms the moment `/ultragoal` is
invoked and stays armed for the session. While a goal's status is `active`, the
`Stop` hook returns `decision: "block"`, and the turn cannot end. The block
reason is not a nag; it re-injects the working set:

- the outcome and absolute paths to `goal.md` and `plan.md`
- the current phase and the recorded strongest next action
- every unmet acceptance condition
- the last verifier run and its real exit code
- exactly what is still blocking completion
- the five commands that release the gate
- the continuation and idle counters, and how the user stops it

This is why the goal does not decay. A model that has drifted, or lost context
to compaction, gets the contract back on every attempt to stop.

### 2. Session resume — surviving restarts

A `SessionStart` hook, installed at activation into the repository's
`.claude/settings.local.json`, injects the full status of every open goal on
`startup`, `resume`, `clear`, and `compact`, along with the reconcile-before-you-
continue sequence.

This is the one hook that cannot come from skill frontmatter: by the time a
skill loads, the session has already started. It is why `activate` writes to a
settings file at all, and it is fully reversible:

```bash
python3 ~/.claude/skills/ultragoal/scripts/install_hooks.py --uninstall
```

Activation also adds `.claude/settings.local.json` to `.git/info/exclude` if it
is not already ignored, which touches no tracked file.

### 3. Anti-cheating guard — enforcing what used to be prose

The original stated anti-cheating rules and trusted the model to follow them. A
`PreToolUse` hook enforces the narrow, high-confidence subset while a goal is
active:

| Action | Decision |
| --- | --- |
| `git push --force` without `--force-with-lease` | deny |
| `git commit`/`push --no-verify` | deny |
| `rm` inside `.claude/goals/` | deny |
| removing or reverting test files | ask |
| adding `@pytest.mark.skip`, `it.skip(`, `#[ignore]`, `t.Skip(`, … | ask |
| editing the acceptance / verifier / completion-proof sections of `goal.md` | ask |

It targets the goal's own proof surface; ordinary development is untouched.
`ultragoal.py config --guard off` disables it per goal.

All three hooks exit silently when no goal is active, and any internal error
exits 0 with no output. A corrupt goal file can never wedge a session — the
selftest asserts this.

## Enforced completion proof

The strongest single change. `complete` is refused unless:

1. every acceptance condition is marked met with an evidence reference, and
2. the primary verifier has a **recorded passing run**, and
3. the assurance tier's review lanes have been recorded (Focused needs 1, Full needs 2).

Checks go through the engine:

```bash
ultragoal.py verify --primary --label "pytest -q" -- python3 -m pytest -q
```

It executes the command, stores the real exit code, duration, an output hash,
and the full log under `evidence/`, and exits non-zero when the check fails.
"Tests pass" with nothing run is rejected. `complete --force` exists for the
case where the user explicitly accepts weaker proof; it records every gap it
was forced past.

## Lifecycle states

| Status | Gate | Meaning | Leaves via |
| --- | --- | --- | --- |
| `drafted` | off | bundle exists, contract not armed | `activate` |
| `active` | **on** | work in progress; turns cannot end | any release below |
| `waiting` | off | an external process must finish | `resume` |
| `awaiting-input` | off | a human decision is pending | `resume` |
| `paused` | off | user stood it down, or a budget tripped | `resume` |
| `blocked` | off | evidence-backed blocker, no progress left | `resume` |
| `complete` | off | proof accepted | terminal |

`waiting` and `await` are deliberately distinct: `waiting` is a machine,
`await` is a person. `block` requires `--evidence`, because difficulty and
uncertainty are not blockers.

## How it stops

The gate is bounded four ways, and every limit auto-pauses with a message rather
than stopping silently:

- **40 continuations** by default (`--max-continues`).
- **3 consecutive continuations that record no progress.** Progress means a
  `verify`, `evidence`, `met`, `phase`, `next`, `attempt`, `lesson`, or
  `assurance` call. Thinking in circles does not count. This is the original's
  anti-spin rule made deterministic.
- **An optional wall-clock deadline** (`--deadline-minutes`).
- **The user**, at any moment: Esc, or `/ultragoal pause`.

Claude also releases the gate itself, deliberately, in five ways: `complete`,
`block`, `await`, `waiting`, `pause`.

## What changed from the Codex version

### Removed

| Codex | Why |
| --- | --- |
| `create_goal` / `get_goal` / `update_goal` preflight | no such tools; replaced by the bundle plus hooks |
| 4,000-character native objective limit | no native objective; `state.json` keeps a short pointer, and the discipline of "pointer, not a second copy of the contract" is preserved |
| `token_budget` parameter | no equivalent; bounded by continuation budget and deadline instead |
| `fork_turns="none"` guidance | `Agent` subagents already start fresh; `SendMessage` continues one with context intact |
| `update_plan` (Codex plan tool) | `TodoWrite`, explicitly subordinate to the durable `plan.md` |
| `.codex/<slug>/` | `.claude/goals/<slug>/` |
| GPT-5.6 model table and retirement dates | Claude model and effort tiers |

### Added — Claude Code only

- **The three hooks above.** The entire enforcement layer is new.
- **`verify --`**, recorded proof with real exit codes and stored logs.
- **`AskUserQuestion`** for the three-question clarification frontier, with the
  original's compact form mapped onto options, recommendations, and tradeoffs.
- **Plan mode** (`EnterPlanMode` / `ExitPlanMode`) as the natural home for
  Design mode and the readiness gate.
- **Worktree isolation.** The original's hard "one writer at a time" rule
  relaxes honestly: an `Agent` with `isolation: worktree` gets its own git
  worktree, so competing approaches or independent subsystems can write in
  parallel and be integrated by the parent.
- **`/code-review` and `/security-review`** as first-class assurance lanes, and
  custom reviewer agents that preload a checklist skill.
- **Background `Bash` and `Monitor`** instead of sleep-polling, with `waiting
  --signal` recording how the session gets woken.
- **`/run`, `/verify`, `/run-skill-generator`, preinstalled Chromium and
  Playwright** in the proof-surface table.
- **PR subscription** (`subscribe_pr_activity`) as an external wake source for
  goals that end in a pull request.
- **`CLAUDE.md` and `.claude/rules/`** as canonical instructions to read during
  Research.
- **Permission modes, `allowed-tools`, `/fewer-permission-prompts`** documented
  as the levers that decide how hands-off a run actually is.
- **`/loop`, scheduled tasks, and routines** for continuation across hours.
- **`--unattended`** — never ask, record assumptions, reserve `await` for
  decisions that would be unsafe to make alone.

### Preserved

Modes (Design / Critique / Activate). Natural invocation with no magic suffix.
Routes Light / Medium / Heavy for execution topology, chosen independently from
assurance tiers Compact / Focused / Full. The specification-readiness gate and
acceptance audit. The at-most-three-questions clarification frontier. The
adaptive Research → Options → Plan → Execute → Review lifecycle. The escalation
ladder — retry a mechanical failure once, abandon an approach after two
scoreless verifier failures, decision review after three distinct approaches.
Worker capsules, discovery deltas, and repair deltas. The proof ladder, from
direct surface down to weaker proxy. Run-local learning that never authorizes
weakening the contract.

## Files

```
ultragoal/
  SKILL.md                                     348 lines — loads on invocation
  README.md                                    install and usage
  references/activation-and-durability.md      state machine, hooks, resume, templates
  references/verification.md                   proof ladder and Claude Code proof surfaces
  references/routing-and-delegation.md         routes, subagents, worktrees, model tiers
  references/review-assurance.md               Compact / Focused / Full review
  references/specification-and-control-loop.md readiness, clarification, anti-spin
  scripts/ultragoal.py                         state engine, hooks, selftest
  scripts/install_hooks.py                     settings installer / uninstaller
```

References load only when the situation calls for them, which keeps the resident
cost to `SKILL.md`.

## Verification

`scripts/ultragoal.py selftest` runs the whole system in a temp directory —
21 checks, all passing:

- bundle creation writes `goal.md`, `plan.md`, `state.json`
- activation is refused without acceptance conditions and a declared verifier
- the stop gate blocks while active and names all five release commands
- a duplicate `prompt_id` (skill frontmatter and settings both firing) counts once
- `complete` is refused with no passing verifier, and again with unmet acceptance
- `complete` is accepted once proof is real
- the gate releases on `complete`
- a failing check is recorded with its real non-zero exit code
- the goal auto-pauses after the idle limit, reports the true idle count, and releases
- `SessionStart` re-injects open goals
- the guard denies a force-push, ignores an ordinary push, and asks before a test skip
- a corrupted `state.json` exits 0 rather than wedging the session

Separately verified by hand in a throwaway git repository with a real pytest
suite: install to `.claude/skills/`, ground, activate (which really wrote the
`SessionStart` hook and the permission rule and updated `.git/info/exclude`),
watch the gate block via the frontmatter shell locator, run a genuinely failing
suite, see `complete` refused with all three gaps listed, delete the broken
test, re-verify to a pass, record an assurance lane, complete, and confirm the
gate released. Also checked: double `activate` is a no-op with a clear message,
and a malformed `settings.local.json` does not lose an activation.

## Known limitations and knobs

- **`.claude/` is a protected path.** Writes there can prompt in some permission
  modes. All state mutation goes through the engine over Bash, and `activate`
  adds the allow rule for it, so this shows up only for direct edits to
  `goal.md` and `plan.md`. Set `ULTRAGOAL_DIR` or `--dir` to relocate the bundle
  if it is noisy in your setup.
- **The frontmatter hook command is a shell locator.** It searches
  `$ULTRAGOAL_HOME`, `$CLAUDE_SKILL_DIR`, `$CLAUDE_PLUGIN_ROOT/skills/ultragoal`,
  `$CLAUDE_PROJECT_DIR/.claude/skills/ultragoal`, and two `$HOME` paths, and
  exits 0 silently if none match. That is deliberate: it degrades to "no gate"
  rather than to an error on every turn. `install_hooks.py --include-stop`
  registers the gate with an absolute path if you would rather not rely on it.
- **One gate reason per session.** With several goals active, the gate reports
  the most recently updated one. CLI commands refuse to guess and ask for
  `--slug`.
- **Cloud sessions and routines start fresh** and do not read
  `~/.claude/skills/`. Commit the skill to the repository's `.claude/skills/`,
  or enable it for your claude.ai account, and commit the goal bundle if a
  scheduled run should pick it up.
- **The engine cannot verify what it cannot run.** Screenshots, manual
  readbacks, and human confirmations are recorded through `evidence` and
  `met --evidence` instead, which is honest bookkeeping rather than proof —
  the proof ladder in `references/verification.md` covers when that is enough.
