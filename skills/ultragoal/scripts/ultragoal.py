#!/usr/bin/env python3
"""Ultragoal state engine for Claude Code.

Claude Code has no native goal primitive, so this script *is* the goal
primitive: a durable state machine on disk plus three hook handlers that make
the state enforceable from outside the model.

  state.json      lifecycle record (the `get_goal` / `update_goal` analogue)
  goal.md         stable contract, human readable
  plan.md         operational phase state
  journal.jsonl   append-only evidence / attempt ledger
  evidence/       recorded verifier output

Hook handlers (invoked as `ultragoal.py hook <event>`):

  stop           blocks the turn from ending while a goal is `active`
  session-start  re-injects goal state after restart, /clear, or compaction
  pre-tool       narrow anti-cheating guard on the goal's own proof surface

Every handler is failure-safe: any unexpected error exits 0 with no output so
a broken goal file can never wedge a Claude Code session.

Stdlib only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = 1
DEFAULT_MAX_CONTINUES = 40
DEFAULT_IDLE_LIMIT = 3
EVIDENCE_TAIL_LINES = 40

STATUS_DRAFTED = "drafted"
STATUS_ACTIVE = "active"
STATUS_WAITING = "waiting"
STATUS_AWAITING = "awaiting-input"
STATUS_PAUSED = "paused"
STATUS_BLOCKED = "blocked"
STATUS_COMPLETE = "complete"

OPEN_STATUSES = {STATUS_ACTIVE, STATUS_WAITING, STATUS_AWAITING, STATUS_PAUSED}
ALL_STATUSES = OPEN_STATUSES | {STATUS_DRAFTED, STATUS_BLOCKED, STATUS_COMPLETE}


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def project_root() -> Path:
    """Repo root, else CLAUDE_PROJECT_DIR, else cwd."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except Exception:
        pass
    if env:
        return Path(env)
    return Path.cwd()


def goals_root(explicit: str = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("ULTRAGOAL_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return project_root() / ".claude" / "goals"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "goal").strip().lower())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return (s or "goal")[:48]


# --------------------------------------------------------------------------
# bundle
# --------------------------------------------------------------------------

class Bundle:
    def __init__(self, root: Path, slug: str):
        self.root = root
        self.slug = slug
        self.dir = root / slug
        self.state_path = self.dir / "state.json"
        self.journal_path = self.dir / "journal.jsonl"
        self.goal_path = self.dir / "goal.md"
        self.plan_path = self.dir / "plan.md"
        self.evidence_dir = self.dir / "evidence"
        self._state = None

    # -- state io ----------------------------------------------------------
    @property
    def state(self) -> dict:
        if self._state is None:
            self._state = json.loads(self.state_path.read_text(encoding="utf-8"))
        return self._state

    def save(self) -> None:
        self._state["updated_at"] = now()
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._state, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.state_path)

    def exists(self) -> bool:
        return self.state_path.is_file()

    # -- journal -----------------------------------------------------------
    def log(self, kind: str, **fields) -> None:
        entry = {"at": now(), "kind": kind}
        entry.update(fields)
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def progress(self, kind: str, **fields) -> None:
        """Record a journal entry that counts as measurable progress."""
        self.state["counters"]["progress"] += 1
        self.log(kind, **fields)

    # -- helpers -----------------------------------------------------------
    def set_status(self, status: str, reason: str = "") -> None:
        prev = self.state.get("status")
        self.state["status"] = status
        self.state["status_reason"] = reason
        if status != STATUS_ACTIVE:
            self.state["counters"]["idle_blocks"] = 0
        self.log("status", **{"from": prev, "to": status, "reason": reason})

    def open_acceptance(self) -> list:
        return [a for a in self.state["acceptance"] if a["status"] != "met"]

    def last_verification(self) -> dict:
        vs = self.state.get("verifications") or []
        return vs[-1] if vs else None

    def primary_pass(self) -> dict:
        """The LATEST primary-verifier run, if and only if it passed.

        The newest run decides: an earlier lucky pass followed by failures is
        not proof. Skipping over newer failures to find a stale pass would let
        a flaky verifier satisfy `complete`."""
        label = self.state.get("verifier", {}).get("primary_label")
        for v in reversed(self.state.get("verifications") or []):
            if label is None or v.get("label") == label or v.get("primary"):
                return v if v["exit_code"] == 0 else None
        return None


def current_pointer(root: Path) -> Path:
    return root / "CURRENT"


def list_bundles(root: Path) -> list:
    if not root.is_dir():
        return []
    out = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "state.json").is_file():
            b = Bundle(root, child.name)
            try:
                _ = b.state
                out.append(b)
            except Exception:
                continue
    return out


def resolve_bundle(root: Path, slug: str = None, statuses=None) -> Bundle:
    """Pick the goal to operate on: explicit slug, CURRENT pointer, or the
    single matching bundle. Ambiguity is an error, never a guess."""
    if slug:
        b = Bundle(root, slug)
        if not b.exists():
            die(f"no goal bundle at {b.dir}")
        return b

    pointer = current_pointer(root)
    if pointer.is_file():
        name = pointer.read_text(encoding="utf-8").strip()
        b = Bundle(root, name)
        if b.exists() and (statuses is None or b.state["status"] in statuses):
            return b

    candidates = list_bundles(root)
    if statuses is not None:
        candidates = [b for b in candidates if b.state["status"] in statuses]
    if not candidates:
        die("no matching goal found. Run `ultragoal.py list` or create one with `new`.")
    if len(candidates) > 1:
        names = ", ".join(b.slug for b in candidates)
        die(f"ambiguous goal; pass --slug. Candidates: {names}")
    return candidates[0]


def active_bundles(root: Path) -> list:
    return [b for b in list_bundles(root) if b.state["status"] == STATUS_ACTIVE]


def die(msg: str, code: int = 1):
    print(f"ultragoal: {msg}", file=sys.stderr)
    sys.exit(code)


# --------------------------------------------------------------------------
# templates
# --------------------------------------------------------------------------

GOAL_TEMPLATE = """# Goal: {title}

**Slug:** `{slug}` · **Status:** see `state.json` · **Plan:** `plan.md`

## Outcome and why it matters
{objective}

## Baseline
<!-- What is true or failing right now. Observed, not assumed. -->

## Scope and non-goals
<!-- Surfaces that may change; what is explicitly out. -->

## Constraints and approval gates
<!-- Compatibility, safety, policy floors. Actions that need separate human approval. -->

## Acceptance conditions
<!-- Mirrored into state.json via `ultragoal.py accept`. Keep both in sync. -->

## Primary verifier, supporting checks, and proof boundary
<!-- The strongest check that can fail independently, and the surface it observes. -->

## Anti-cheating and stopping rules
- Do not weaken tests, narrow scope, hide failures, swap in mocks, or change
  benchmarks to make the verifier pass.
- Irreversible, public, shared, or costly actions require separate approval.

## Completion and blocker evidence
<!-- Exact commands, outputs, paths, screenshots required before `complete`. -->

## Decisions and assumptions
<!-- Recorded assumptions, resolved decisions, and their rationale. -->
"""

PLAN_TEMPLATE = """# Plan: {title}

**Current state:** drafted
**Strongest next action:** ground the contract, then activate.

## Phase: Research
Status: in_progress
Implementation tasks:
- [ ] Inspect canonical sources, baseline, and constraints

Verification tasks:
- [ ] Confirm the finish line and verifier are grounded

Evidence and artifact pointers:
-

Exit criteria: facts are sufficient to draft the contract and expose remaining decisions.
"""


