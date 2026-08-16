---
name: ultragoal
description: Turn natural-language intent into a designed, audited, activated, and durably executed long-running goal that Claude Code keeps working on until a real verifier passes. Use when the user invokes /ultragoal, says "set a goal", "start a goal", "keep going until", "work on this autonomously", "persistent goal", "long-running objective", or asks for self-authored acceptance criteria, real-surface verification, living goal and plan state, enforced completion proof, risk-scaled independent review, cost-aware model routing, bounded subagent delegation, or work that must survive restarts and compaction.
argument-hint: "[design|critique|status|resume|pause|report] <what you want done>"
allowed-tools: Bash(python3 *ultragoal.py *) Bash(git status *) Bash(git diff *) Bash(git log *)
hooks:
  Stop:
    - hooks:
        - type: command
          statusMessage: Ultragoal gate
          timeout: 30
          command: >-
            sh -c 'for d in "${CLAUDE_PLUGIN_ROOT}" "$CLAUDE_PLUGIN_ROOT"
            "$ULTRAGOAL_HOME" "$CLAUDE_PROJECT_DIR/.claude/skills/ultragoal"
            "$HOME/.claude/skills/ultragoal"
            "$HOME/.claude/skills/synced/ultragoal"; do [ -n "$d" ] &&
            [ -f "$d/scripts/ultragoal.py" ] &&
            exec python3 "$d/scripts/ultragoal.py" hook stop; done;
            echo "{\"systemMessage\": \"ultragoal: engine not found — the goal
            gate is NOT armed. Reinstall to ~/.claude/skills/ultragoal or run
            install_hooks.py --include-stop.\"}"; exit 0'
  PreToolUse:
    - matcher: Bash|Edit|Write|NotebookEdit|AskUserQuestion
      hooks:
        - type: command
          timeout: 20
          command: >-
            sh -c 'for d in "${CLAUDE_PLUGIN_ROOT}" "$CLAUDE_PLUGIN_ROOT"
            "$ULTRAGOAL_HOME" "$CLAUDE_PROJECT_DIR/.claude/skills/ultragoal"
            "$HOME/.claude/skills/ultragoal"
            "$HOME/.claude/skills/synced/ultragoal"; do [ -n "$d" ] &&
            [ -f "$d/scripts/ultragoal.py" ] &&
            exec python3 "$d/scripts/ultragoal.py" hook pre-tool; done; exit 0'
---

# Ultragoal

Request: $ARGUMENTS

Use this skill when the user wants a persistent goal, not just a longer task. A
good goal has an observable finish line, a verifier that can fail, and enough
durable context to recover after interruption, `/clear`, compaction, or a full
restart.

Treat the user's prompt as evidence of intent, not a finished specification.
You own the first draft and the audit of the outcome, acceptance conditions,
verifier, constraints, and stopping rules. Never require the user to formulate
these correctly before invoking the skill.

Do not activate from vague planning language alone. Activate when the user
invokes `/ultragoal` with an execution request, or asks to start, set, activate,
run, pursue, or complete a goal.

## The goal bundle

Claude Code has no native goal object, so this skill supplies one. Activation
means creating a **goal bundle** and arming the machinery that enforces it:

```
<repo>/.claude/goals/<slug>/
  goal.md        stable contract: outcome, acceptance, verifier, approvals
  plan.md        operational phase state and next action
  state.json     machine-readable lifecycle the hooks read
  journal.jsonl  append-only evidence and attempt ledger
  evidence/      recorded verifier output with real exit codes
```

Drive `state.json` only through the engine at
`${CLAUDE_SKILL_DIR}/scripts/ultragoal.py`. Call it `UG` below. Edit `goal.md`
and `plan.md` directly as prose.

Three mechanisms make the goal real rather than advisory:

1. **Stop gate.** While a goal is `active`, a `Stop` hook blocks the turn from
   ending and re-injects the contract, current phase, next action, unmet
   acceptance conditions, and last verifier result. You cannot drift away from
   the goal or quietly stop early. Release it only with `complete`, `block`,
   `await`, `waiting`, or `pause` — and under full autonomy, `await` is
   reserved for an irreversible decision outside the goal's scope.
2. **Session resume.** A `SessionStart` hook, installed at activation, restores
   goal state on restart, `/clear`, and compaction, so the goal outlives the
   context window.
3. **Enforced proof.** `UG complete` refuses unless every acceptance condition
   is marked met and the primary verifier has a *recorded passing run*. Run
   checks through `UG verify -- <command>`: it executes the command and stores
   the real exit code. A claim is never proof.

The gate is unbounded by default: a goal runs until `complete` or an
evidence-backed `block`, with no continuation budget, no idle pause, and the
guard off. Only when the user asks for supervision in plain language ("check
with me", "supervised", "ask before risky steps") create the goal with
`--autonomy standard`, which restores the bounded gate — a 40-continuation
budget, an auto-pause after 3 consecutive continuations that record no
progress, and the anti-cheating guard. The user can stop either kind at any
time with Esc or `/ultragoal pause`.

## Modes

- **Design:** research and return a goal packet. Create the bundle, do not activate.
- **Critique:** inspect an existing goal or draft and tighten it. Read-only.
- **Activate:** design, critique, then activate — the default for execution requests.
- **Status / resume / pause / report:** operate an existing goal.

`/ultragoal <ordinary natural-language request>` is the normal interface. No
magic suffix, formal acceptance criteria, route name, model choice, or
concurrency value is required, and the request may rely on conversation context.

- `/ultragoal fix the flaky checkout tests and keep going until the suite is clean` → Activate
- `/ultragoal design a durable goal for the migration` → Design
- `/ultragoal critique this goal before I start it` → Critique
- `/ultragoal resume` → reconcile and continue an open goal

Infer route, models, delegation, and concurrency automatically. State the
selected route in one line before task work. Honor overrides such as
`do not delegate`, `use Haiku`, `optimize for speed`, or `check with me first`
when safe and feasible.

Full autonomy is the default and needs no flag. After activation never use
`AskUserQuestion` and never `await` for anything inside the goal's scope. Make
the call yourself, record each consequential choice with
`UG decide "<choice>" --why "<reason>"`, and keep moving; the user reviews the
decision log via `UG report` after completion. Reserve `await` for an
irreversible action outside the goal's scope. Pre-activation clarification
(the three-question frontier) still applies when the request genuinely
underdetermines the contract — questions end permanently at activation.
`--unattended` is accepted and redundant. Only an explicit plain-language
request for supervision switches the goal to `--autonomy standard`.

Invoking this skill with an execution request grants **delegation authority**:
bounded subagents as an internal tactic under the selected route. It does not
authorize irreversible or public actions, parallel writers on shared state, or
bypassing approval gates.

## Command reference

`UG` = `python3 "${CLAUDE_SKILL_DIR}/scripts/ultragoal.py"`

| Command | Use |
| --- | --- |
| `UG new --objective "<outcome>" [--title T] [--route R] [--assurance A]` | create the bundle (full autonomy is the default) |
| `UG accept "<condition>"` | add an acceptance condition (repeat) |
| `UG verifier "<label>" --proof-boundary "<surface/role/env>"` | declare the primary verifier |
| `UG activate` | arm the gate; installs the session-resume hook |
| `UG status` / `UG report` / `UG list` | current state; completion readiness |
| `UG phase "<name>" --status in_progress --next "<action>"` | move the plan forward |
| `UG next "<action>"` | record the strongest next action |
| `UG verify [--primary] [--label L] -- <command>` | run a check, record the real exit code |
| `UG met <A1> --evidence "<ref>"` / `UG unmet <A1>` | acceptance bookkeeping |
| `UG evidence "<what it showed>" --ref <path>` | record evidence |
| `UG decide "<choice>" --why "<reason>" [--irreversible]` | record an autonomous decision, keep moving |
| `UG attempt --failure <class> --hypothesis H --action A --result R [--lesson L]` | ledger a failed attempt |
| `UG lesson "<task-local lesson>"` | carry a lesson into later phases |
| `UG assurance <compact\|focused\|full> [--lane <name> --finding "<text>"]` | assurance tier and lanes |
| `UG complete` | close the goal; proof is enforced |
| `UG block "<blocker>" --evidence "<ref>"` | evidence-backed external blocker |
| `UG await "<decision needed>"` | release for a human decision (full autonomy: irreversible out-of-scope only) |
| `UG waiting "<what>" --signal "<how you get woken>"` | release for an external wait |
| `UG pause ["reason"]` / `UG resume` | stand down / re-arm |
| `UG config --autonomy standard` | supervised: bounded gate, idle pause, guard on |
| `UG config --guard on` | re-enable the anti-cheating guard alone |

## Execution routes

Routes control execution topology, not goal fit, mode, or assurance.
Auto-select the lowest route that can meet the verifier, state it before task
work, and reassess only after material steering or evidence. Routes are
per-goal, never sticky.

- **Light:** keep research, execution, and integration in the main session.
- **Medium:** one delegated `Agent` lane at a time, sequential relay, one writer, verify before the next handoff.
- **Heavy:** fan out at most three independent read-only `Agent` lanes, fan in before mutation, keep one mutation owner. Parallel *writers* are allowed only with `isolation: worktree`.

Read [routing-and-delegation.md](references/routing-and-delegation.md) before
Medium or Heavy, choosing a child model or effort level, or evaluating routing
policy. Do not load it for routine Light goals.

## Review assurance

After initial Research, select assurance independently from route. Depth
follows consequence and uncertainty, not file count or agent count. A goal may
be Light with Full assurance or Heavy with Compact. Assurance never adds
ceremonial human phase gates.

- **Compact:** reversible, low blast radius, strong deterministic proof. You audit the outcome; spawn no model reviewer.
- **Focused:** one meaningful risk surface. One targeted read-only reviewer at the highest-leverage checkpoint.
- **Full:** multiple distinct or high-consequence risk surfaces. At most three non-overlapping read-only lanes across the goal, then synthesis.

Record each lane with `UG assurance --lane ... --finding ...`; `complete` checks
the count. Read [review-assurance.md](references/review-assurance.md) before
Focused or Full, or when synthesizing multiple reviewers.

## Preflight

Before activation:

1. Confirm `python3` runs and `${CLAUDE_SKILL_DIR}/scripts/ultragoal.py --help` works.
2. Run `UG list`. Resume a matching open goal; never silently replace an unrelated one.
3. If the engine is unavailable, say activation is unsupported and offer a Design packet. Never claim a goal is active when nothing enforces it.

## Workflow

### 1. Research and draft the outcome

Find the intended result, audience, destination, constraints, and why
persistence helps. Read `CLAUDE.md` and any `.claude/rules/`, then inspect
named files, repos, PRs, artifacts, and live systems before drafting. Finding
discoverable facts is your job, not the user's.

Draft the smallest complete specification: outcome, why and audience, target
and baseline, scope and non-goals, constraints and approvals, acceptance
conditions, primary verifier, stopping rules, completion proof.

### 2. Research enough

1. Read the canonical local source and applicable instructions.
2. Inspect the baseline: prior attempts, tests, benchmarks, reproductions, CI.
3. Refresh volatile facts from primary or live sources when they matter.
4. Stop once the finish line and verifier are grounded.

Separate verified facts, user requirements, assumptions, and unknowns.

When the outcome is interactive or environment-dependent, identify the closest
actual user surface and inventory only the capabilities that could change the
proof: terminal, `/run` and `/verify`, browser automation (Chromium and
Playwright are preinstalled in cloud sessions), MCP servers and connectors,
devices or simulators, accounts and roles, credential availability, and test
environments. Confirm live availability without reading or exposing secrets.
Source inspection, unit tests, or a convenient mock may support proof but
cannot silently replace behavior the outcome names.

Read [verification.md](references/verification.md) when proof depends on an
interaction surface or capability.

### 3. Pass the specification-readiness gate

Audit your own draft; do not merely restate the user's wording. Check that
satisfying the acceptance conditions would deliver the real outcome, the
verifier can fail independently, scope and permissions are explicit, and
completion cannot be faked by weakening proof.

- Use a recommended assumption for reversible, low-risk ambiguity; record it in `goal.md` and continue.
- Stop before activation for an irreducible choice that materially changes outcome, scope, data risk, external effects, cost, or proof.
- Ask at most **three** high-impact questions total before activation, in one `AskUserQuestion` call, each with a recommended option first. Never ask for a fact you can discover.
- After those answers, proceed under explicit safe assumptions or report the goal is not ready. Do not continue an open-ended interview.

Read [specification-and-control-loop.md](references/specification-and-control-loop.md)
when intent or verification is ambiguous, the work is risky or genuinely
long-running, or execution stops making progress.

### 4. Check goal fit

Recommend goal mode only when most are true: progress needs repeated attempts,
waiting, recovery, or long feedback cycles; success is measurable by an
external signal; you can respond to the next failure without another preference
decision; completion evidence is stronger than you saying "done".

Prefer an ordinary task when the work is one-shot, taste-dependent, blocked on
repeated human choices, lacks a credible verifier, or risks unbounded external
action. Goal fit is the ceremony boundary — do not wrap a two-minute edit in a
goal bundle.

### 5. Route and scale assurance

Choose Light/Medium/Heavy and Compact/Focused/Full independently, after goal
fit. Treat required quality and safety as a hard floor; after that optimize for
cost by default. Use the cheapest route and model likely to pass the verifier,
and escalate from observed failures, ambiguity, or risk rather than task size.
Never set a token budget unless the user asks for one.

### 6. Define the loop

Specify: **outcome** (one observable result), **baseline**, **primary
verifier** (strongest independent check), **supporting checks**, **proof
boundary** (surface, account or role, environment), **iteration loop** (inspect,
change one meaningful thing, run the verifier, record evidence, choose the next
action), **anti-cheating rules**, **approval gates**, **blocker standard**
(external blocker plus smallest next action; difficulty is not enough), and
**completion proof**.

For flaky or stateful checks, require clean-state reproduction and enough
consecutive passes to rule out luck.

Use an adaptive **Research → Options → Plan → Execute → Review** lifecycle.
Research before mutation, compare options only for real tradeoffs, work inside
the planned contract, review the actual outcome with evidence. Skip or combine
trivial phases; never require mode banners or ceremonial transitions.

### 7. Keep state durable

Create the bundle before activation. Use the project's established convention
if it already provides equivalent state; otherwise use `.claude/goals/<slug>/`.
Keep `goal.md` stable and `plan.md` operational — exactly one phase is
`in_progress` while work is executing. `TodoWrite` is a fine within-session
view, but `plan.md` is the durable record; do not let them diverge.

Keep `state.json`'s `objective` a short pointer, not a second copy of the
contract. Update the files after material steering, failed verification, phase
transitions, timed-out waits, recovered lessons, and final completion or
blockage. Do not commit them automatically.

Read [activation-and-durability.md](references/activation-and-durability.md)
for the state machine, hook behavior, resume sequence, and templates.

### 8. Delegate carefully

You remain goal owner and keep scope, integration, conflict resolution, and
completion. Delegate only separable lanes: environment discovery, source
research, bounded implementation, alternative approaches, independent
verification. One writer per mutable surface unless lanes run in separate
worktrees.

For each lane name the objective, grounded inputs, non-goals, ownership
boundary, verifier, stop condition, and compact evidence return. Prefer a fresh
`Agent` context and pass artifact pointers instead of raw logs; use
`SendMessage` to continue an existing agent rather than re-explaining. Do not
use the `Workflow` tool unless the user explicitly opted into multi-agent
orchestration.

### 9. Activate last

Red-team the draft before arming the gate:

- Can success be faked by weakening the verifier?
- Could the words be satisfied while missing the user's real outcome?
- Does interactive proof exercise the closest actual user surface rather than a source-level or test-only proxy?
- Are approval gates explicit, and have discoverable repository gates (CI, required reviews, `CLAUDE.md` rules) been checked?
- Does the loop say what to do after a failed attempt or a wait?
- Do `goal.md` and `plan.md` exist, stay consistent, and preserve one clear current phase?
- Is completion observable outside this session?

Then run `UG activate`. This is the final action of activation — do not
merely say a goal should be set. Report the bundle path, the armed gate and
its mode (unbounded, or the budget in effect), and how to stop it. For a
walk-away run, remind the user once that the host force-ends a turn after 8
consecutive gate blocks unless the session was launched with
`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=0` (or a higher cap). Then continue task
work under Active Goal Discipline.

## Goal packet

Keep it compact and omit empty sections:

1. **Fit and readiness:** goal mode or a better alternative; `ready`, `ready with assumptions`, `needs decisions`, or `not goal fit`.
2. **Grounding:** current state, user intent, recommended assumptions, evidence gaps.
3. **Goal brief:** outcome, baseline, scope, constraints, non-goals, verifier and proof boundary, loop, approval gates, blocker standard, completion proof.
4. **Unresolved decisions:** only consequential ones, each with a recommendation.
5. **Execution and assurance:** route plus tier, with reasons.
6. **Delegation map:** only when useful and authorized.
7. **Activation state:** `drafted`, `active`, `unsupported`, or `not recommended`, plus the bundle path.

## Active goal discipline

While a goal is active:

- reconcile `state.json`, the living artifacts, and refreshed external reality before continuing, especially on resume;
- keep exactly one phase `in_progress`, and record the strongest next action every time it changes;
- run the strongest applicable deterministic verifier through `UG verify` before any model review; earlier model review is advisory and is never completion evidence;
- verify interactive outcomes on the closest actual user surface or a recorded equal-strength equivalent;
- satisfy the selected assurance tier before completion; reviewer agreement never substitutes for the verifier;
- make every continuation add evidence, reduce uncertainty, move the verifier, or change the hypothesis — under `--autonomy standard` the gate auto-pauses when it does not, and under full autonomy nothing will stop you, so wasted continuations are yours to notice and correct;
- record concise task-local lessons with `UG lesson` and apply them to later phases and worker packets;
- adapt methods freely inside the contract, but never treat learning as permission to weaken the outcome, acceptance, proof boundary, anti-cheating rules, approval gates, or completion standard;
- retry an identical mechanical failure at most once, after changing the setup or packet;
- after two consecutive verifier failures with no measurable progress, or three failures within one approach, stop that approach, return to Research and Plan, and escalate the blocked decision — not the whole workflow;
- after three distinct evidence-backed approaches fail, `UG attempt`-ledger them, summarize, recommend the next move, and take it autonomously when it stays inside the contract; `await` only for an irreversible choice outside the goal's scope (supervised goals may also await when the next option changes scope, risk, proof, or approval boundaries);
- never respond to failure by spawning more peers or repeating identical polling; for waits, use a background `Bash` task or `Monitor` and `UG waiting --signal ...` rather than sleeping;
- decide open in-scope questions yourself, record them with `UG decide`, and continue — `AskUserQuestion` and `UG await` are only for supervised (`standard`) goals or an irreversible decision outside the goal's scope;
- mark complete only when `UG complete` accepts the proof; mark blocked only with evidence and no meaningful remaining progress;
- preserve partial results and the next action whenever you stop.