def new_state(slug: str, title: str, objective: str, route: str, assurance: str,
              max_continues: int, deadline_minutes: int,
              autonomy: str = "full") -> dict:
    deadline = None
    if deadline_minutes:
        deadline = (datetime.now(timezone.utc) + timedelta(minutes=deadline_minutes)) \
            .replace(microsecond=0).isoformat()
    if autonomy == "full":
        if max_continues is None:
            max_continues = 0   # 0 = unbounded
        idle_limit = 0          # 0 = anti-spin pause off
        guard = False
    else:
        if max_continues is None:
            max_continues = DEFAULT_MAX_CONTINUES
        idle_limit = DEFAULT_IDLE_LIMIT
        guard = True
    return {
        "schema": SCHEMA,
        "slug": slug,
        "title": title,
        "objective": objective,
        "status": STATUS_DRAFTED,
        "status_reason": "",
        "created_at": now(),
        "updated_at": now(),
        "route": route,
        "assurance": assurance,
        "proof_boundary": "",
        "phase": {"name": "Research", "status": "in_progress", "next_action": ""},
        "acceptance": [],
        "verifier": {"primary_label": None},
        "verifications": [],
        "assurance_lanes": [],
        "lessons": [],
        "counters": {
            "progress": 0,
            "stop_blocks": 0,
            "idle_blocks": 0,
            "progress_at_last_block": 0,
            "attempts": 0,
        },
        "limits": {
            "max_continues": max_continues,
            "idle_limit": idle_limit,
            "deadline": deadline,
        },
        "guard": guard,
        "autonomy": autonomy,
        "decisions": [],
        "last_prompt_id": None,
    }


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_new(args):
    root = goals_root(args.dir)
    slug = args.slug or slugify(args.title or args.objective)
    b = Bundle(root, slug)
    if b.exists() and not args.force:
        die(f"goal `{slug}` already exists at {b.dir} (use --force to overwrite)")
    b.dir.mkdir(parents=True, exist_ok=True)
    b.evidence_dir.mkdir(exist_ok=True)
    title = args.title or args.objective[:80]
    b._state = new_state(slug, title, args.objective, args.route, args.assurance,
                         args.max_continues, args.deadline_minutes, args.autonomy)
    b.save()
    if not b.goal_path.exists() or args.force:
        b.goal_path.write_text(
            GOAL_TEMPLATE.format(title=title, slug=slug, objective=args.objective),
            encoding="utf-8")
    if not b.plan_path.exists() or args.force:
        b.plan_path.write_text(PLAN_TEMPLATE.format(title=title), encoding="utf-8")
    b.log("created", slug=slug, objective=args.objective)
    current_pointer(root).write_text(slug + "\n", encoding="utf-8")
    print(f"created goal `{slug}`")
    print(f"  goal:  {b.goal_path}")
    print(f"  plan:  {b.plan_path}")
    print(f"  state: {b.state_path}")
    if b.state.get("autonomy") == "full":
        print("Autonomy: FULL — unbounded continuations, no idle pause, guard off. "
              "The goal runs until complete or blocked.")
    print("Fill in goal.md and plan.md, then run `activate`.")


def cmd_activate(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug, statuses={STATUS_DRAFTED, STATUS_PAUSED,
                                                  STATUS_AWAITING, STATUS_WAITING,
                                                  STATUS_ACTIVE})
    if b.state["status"] == STATUS_ACTIVE:
        print(f"goal `{b.slug}` is already ACTIVE.")
        print(render_status(b))
        return
    problems = []
    if not b.goal_path.is_file():
        problems.append("goal.md is missing")
    if not b.plan_path.is_file():
        problems.append("plan.md is missing")
    if not b.state["acceptance"]:
        problems.append("no acceptance conditions recorded (`ultragoal.py accept \"...\"`)")
    if not b.state["verifier"].get("primary_label"):
        problems.append("no primary verifier declared (`ultragoal.py verifier \"<label>\"`)")
    if problems and not args.force:
        print("activation blocked:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(2)

    b.set_status(STATUS_ACTIVE, args.reason or "activated")
    b.state["counters"]["stop_blocks"] = 0
    b.state["counters"]["idle_blocks"] = 0
    b.save()
    current_pointer(root).write_text(b.slug + "\n", encoding="utf-8")

    hook_note = ""
    if not args.no_hooks:
        try:
            from install_hooks import install  # type: ignore
        except Exception:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            try:
                from install_hooks import install  # type: ignore
            except Exception:
                install = None
        if install:
            try:
                res = install(scope="project", script=Path(__file__).resolve(),
                              include_stop=True, include_guard=True)
                hook_note = f"\nsettings hooks (gate + resume + ask-guard): {res}"
            except BaseException as exc:  # never lose an activation over this
                hook_note = (f"\nsession-resume hook NOT installed: {exc}"
                             "\n  the goal is still active; resume manually with "
                             "`/ultragoal resume` in a new session")

    mc = b.state["limits"]["max_continues"]
    il = b.state["limits"]["idle_limit"]
    print(f"goal `{b.slug}` is ACTIVE.")
    if mc == 0 and il == 0:
        print("  stop gate armed: unbounded — runs until complete or an "
              "evidence-backed block")
    else:
        print(f"  stop gate armed: up to {mc or '∞'} continuations, "
              f"auto-pause after {il or '∞'} with no progress")
    print(f"  release with: complete | block | await | waiting | pause{hook_note}")


def cmd_status(args):
    root = goals_root(args.dir)
    if args.slug:
        bundles = [resolve_bundle(root, args.slug)]
    else:
        bundles = list_bundles(root)
        if not args.all:
            open_ = [b for b in bundles if b.state["status"] in OPEN_STATUSES]
            bundles = open_ or bundles
    if args.json:
        print(json.dumps([b.state for b in bundles], indent=2))
        return
    if not bundles:
        print("no goals found.")
        return
    for b in bundles:
        print(render_status(b))
        print()


def cmd_list(args):
    root = goals_root(args.dir)
    bundles = list_bundles(root)
    if args.json:
        print(json.dumps([
            {"slug": b.slug, "status": b.state["status"], "title": b.state["title"],
             "updated_at": b.state["updated_at"], "dir": str(b.dir)}
            for b in bundles], indent=2))
        return
    if not bundles:
        print(f"no goals under {root}")
        return
    for b in bundles:
        s = b.state
        print(f"{s['status']:<15} {b.slug:<32} {s['title'][:60]}")


def cmd_phase(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug, statuses=OPEN_STATUSES)
    b.state["phase"] = {
        "name": args.name,
        "status": args.status,
        "next_action": args.next or b.state["phase"].get("next_action", ""),
    }
    b.progress("phase", name=args.name, status=args.status, next_action=args.next or "")
    b.save()
    print(f"phase -> {args.name} ({args.status})")


def cmd_next(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug, statuses=OPEN_STATUSES)
    b.state["phase"]["next_action"] = args.text
    b.progress("next_action", text=args.text)
    b.save()
    print(f"next action: {args.text}")


def cmd_accept(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    ident = f"A{len(b.state['acceptance']) + 1}"
    b.state["acceptance"].append(
        {"id": ident, "text": args.text, "status": "open", "evidence": ""})
    b.progress("acceptance_added", id=ident, text=args.text)
    b.save()
    print(f"{ident}: {args.text}")


def cmd_met(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    for a in b.state["acceptance"]:
        if a["id"].lower() == args.id.lower():
            a["status"] = "met"
            a["evidence"] = args.evidence
            b.progress("acceptance_met", id=a["id"], evidence=args.evidence)
            b.save()
            print(f"{a['id']} met — {args.evidence}")
            return
    die(f"no acceptance condition `{args.id}`")


def cmd_unmet(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    for a in b.state["acceptance"]:
        if a["id"].lower() == args.id.lower():
            a["status"] = "open"
            a["evidence"] = args.why or ""
            b.progress("acceptance_unmet", id=a["id"], why=args.why or "")
            b.save()
            print(f"{a['id']} reopened")
            return
    die(f"no acceptance condition `{args.id}`")


def cmd_verifier(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    b.state["verifier"]["primary_label"] = args.label
    if args.proof_boundary:
        b.state["proof_boundary"] = args.proof_boundary
    b.progress("verifier_declared", label=args.label,
               proof_boundary=args.proof_boundary or "")
    b.save()
    print(f"primary verifier: {args.label}")


def cmd_verify(args):
    """Actually run a check and record its real exit code. Claims are not proof."""
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    if not args.command:
        die("nothing to run; pass the command after `--`")
    b.evidence_dir.mkdir(parents=True, exist_ok=True)
    label = args.label or " ".join(args.command)[:60]
    started = time.time()
    try:
        proc = subprocess.run(
            args.command, capture_output=True, text=True,
            timeout=args.timeout, cwd=str(project_root()),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + (exc.stderr or "") if isinstance(exc.stdout, str) else ""
        code = 124
        timed_out = True
    except FileNotFoundError as exc:
        out = str(exc)
        code = 127
        timed_out = False
    duration = round(time.time() - started, 2)

    index = len(b.state["verifications"]) + 1
    log_path = b.evidence_dir / f"verify-{index:03d}.log"
    log_path.write_text(out, encoding="utf-8")
    tail = "\n".join(out.splitlines()[-EVIDENCE_TAIL_LINES:])

    record = {
        "n": index,
        "at": now(),
        "label": label,
        "argv": args.command,
        "exit_code": code,
        "timed_out": timed_out,
        "duration_s": duration,
        "output_sha256": hashlib.sha256(out.encode("utf-8", "replace")).hexdigest()[:16],
        "log": str(log_path),
        "primary": bool(args.primary) or label == b.state["verifier"].get("primary_label"),
    }
    b.state["verifications"].append(record)
    if args.primary and not b.state["verifier"].get("primary_label"):
        b.state["verifier"]["primary_label"] = label
    b.progress("verify", **{k: record[k] for k in ("n", "label", "exit_code", "duration_s")})
    b.save()

    verdict = "PASS" if code == 0 else f"FAIL (exit {code})"
    print(f"[{verdict}] {label}  {duration}s  -> {log_path}")
    if tail:
        print("--- tail ---")
        print(tail)
    sys.exit(0 if code == 0 else 1)


def cmd_evidence(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    b.progress("evidence", text=args.text, ref=args.ref or "")
    b.save()
    print("evidence recorded")


def cmd_attempt(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    b.state["counters"]["attempts"] += 1
    b.progress("attempt",
               n=b.state["counters"]["attempts"],
               failure_class=args.failure,
               hypothesis=args.hypothesis,
               action=args.action,
               result=args.result,
               lesson=args.lesson or "")
    b.save()
    n = b.state["counters"]["attempts"]
    print(f"attempt #{n} recorded")
    if n >= 3:
        print("3+ attempts: return to Research/Plan and change the hypothesis "
              "before another pass.")


def cmd_lesson(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    b.state["lessons"].append({"at": now(), "text": args.text})
    b.progress("lesson", text=args.text)
    b.save()
    print("lesson recorded")


def cmd_assurance(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    if args.tier:
        b.state["assurance"] = args.tier
    if args.lane:
        b.state["assurance_lanes"].append({
            "at": now(), "name": args.lane,
            "finding": args.finding or "(clean)",
        })
    b.progress("assurance", tier=b.state["assurance"], lane=args.lane or "")
    b.save()
    print(f"assurance: {b.state['assurance']} "
          f"({len(b.state['assurance_lanes'])} lane(s) recorded)")


def cmd_route(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    b.state["route"] = args.route
    b.progress("route", route=args.route)
    b.save()
    print(f"route: {args.route}")


def _release(args, status, reason, extra=None):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug, statuses=OPEN_STATUSES)
    b.set_status(status, reason)
    if extra:
        b.state.update(extra)
    b.save()
    return b


def cmd_await(args):
    b = _release(args, STATUS_AWAITING, args.reason)
    print(f"goal `{b.slug}` is awaiting input — stop gate released.")
    print("Ask the user now (AskUserQuestion), then `resume` after they answer.")
    if b.state.get("autonomy") == "full":
        print("note: FULL AUTONOMY goal — await is reserved for an irreversible "
              "decision outside the goal's scope. If this is not one, `resume`, "
              "`decide` it, and keep moving.")


def cmd_waiting(args):
    b = _release(args, STATUS_WAITING, args.reason)
    if args.signal:
        b.state["status_reason"] += f" | wake signal: {args.signal}"
        b.save()
    print(f"goal `{b.slug}` is waiting — stop gate released.")
    print("Arm a Monitor, a background Bash task, or a scheduled wake before ending "
          "the turn; do not sleep-poll.")


def cmd_pause(args):
    b = _release(args, STATUS_PAUSED, args.reason or "paused by user")
    print(f"goal `{b.slug}` paused — stop gate released. Run `resume` to re-arm.")


def cmd_resume(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug,
                       statuses={STATUS_PAUSED, STATUS_AWAITING, STATUS_WAITING,
                                 STATUS_BLOCKED, STATUS_DRAFTED})
    b.set_status(STATUS_ACTIVE, args.reason or "resumed")
    b.state["counters"]["idle_blocks"] = 0
    if args.reset_budget:
        b.state["counters"]["stop_blocks"] = 0
    b.save()
    current_pointer(root).write_text(b.slug + "\n", encoding="utf-8")
    print(f"goal `{b.slug}` is ACTIVE again (stop gate armed).")
    print(render_status(b))


def cmd_block(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug, statuses=OPEN_STATUSES)
    if not args.evidence and not args.force:
        die("blocking needs evidence: --evidence \"<observed external blocker>\" "
            "(difficulty or uncertainty is not a blocker)")
    b.set_status(STATUS_BLOCKED, args.reason)
    b.log("blocked", reason=args.reason, evidence=args.evidence or "")
    b.state["phase"]["status"] = "blocked"
    b.save()
    print(f"goal `{b.slug}` BLOCKED — stop gate released.")
    print(f"  reason: {args.reason}")
    print(f"  smallest next action: {b.state['phase'].get('next_action') or '(record one)'}")


def completion_report(b: Bundle) -> dict:
    unmet = b.open_acceptance()
    primary = b.primary_pass()
    tier = b.state.get("assurance", "compact")
    lanes = b.state.get("assurance_lanes", [])
    needed_lanes = {"compact": 0, "focused": 1, "full": 2}.get(tier, 0)
    failures = []
    if not b.state["acceptance"]:
        failures.append("no acceptance conditions were ever recorded")
    if unmet:
        failures.append("unmet acceptance conditions: "
                        + ", ".join(f"{a['id']} ({a['text'][:48]})" for a in unmet))
    if primary is None:
        label = b.state["verifier"].get("primary_label") or "(none declared)"
        failures.append(f"no recorded passing run of the primary verifier `{label}` — "
                        "run it through `ultragoal.py verify --primary -- <command>`")
    if len(lanes) < needed_lanes:
        failures.append(f"assurance tier `{tier}` needs {needed_lanes} independent "
                        f"review lane(s); {len(lanes)} recorded")
    return {"ok": not failures, "failures": failures, "primary": primary,
            "lanes": lanes, "tier": tier}


def cmd_complete(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug, statuses=OPEN_STATUSES)
    report = completion_report(b)
    if not report["ok"] and not args.force:
        print("completion refused — missing proof:")
        for f in report["failures"]:
            print(f"  - {f}")
        print("\nFix the gap or, if the user explicitly accepted weaker proof, "
              "re-run with --force (it is recorded as a contract change).")
        sys.exit(2)
    b.set_status(STATUS_COMPLETE, args.reason or "completion proof satisfied")
    b.state["phase"]["status"] = "completed"
    b.log("complete", forced=bool(args.force), failures=report["failures"])
    b.save()
    print(f"goal `{b.slug}` COMPLETE — stop gate released.")
    if report["primary"]:
        p = report["primary"]
        print(f"  primary verifier: {p['label']} exit 0 at {p['at']} -> {p['log']}")
    if args.force and report["failures"]:
        print("  forced past: " + "; ".join(report["failures"]))


def cmd_decide(args):
    root = goals_root(args.dir)
    if args.slug:
        b = resolve_bundle(root, args.slug)
    else:
        # Decisions belong to the goal being gated, not to whatever bundle the
        # CURRENT pointer drifted to (e.g. a follow-up goal drafted mid-run).
        actives = active_bundles(root)
        b = (max(actives, key=lambda x: x.state["updated_at"])
             if actives else resolve_bundle(root, None))
    entry = {"at": now(), "text": args.text, "why": args.why or "",
             "reversible": not args.irreversible}
    b.state.setdefault("decisions", []).append(entry)
    b.progress("decision", **entry)
    b.save()
    print(f"decision #{len(b.state['decisions'])} recorded: {args.text}")


def cmd_report(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    rep = completion_report(b)
    if args.json:
        print(json.dumps({"state": b.state, "completion": rep}, indent=2, default=str))
        return
    print(render_status(b))
    print("\nCompletion readiness: " + ("READY" if rep["ok"] else "NOT READY"))
    for f in rep["failures"]:
        print(f"  - {f}")
    decisions = b.state.get("decisions") or []
    if decisions:
        print(f"\nAutonomous decisions to review ({len(decisions)}):")
        for i, d in enumerate(decisions, 1):
            tail = f" — {d['why']}" if d.get("why") else ""
            rev = "  [irreversible]" if not d.get("reversible", True) else ""
            print(f"  {i}. {d['text']}{tail}{rev}")


def cmd_config(args):
    root = goals_root(args.dir)
    b = resolve_bundle(root, args.slug)
    if args.autonomy is not None:
        b.state["autonomy"] = args.autonomy
        if args.autonomy == "full":
            b.state["guard"] = False
            b.state["limits"]["max_continues"] = 0
            b.state["limits"]["idle_limit"] = 0
        else:
            b.state["guard"] = True
            b.state["limits"]["max_continues"] = DEFAULT_MAX_CONTINUES
            b.state["limits"]["idle_limit"] = DEFAULT_IDLE_LIMIT
    if args.guard is not None:
        b.state["guard"] = args.guard == "on"
    if args.max_continues is not None:
        b.state["limits"]["max_continues"] = args.max_continues
    if args.idle_limit is not None:
        b.state["limits"]["idle_limit"] = args.idle_limit
    b.save()
    print(json.dumps({"autonomy": b.state.get("autonomy", "standard"),
                      "guard": b.state["guard"], **b.state["limits"]}, indent=2))


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def render_status(b: Bundle) -> str:
    s = b.state
    lines = [
        f"# Ultragoal `{b.slug}` — {s['status'].upper()}",
        f"Title: {s['title']}",
        f"Objective: {s['objective']}",
        f"Route: {s['route']} · Assurance: {s['assurance']} · "
        f"Autonomy: {s.get('autonomy', 'standard')} · "
        f"Proof boundary: {s.get('proof_boundary') or '(unset)'}",
        f"Bundle: {b.dir}",
        f"  goal.md   {b.goal_path}",
        f"  plan.md   {b.plan_path}",
    ]
    ph = s.get("phase", {})
    lines.append(f"Phase: {ph.get('name', '?')} ({ph.get('status', '?')})")
    lines.append(f"Next action: {ph.get('next_action') or '(none recorded)'}")

    if s["acceptance"]:
        lines.append("Acceptance:")
        for a in s["acceptance"]:
            mark = "x" if a["status"] == "met" else " "
            ev = f"  [{a['evidence']}]" if a.get("evidence") else ""
            lines.append(f"  [{mark}] {a['id']} {a['text']}{ev}")
    else:
        lines.append("Acceptance: (none recorded)")

    last = b.last_verification()
    if last:
        verdict = "PASS" if last["exit_code"] == 0 else f"FAIL exit {last['exit_code']}"
        lines.append(f"Last verifier: {last['label']} — {verdict} ({last['at']}) "
                     f"-> {last['log']}")
    else:
        lines.append(f"Last verifier: none run. Primary is "
                     f"`{s['verifier'].get('primary_label') or 'undeclared'}`.")

    if s.get("assurance_lanes"):
        lines.append(f"Assurance lanes: "
                     + "; ".join(l["name"] for l in s["assurance_lanes"]))
    if s.get("lessons"):
        lines.append("Lessons:")
        for l in s["lessons"][-4:]:
            lines.append(f"  - {l['text']}")
    if s.get("decisions"):
        lines.append(f"Autonomous decisions ({len(s['decisions'])}, "
                     "full list in `report`):")
        for d in s["decisions"][-4:]:
            lines.append(f"  - {d['text']}")

    c, lim = s["counters"], s["limits"]
    mc = lim["max_continues"] or "∞"
    il = lim["idle_limit"] or "∞"
    lines.append(f"Counters: continuations {c['stop_blocks']}/{mc} · "
                 f"idle {c['idle_blocks']}/{il} · "
                 f"attempts {c['attempts']} · progress marks {c['progress']}")
    if s.get("status_reason"):
        lines.append(f"Status note: {s['status_reason']}")
    return "\n".join(lines)


def gate_reason(b: Bundle, script: str) -> str:
    s = b.state
    ph = s.get("phase", {})
    unmet = b.open_acceptance()
    last = b.last_verification()
    ug = f"python3 {script}"

    lines = [
        f"ULTRAGOAL `{b.slug}` IS ACTIVE — do not end the turn yet.",
        "",
        f"Outcome: {s['objective']}",
        f"Contract: {b.goal_path}",
        f"Plan: {b.plan_path}",
        f"Phase: {ph.get('name', '?')} ({ph.get('status', '?')})",
        f"Strongest next action: {ph.get('next_action') or '(none recorded — record one now)'}",
    ]
    if unmet:
        lines.append("Unmet acceptance conditions:")
        for a in unmet:
            lines.append(f"  - {a['id']} {a['text']}")
    else:
        lines.append("All acceptance conditions are marked met.")

    if last:
        verdict = "PASS" if last["exit_code"] == 0 else f"FAIL (exit {last['exit_code']})"
        lines.append(f"Last verifier run: {last['label']} — {verdict} -> {last['log']}")
    else:
        lines.append("No verifier has been run yet. A claim is not proof; run it.")

    rep = completion_report(b)
    if rep["ok"]:
        lines += ["", "Completion proof is satisfied. Close the goal now:",
                  f"  {ug} complete"]
    else:
        lines += ["", "Completion is blocked by:"]
        lines += [f"  - {f}" for f in rep["failures"]]

    c, lim = s["counters"], s["limits"]
    lines += [
        "",
        "Take the next real step: advance the plan, run the verifier, record "
        "evidence, or repair a failure. Every continuation must add evidence, "
        "reduce uncertainty, move the verifier, or change the hypothesis.",
    ]
    mc, il = lim["max_continues"], lim["idle_limit"]
    if mc == 0 and il == 0:
        budget_line = (f"Continuation {c['stop_blocks']} — unbounded: the goal "
                       "runs until complete or blocked. The user can stop it at "
                       "any time with Esc or `/ultragoal pause`.")
    else:
        budget_line = (f"Continuation {c['stop_blocks']}/{mc or '∞'}; "
                       f"{c['idle_blocks']}/{il or '∞'} consecutive continuations "
                       "with no recorded progress (the gate auto-pauses at a "
                       "reached limit). The user can stop this at any time with "
                       "Esc or `/ultragoal pause`.")
    if s.get("autonomy", "standard") == "full":
        lines += [
            "",
            "FULL AUTONOMY: the user is away by design and reviews only after "
            "completion. Do not use AskUserQuestion, and do not stop to ask "
            "anything. For any open question inside the goal's scope, make the "
            "call yourself, record it with "
            f"`{ug} decide \"<choice>\" --why \"<reason>\"`, and keep moving. "
            "Self-heal: on failure, diagnose, change one thing, re-verify; after "
            "three distinct evidence-backed approaches fail, ledger them and take "
            "the strongest next option — do not wait for the user.",
            "",
            "Release the gate only with:",
            f"  {ug} complete                   # proof satisfied",
            f"  {ug} block \"<blocker>\" --evidence \"<ref>\"   # truly external, evidence-backed",
            f"  {ug} waiting \"<what>\" --signal \"<how you get woken>\"",
            "",
            budget_line,
        ]
    else:
        lines += [
            "",
            "Release the gate deliberately with exactly one of:",
            f"  {ug} complete                   # proof satisfied",
            f"  {ug} block \"<blocker>\" --evidence \"<ref>\"   # external blocker, evidence-backed",
            f"  {ug} await \"<decision needed>\"  # a consequential human decision",
            f"  {ug} waiting \"<what>\" --signal \"<how you get woken>\"",
            f"  {ug} pause \"<reason>\"           # stand down",
            "",
            budget_line,
        ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# hooks
# --------------------------------------------------------------------------

def read_hook_payload() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def hook_stop(payload: dict) -> None:
    root = goals_root(None)
    actives = active_bundles(root)
    if not actives:
        sys.exit(0)
    b = max(actives, key=lambda x: x.state["updated_at"])
    script = str(Path(__file__).resolve())
    c, lim = b.state["counters"], b.state["limits"]

    # A single logical stop can reach us through more than one registration
    # (skill frontmatter + settings.json). Count it once.
    prompt_id = payload.get("prompt_id")
    duplicate = prompt_id is not None and prompt_id == b.state.get("last_prompt_id")

    if not duplicate:
        if c["progress"] == c["progress_at_last_block"]:
            c["idle_blocks"] += 1
        else:
            c["idle_blocks"] = 0
        c["progress_at_last_block"] = c["progress"]
        c["stop_blocks"] += 1
        b.state["last_prompt_id"] = prompt_id

    deadline = lim.get("deadline")
    if deadline and now() >= deadline:
        b.set_status(STATUS_PAUSED, f"wall-clock deadline {deadline} reached")
        b.save()
        emit({"systemMessage": f"Ultragoal `{b.slug}` auto-paused: deadline reached. "
                               f"Resume with `/ultragoal resume`."})
        sys.exit(0)

    if lim["idle_limit"] > 0 and c["idle_blocks"] >= lim["idle_limit"]:
        idle = c["idle_blocks"]  # set_status clears the counter; report the real one
        b.set_status(STATUS_PAUSED,
                     f"auto-paused after {idle} continuations with no recorded progress")
        b.save()
        emit({"systemMessage": f"Ultragoal `{b.slug}` auto-paused: "
                               f"{idle} continuations added no evidence, "
                               "verifier movement, or plan change. "
                               "Review the plan, then `/ultragoal resume`."})
        sys.exit(0)

    if lim["max_continues"] > 0 and c["stop_blocks"] > lim["max_continues"]:
        b.set_status(STATUS_PAUSED,
                     f"auto-paused at the {lim['max_continues']}-continuation budget")
        b.save()
        emit({"systemMessage": f"Ultragoal `{b.slug}` auto-paused: continuation budget "
                               f"({lim['max_continues']}) exhausted. Resume with "
                               "`/ultragoal resume` to grant more."})
        sys.exit(0)

    b.save()
    b.log("gate", decision="block", stop_blocks=c["stop_blocks"],
          idle_blocks=c["idle_blocks"])
    # Claude Code honors Stop blocks ONLY as top-level decision/reason
    # (live-verified); a hookSpecificOutput "Stop" variant does not exist in
    # the host schema and is discarded as a non-blocking error.
    emit({"decision": "block", "reason": gate_reason(b, script)})
    sys.exit(0)


def hook_session_start(payload: dict) -> None:
    root = goals_root(None)
    bundles = [b for b in list_bundles(root) if b.state["status"] in OPEN_STATUSES]
    if not bundles:
        sys.exit(0)
    script = str(Path(__file__).resolve())
    parts = [
        "An Ultragoal is still open in this project. Reconcile it before starting "
        "unrelated work, and do not ask the user to re-supply context that is "
        "already on disk.",
        "",
    ]
    for b in bundles:
        parts.append(render_status(b))
        parts.append("")
    active = [b for b in bundles if b.state["status"] == STATUS_ACTIVE]
    parts += [
        "Resume sequence: read goal.md and plan.md, refresh mutable reality "
        "(repo, tests, CI, runtime, external systems), reconcile recorded state "
        "against what is actually true now, restore exactly one in-progress "
        "phase, then take the smallest safe next action inside the existing "
        "contract.",
        f"State commands: python3 {script} status | resume | complete | block | "
        "await | waiting | pause",
    ]
    if active:
        parts.append(
            f"NOTE: `{active[0].slug}` is ACTIVE, so the stop gate is armed for this "
            "session and turns will not end until it is released.")
    # SessionStart is the mirror image of Stop: the host reads
    # additionalContext ONLY from hookSpecificOutput (live-verified); a
    # top-level additionalContext is stripped by schema validation.
    emit({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(parts),
        },
        "systemMessage": f"Ultragoal: {len(bundles)} open goal(s) restored from "
                         f"{root}",
    })
    sys.exit(0)


# Narrow, high-confidence anti-cheating patterns. Everything here targets the
# goal's own proof surface; ordinary development is untouched.
DENY_BASH = [
    (r"\bgit\s+push\b.*(--force\b|(?<!-)-f\b)(?!.*--force-with-lease)",
     "force-push while an Ultragoal is active: it can destroy the evidence trail. "
     "Use --force-with-lease, or pause the goal first."),
    (r"\bgit\s+(commit|push)\b.*--no-verify\b",
     "--no-verify skips the repository's own checks, which is exactly the "
     "'weaken the proof' failure the goal contract forbids."),
    (r"\brm\b[^|;&]*\.claude/goals/",
     "deleting the Ultragoal bundle would erase the goal's evidence. "
     "Use `pause` or `block` instead."),
]

ASK_BASH = [
    (r"\brm\b\s+(-[a-zA-Z]*\s+)*[^|;&]*(tests?|spec|__tests__)\b",
     "removing test files while a goal is active"),
    (r"\bgit\s+checkout\b\s+--\s+.*(tests?|spec)/",
     "reverting tests while a goal is active"),
]

ASK_EDIT_CONTENT = [
    (r"@pytest\.mark\.(skip|xfail)", "skipping or xfailing a test"),
    (r"\b(it|test|describe)\.skip\s*\(", "skipping a test"),
    (r"\bxit\s*\(|\bxdescribe\s*\(", "skipping a test"),
    (r"#\[ignore\]", "ignoring a test"),
    (r"\bt\.Skip\s*\(", "skipping a test"),
    (r"\.skip\s*\(\s*['\"]", "skipping a test"),
]

CONTRACT_HEADINGS = re.compile(
    r"(Acceptance conditions|Primary verifier|Completion and blocker evidence|"
    r"Anti-cheating and stopping rules)", re.I)


def hook_pre_tool(payload: dict) -> None:
    root = goals_root(None)
    actives = active_bundles(root)
    if not actives:
        sys.exit(0)
    b = max(actives, key=lambda x: x.state["updated_at"])
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}

    def decide(kind, reason):
        emit({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": kind,
            "permissionDecisionReason":
                f"Ultragoal `{b.slug}`: {reason}",
        }})
        sys.exit(0)

    # Full autonomy bans mid-run questions mechanically, not just in prose.
    # This runs even with the guard off; `UG await` first releases the gate
    # (status leaves ACTIVE), so the sanctioned irreversible-out-of-scope ask
    # is still possible after an explicit await.
    if tool == "AskUserQuestion" and b.state.get("autonomy") == "full":
        decide("deny",
               "this goal runs at FULL AUTONOMY — the user is away and reviews "
               "after completion. Decide it yourself, record it with "
               "`ultragoal.py decide \"<choice>\" --why \"<reason>\"`, and keep "
               "moving. For an irreversible decision outside the goal's scope, "
               "run `ultragoal.py await \"<decision>\"` first, then ask.")

    if not b.state.get("guard", False):
        sys.exit(0)

    if tool in ("Bash", "PowerShell"):
        cmd = ti.get("command") or ""
        for pattern, reason in DENY_BASH:
            if re.search(pattern, cmd):
                decide("deny", reason + " (disable with `ultragoal.py config --guard off`)")
        for pattern, what in ASK_BASH:
            if re.search(pattern, cmd):
                decide("ask", f"{what}. Confirm this is a real fix and not a way to "
                              "make the verifier pass.")
        sys.exit(0)

    if tool in ("Edit", "Write", "NotebookEdit"):
        path = str(ti.get("file_path") or ti.get("notebook_path") or "")
        new = str(ti.get("new_string") or ti.get("content") or "")
        old = str(ti.get("old_string") or "")

        if path.endswith("goal.md") and ".claude/goals/" in path.replace("\\", "/"):
            if CONTRACT_HEADINGS.search(old) or CONTRACT_HEADINGS.search(new):
                decide("ask", "this edit touches the goal's acceptance conditions, "
                              "verifier, or completion proof. Changing the contract "
                              "is a deliberate decision, not an implementation detail.")
            sys.exit(0)

        added = new if not old else new.replace(old, "")
        for pattern, what in ASK_EDIT_CONTENT:
            if re.search(pattern, added):
                decide("ask", f"{what} in `{Path(path).name}`. If the test is wrong, "
                              "fix it; if the feature is incomplete, keep it failing.")
    sys.exit(0)


def cmd_hook(args):
    payload = read_hook_payload()
    try:
        if args.event == "stop":
            hook_stop(payload)
        elif args.event == "session-start":
            hook_session_start(payload)
        elif args.event == "pre-tool":
            hook_pre_tool(payload)
    except SystemExit:
        raise
    except Exception:
        # Never wedge a session over goal bookkeeping.
        sys.exit(0)
    sys.exit(0)


def cmd_install_hooks(args):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from install_hooks import install, uninstall  # type: ignore
    scope = "user" if args.user else "project"
    if args.uninstall:
        print(uninstall(scope=scope))
    else:
        print(install(scope=scope, script=Path(__file__).resolve(),
                      include_stop=args.include_stop))


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def cmd_selftest(args):
    import tempfile
    failures = []

    def check(name, cond, detail=""):
        print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))
        if not cond:
            failures.append(name)

    def run(argv, stdin=None):
        return subprocess.run(
            [sys.executable, str(Path(__file__).resolve())] + argv,
            capture_output=True, text=True, input=stdin, env=env, cwd=tmp)

    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env["ULTRAGOAL_DIR"] = str(Path(tmp) / ".claude" / "goals")
        env.pop("CLAUDE_PROJECT_DIR", None)

        print("ultragoal selftest")
        print("-- lifecycle")
        r = run(["new", "--slug", "demo", "--objective", "Make the smoke check pass",
                 "--title", "Demo goal", "--autonomy", "standard"])
        check("new creates a bundle", r.returncode == 0, r.stderr)
        check("goal.md written", (Path(env["ULTRAGOAL_DIR"]) / "demo" / "goal.md").is_file())
        check("plan.md written", (Path(env["ULTRAGOAL_DIR"]) / "demo" / "plan.md").is_file())

        r = run(["activate", "--no-hooks"])
        check("activation refuses without acceptance + verifier", r.returncode == 2, r.stdout)

        run(["accept", "The smoke check exits 0"])
        run(["verifier", "smoke"])
        r = run(["activate", "--no-hooks"])
        check("activation succeeds once grounded", r.returncode == 0, r.stderr)

        print("-- stop gate")
        payload = json.dumps({"hook_event_name": "Stop", "prompt_id": "p1"})
        r = run(["hook", "stop"], stdin=payload)
        out = json.loads(r.stdout or "{}")
        check("gate blocks with host-honored top-level decision",
              out.get("decision") == "block" and "hookSpecificOutput" not in out,
              r.stdout[:200])
        check("gate reason names the release commands",
              "complete" in r.stdout and "block" in r.stdout and "await" in r.stdout)

        r2 = run(["hook", "stop"], stdin=payload)
        s = json.loads((Path(env["ULTRAGOAL_DIR"]) / "demo" / "state.json").read_text())
        check("duplicate prompt_id counted once", s["counters"]["stop_blocks"] == 1,
              str(s["counters"]))

        print("-- completion proof")
        r = run(["complete"])
        check("complete refused without a passing verifier", r.returncode == 2, r.stdout)

        run(["verify", "--primary", "--label", "smoke", "--", "true"])
        r = run(["complete"])
        check("complete still refused with unmet acceptance", r.returncode == 2, r.stdout)

        run(["met", "A1", "--evidence", "verify-001.log"])
        r = run(["complete"])
        check("complete accepted with full proof", r.returncode == 0, r.stdout + r.stderr)

        r = run(["hook", "stop"], stdin=json.dumps({"prompt_id": "p9"}))
        check("gate releases once complete", r.stdout.strip() == "", r.stdout[:200])

        print("-- failing verifier is recorded honestly")
        run(["new", "--slug", "fail", "--objective", "x", "--autonomy", "standard"])
        run(["accept", "y", "--slug", "fail"])
        run(["verifier", "f", "--slug", "fail"])
        r = run(["verify", "--slug", "fail", "--label", "f", "--primary", "--", "false"])
        check("failing check reports non-zero", r.returncode == 1, r.stdout)
        s = json.loads((Path(env["ULTRAGOAL_DIR"]) / "fail" / "state.json").read_text())
        check("failing check stored with real exit code",
              s["verifications"][0]["exit_code"] != 0, str(s["verifications"]))

        print("-- anti-spin auto-pause")
        run(["activate", "--slug", "fail", "--no-hooks"])
        # The first continuation follows real work, so it is not idle; the
        # limit counts consecutive continuations that add nothing after it.
        for i in range(DEFAULT_IDLE_LIMIT + 1):
            r = run(["hook", "stop"], stdin=json.dumps({"prompt_id": f"spin{i}"}))
        s = json.loads((Path(env["ULTRAGOAL_DIR"]) / "fail" / "state.json").read_text())
        check("auto-pauses after idle continuations", s["status"] == STATUS_PAUSED,
              s["status"])
        check("auto-pause reports the real idle count",
              f"{DEFAULT_IDLE_LIMIT} continuations" in r.stdout, r.stdout[:200])
        r = run(["hook", "stop"], stdin=json.dumps({"prompt_id": "spin-after"}))
        check("gate releases once auto-paused", r.stdout.strip() == "", r.stdout[:200])

        print("-- session-start resume")
        r = run(["hook", "session-start"], stdin=json.dumps({"source": "startup"}))
        out = json.loads(r.stdout or "{}")
        ctx = (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
        check("session-start injects via hookSpecificOutput (host contract)",
              (out.get("hookSpecificOutput") or {}).get("hookEventName") == "SessionStart"
              and "Ultragoal" in ctx, r.stdout[:200])

        print("-- pre-tool guard")
        run(["resume", "--slug", "fail"])
        guard_in = json.dumps({"tool_name": "Bash",
                               "tool_input": {"command": "git push --force origin main"}})
        r = run(["hook", "pre-tool"], stdin=guard_in)
        dec = json.loads(r.stdout or "{}").get("hookSpecificOutput", {})
        check("guard denies force-push", dec.get("permissionDecision") == "deny", r.stdout[:200])

        ok_in = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push -u origin feat"}})
        r = run(["hook", "pre-tool"], stdin=ok_in)
        check("guard ignores ordinary pushes", r.stdout.strip() == "", r.stdout[:200])

        skip_in = json.dumps({"tool_name": "Edit", "tool_input": {
            "file_path": "/repo/tests/test_a.py", "old_string": "def test_a():",
            "new_string": "@pytest.mark.skip\ndef test_a():"}})
        r = run(["hook", "pre-tool"], stdin=skip_in)
        dec = json.loads(r.stdout or "{}").get("hookSpecificOutput", {})
        check("guard asks before skipping a test",
              dec.get("permissionDecision") == "ask", r.stdout[:200])

        print("-- full autonomy (the default)")
        run(["new", "--slug", "auto", "--objective", "z"])
        run(["accept", "w", "--slug", "auto"])
        run(["verifier", "v", "--slug", "auto"])
        run(["activate", "--slug", "auto", "--no-hooks"])
        s = json.loads((Path(env["ULTRAGOAL_DIR"]) / "auto" / "state.json").read_text())
        check("full autonomy is the default: guard off, unbounded limits",
              s.get("autonomy") == "full" and s["guard"] is False
              and s["limits"]["max_continues"] == 0
              and s["limits"]["idle_limit"] == 0, str(s["limits"]))
        for i in range(DEFAULT_IDLE_LIMIT + 3):
            r = run(["hook", "stop"], stdin=json.dumps({"prompt_id": f"auto{i}"}))
        s = json.loads((Path(env["ULTRAGOAL_DIR"]) / "auto" / "state.json").read_text())
        check("gate never auto-pauses under full autonomy",
              s["status"] == STATUS_ACTIVE, s["status"])
        out = json.loads(r.stdout or "{}")
        check("full-autonomy gate keeps blocking (top-level decision)",
              out.get("decision") == "block", r.stdout[:200])
        check("full-autonomy reason directs deciding, not asking",
              "FULL AUTONOMY" in r.stdout and "decide" in r.stdout, r.stdout[:200])

        ask_in = json.dumps({"tool_name": "AskUserQuestion", "tool_input": {}})
        r = run(["hook", "pre-tool"], stdin=ask_in)
        dec = json.loads(r.stdout or "{}").get("hookSpecificOutput", {})
        check("AskUserQuestion denied mid-run even with guard off",
              dec.get("permissionDecision") == "deny", r.stdout[:200])

        run(["new", "--slug", "draftb", "--objective", "q"])  # CURRENT -> draftb
        r = run(["decide", "prefer sqlite", "--why", "single writer"])
        check("decide records an autonomous decision", r.returncode == 0, r.stderr)
        s = json.loads((Path(env["ULTRAGOAL_DIR"]) / "auto" / "state.json").read_text())
        check("decide targets the ACTIVE goal, not the CURRENT pointer",
              any(d.get("text") == "prefer sqlite" for d in s.get("decisions", [])),
              str(s.get("decisions")))
        r = run(["report", "--slug", "auto"])
        check("report lists decisions for post-run review",
              "Autonomous decisions to review (1)" in r.stdout, r.stdout[:300])

        run(["new", "--slug", "capped", "--objective", "c", "--max-continues", "50"])
        s = json.loads((Path(env["ULTRAGOAL_DIR"]) / "capped" / "state.json").read_text())
        check("explicit --max-continues survives full autonomy",
              s["limits"]["max_continues"] == 50 and s.get("autonomy") == "full",
              str(s["limits"]))
        run(["pause", "--slug", "auto"])

        print("-- supervised budget and latest-run proof")
        run(["new", "--slug", "bud", "--objective", "b", "--autonomy", "standard",
             "--max-continues", "1"])
        run(["accept", "y", "--slug", "bud"])
        run(["verifier", "bv", "--slug", "bud"])
        run(["activate", "--slug", "bud", "--no-hooks"])
        for i in range(2):
            r = run(["hook", "stop"], stdin=json.dumps({"prompt_id": f"bud{i}"}))
        s = json.loads((Path(env["ULTRAGOAL_DIR"]) / "bud" / "state.json").read_text())
        check("standard budget exhausts and auto-pauses",
              s["status"] == STATUS_PAUSED and "budget" in r.stdout, s["status"])

        run(["new", "--slug", "flaky", "--objective", "f"])
        run(["accept", "z", "--slug", "flaky"])
        run(["verifier", "fv", "--slug", "flaky"])
        run(["verify", "--slug", "flaky", "--primary", "--label", "fv", "--", "true"])
        run(["verify", "--slug", "flaky", "--primary", "--label", "fv", "--", "false"])
        run(["met", "A1", "--slug", "flaky", "--evidence", "x"])
        r = run(["complete", "--slug", "flaky"])
        check("stale earlier pass does not satisfy completion",
              r.returncode == 2, r.stdout[:200])

        print("-- pre-autonomy bundle compatibility")
        leg = Path(env["ULTRAGOAL_DIR"]) / "legacy"
        (leg / "evidence").mkdir(parents=True, exist_ok=True)
        (leg / "goal.md").write_text("# legacy\n", encoding="utf-8")
        (leg / "plan.md").write_text("# p\n", encoding="utf-8")
        legacy_state = {
            "schema": 1, "slug": "legacy", "title": "legacy", "objective": "old",
            "status": "active", "status_reason": "", "route": "light",
            "assurance": "compact", "proof_boundary": "",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "9999-01-01T00:00:00+00:00",
            "phase": {"name": "Research", "status": "in_progress", "next_action": ""},
            "acceptance": [], "verifier": {"primary_label": "t"},
            "verifications": [], "assurance_lanes": [], "lessons": [],
            "counters": {"progress": 0, "stop_blocks": 0, "idle_blocks": 0,
                         "progress_at_last_block": 0, "attempts": 0},
            "limits": {"max_continues": 40, "idle_limit": 3, "deadline": None},
            "guard": True, "last_prompt_id": None,
        }
        (leg / "state.json").write_text(json.dumps(legacy_state), encoding="utf-8")
        r = run(["hook", "stop"], stdin=json.dumps({"prompt_id": "leg1"}))
        out = json.loads(r.stdout or "{}")
        check("pre-autonomy bundle still gates in supervised mode",
              out.get("decision") == "block" and "/40" in out.get("reason", ""),
              r.stdout[:200])
        run(["pause", "--slug", "legacy"])

        print("-- resilience")
        (Path(env["ULTRAGOAL_DIR"]) / "demo" / "state.json").write_text("{not json")
        r = run(["hook", "stop"], stdin=json.dumps({"prompt_id": "z"}))
        check("corrupt state never wedges the session", r.returncode == 0, r.stderr[:200])

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s): " + ", ".join(failures))
        sys.exit(1)
    print("all checks passed")


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ultragoal.py",
        description="Durable goal state and enforcement for Claude Code.")
    p.add_argument("--dir", help="goal root (default <repo>/.claude/goals)")
    p.add_argument("--slug", help="operate on this goal")

    # Repeated on every subcommand so `--slug` works before or after the verb.
    # SUPPRESS keeps an omitted child flag from clobbering the parent's value.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default=argparse.SUPPRESS)
    common.add_argument("--slug", default=argparse.SUPPRESS)

    sub = p.add_subparsers(dest="cmd", required=True)

    def sub_parser(name, **kw):
        return sub.add_parser(name, parents=[common], **kw)

    n = sub_parser("new", help="create a goal bundle (status: drafted)")
    n.add_argument("--objective", required=True,
                   help="one-sentence observable outcome")
    n.add_argument("--title")
    n.add_argument("--route", default="light", choices=["light", "medium", "heavy"])
    n.add_argument("--assurance", default="compact",
                   choices=["compact", "focused", "full"])
    n.add_argument("--max-continues", type=int, default=None,
                   help="continuation budget; default: unbounded (full autonomy) "
                        f"or {DEFAULT_MAX_CONTINUES} (standard). Explicit values "
                        "are honored in either mode; 0 = unbounded")
    n.add_argument("--deadline-minutes", type=int, default=0)
    n.add_argument("--autonomy", default="full", choices=["standard", "full"],
                   help="full (default): unbounded continuations, no idle pause, "
                        "guard off — runs until complete or blocked; "
                        "standard: supervised, bounded gate with guard")
    n.add_argument("--force", action="store_true")
    n.set_defaults(func=cmd_new)

    a = sub_parser("activate", help="arm the stop gate")
    a.add_argument("--reason", default="")
    a.add_argument("--no-hooks", action="store_true",
                   help="skip installing the session-resume hook")
    a.add_argument("--force", action="store_true", help="activate despite gaps")
    a.set_defaults(func=cmd_activate)

    s = sub_parser("status", help="render goal state")
    s.add_argument("--json", action="store_true")
    s.add_argument("--all", action="store_true")
    s.set_defaults(func=cmd_status)

    l = sub_parser("list")
    l.add_argument("--json", action="store_true")
    l.set_defaults(func=cmd_list)

    ph = sub_parser("phase", help="set the current phase")
    ph.add_argument("name")
    ph.add_argument("--status", default="in_progress",
                    choices=["pending", "in_progress", "waiting", "blocked", "completed"])
    ph.add_argument("--next", help="strongest next action")
    ph.set_defaults(func=cmd_phase)

    nx = sub_parser("next", help="record the strongest next action")
    nx.add_argument("text")
    nx.set_defaults(func=cmd_next)

    ac = sub_parser("accept", help="add an acceptance condition")
    ac.add_argument("text")
    ac.set_defaults(func=cmd_accept)

    m = sub_parser("met", help="mark an acceptance condition met")
    m.add_argument("id")
    m.add_argument("--evidence", required=True)
    m.set_defaults(func=cmd_met)

    um = sub_parser("unmet", help="reopen an acceptance condition")
    um.add_argument("id")
    um.add_argument("--why")
    um.set_defaults(func=cmd_unmet)

    vd = sub_parser("verifier", help="declare the primary verifier")
    vd.add_argument("label")
    vd.add_argument("--proof-boundary", help="surface, account/role, environment")
    vd.set_defaults(func=cmd_verifier)

    v = sub_parser("verify", help="run a check and record its real exit code")
    v.add_argument("--label")
    v.add_argument("--primary", action="store_true")
    v.add_argument("--timeout", type=int, default=1800)
    v.add_argument("command", nargs=argparse.REMAINDER)
    v.set_defaults(func=cmd_verify)

    e = sub_parser("evidence", help="record an evidence note")
    e.add_argument("text")
    e.add_argument("--ref", help="path, URL, or command")
    e.set_defaults(func=cmd_evidence)

    dc = sub_parser("decide", help="record an autonomous decision and keep moving")
    dc.add_argument("text")
    dc.add_argument("--why", default="")
    dc.add_argument("--irreversible", action="store_true",
                    help="flag for prominent post-run review")
    dc.set_defaults(func=cmd_decide)

    at = sub_parser("attempt", help="record a failed attempt in the ledger")
    at.add_argument("--failure", required=True,
                    help="mechanical | hypothesis | specification | approval | external")
    at.add_argument("--hypothesis", required=True)
    at.add_argument("--action", required=True)
    at.add_argument("--result", required=True)
    at.add_argument("--lesson")
    at.set_defaults(func=cmd_attempt)

    ls = sub_parser("lesson", help="record a task-local lesson")
    ls.add_argument("text")
    ls.set_defaults(func=cmd_lesson)

    asr = sub_parser("assurance", help="set the tier or record a review lane")
    asr.add_argument("tier", nargs="?", choices=["compact", "focused", "full"])
    asr.add_argument("--lane")
    asr.add_argument("--finding")
    asr.set_defaults(func=cmd_assurance)

    rt = sub_parser("route")
    rt.add_argument("route", choices=["light", "medium", "heavy"])
    rt.set_defaults(func=cmd_route)

    aw = sub_parser("await", help="release the gate for a human decision")
    aw.add_argument("reason")
    aw.set_defaults(func=cmd_await)

    wt = sub_parser("waiting", help="release the gate for an external wait")
    wt.add_argument("reason")
    wt.add_argument("--signal", help="how this session gets woken")
    wt.set_defaults(func=cmd_waiting)

    pa = sub_parser("pause")
    pa.add_argument("reason", nargs="?", default="")
    pa.set_defaults(func=cmd_pause)

    re_ = sub_parser("resume", help="re-arm the stop gate")
    re_.add_argument("--reason", default="")
    re_.add_argument("--reset-budget", action="store_true")
    re_.set_defaults(func=cmd_resume)

    bl = sub_parser("block", help="stop on an evidence-backed external blocker")
    bl.add_argument("reason")
    bl.add_argument("--evidence")
    bl.add_argument("--force", action="store_true")
    bl.set_defaults(func=cmd_block)

    co = sub_parser("complete", help="close the goal (proof enforced)")
    co.add_argument("--reason", default="")
    co.add_argument("--force", action="store_true",
                    help="close despite missing proof; recorded as a contract change")
    co.set_defaults(func=cmd_complete)

    rp = sub_parser("report", help="status plus completion readiness")
    rp.add_argument("--json", action="store_true")
    rp.set_defaults(func=cmd_report)

    cf = sub_parser("config")
    cf.add_argument("--autonomy", choices=["standard", "full"])
    cf.add_argument("--guard", choices=["on", "off"])
    cf.add_argument("--max-continues", type=int)
    cf.add_argument("--idle-limit", type=int)
    cf.set_defaults(func=cmd_config)

    hk = sub_parser("hook", help="hook entrypoint (reads JSON on stdin)")
    hk.add_argument("event", choices=["stop", "session-start", "pre-tool"])
    hk.set_defaults(func=cmd_hook)

    ih = sub_parser("install-hooks")
    ih.add_argument("--user", action="store_true", help="write to ~/.claude/settings.json")
    ih.add_argument("--uninstall", action="store_true")
    ih.add_argument("--include-stop", action="store_true",
                    help="also register the Stop gate in settings (frontmatter already does)")
    ih.set_defaults(func=cmd_install_hooks)

    st = sub_parser("selftest", help="end-to-end check in a temp directory")
    st.set_defaults(func=cmd_selftest)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "verify" and args.command and args.command[0] == "--":
        args.command = args.command[1:]
    args.func(args)


if __name__ == "__main__":
    main()
