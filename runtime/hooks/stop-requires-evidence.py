#!/usr/bin/env python3
"""Stop gate: block ending a session while an active harness task lacks evidence.

Works in two modes:
  1. Wrapper mode: AGENT_HARNESS_TASK_ID + AGENT_HARNESS_REQUIRE_EVIDENCE env vars
     (set by the ah-* launchers).
  2. Hook mode: no env needed. Reads the session cwd from the hook payload and
     matches it against state/active-tasks.json, so the gate fires in plain
     Claude Code / Cursor sessions started from a configured repo.

Loop safety: honors stop_hook_active from the payload, ignores stale active
tasks (> ACTIVE_TASK_TTL_HOURS), and AGENT_HARNESS_SKIP_STOP_GATE=1 disables it.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("AGENT_HARNESS_ROOT") or Path(__file__).resolve().parents[1]).expanduser()
ACTIVE_TASK_TTL_HOURS = 24
REQUIRED_HEADINGS = ["Summary", "Positive Proof", "Negative Proof", "Commands Run", "Skipped Checks", "Diff Risk Notes", "Memory Candidates"]


def section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.M)
    return match.group(1).strip() if match else ""


def validate(text: str) -> list[str]:
    failures: list[str] = []
    for heading in REQUIRED_HEADINGS:
        if not section(text, heading):
            failures.append(f"missing {heading}")
    if "What changed or what was learned." in text:
        failures.append("evidence template is not filled")
    return failures


def load_payload() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def fresh(entry: dict[str, Any]) -> bool:
    try:
        updated = datetime.fromisoformat(str(entry.get("updated_at", "")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - updated < timedelta(hours=ACTIVE_TASK_TTL_HOURS)


def active_tasks_for_cwd(cwd: str) -> list[str]:
    """All fresh tasks whose repo path contains cwd, longest-prefix first.

    Both sides are realpath-normalized so a repo under a symlinked path (e.g.
    /tmp -> /private/tmp) still matches the resolved path stored at task start.
    """
    try:
        active = json.loads((ROOT / "state" / "active-tasks.json").read_text())
    except Exception:
        return []
    cwd = os.path.realpath(cwd)
    matches = []
    for key, entry in active.items():
        if not isinstance(entry, dict) or not fresh(entry):
            continue
        repo_path = os.path.realpath(str(entry.get("repo_path") or key))
        task_id = str(entry.get("task_id") or key)
        if cwd == repo_path or cwd.startswith(repo_path.rstrip("/") + "/"):
            matches.append((len(repo_path), task_id))
    return [task_id for _, task_id in sorted(matches, reverse=True)]


def block(reason: str) -> int:
    print(json.dumps({"decision": "block", "reason": reason}))
    print(reason, file=sys.stderr)
    return 0


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--validate-file":
        failures = validate(Path(sys.argv[2]).read_text(errors="replace"))
        if failures:
            print("Evidence file is incomplete: " + "; ".join(failures), file=sys.stderr)
            return 2
        return 0

    if os.environ.get("AGENT_HARNESS_SKIP_STOP_GATE") == "1":
        return 0
    payload = load_payload()
    if payload.get("stop_hook_active"):
        return 0

    # The env task id binds only when the wrapper explicitly demanded evidence
    # (interactive wrapper sessions). Print-mode / peer-lane runs export the
    # task id for artifact routing but must not be stop-gated.
    candidates: list[str] = []
    if os.environ.get("AGENT_HARNESS_REQUIRE_EVIDENCE") == "1":
        env_task = os.environ.get("AGENT_HARNESS_TASK_ID")
        if not env_task:
            print("AGENT_HARNESS_REQUIRE_EVIDENCE=1 but AGENT_HARNESS_TASK_ID is unset.", file=sys.stderr)
            return 2
        candidates = [env_task]
    else:
        candidates = active_tasks_for_cwd(str(payload.get("cwd") or os.getcwd()))
    # Block on the first active task (that was actually started) lacking complete
    # evidence — so a second task in the same repo can't hide the first's gate.
    for task_id in candidates:
        if not (ROOT / "tasks" / task_id / "task.json").exists():
            continue
        evidence = ROOT / "tasks" / task_id / "evidence.md"
        if not evidence.exists():
            return block(
                f"Harness task {task_id} is active but has no evidence.md. "
                f"Write evidence (write_evidence or `harness evidence write {task_id} ...`) and call finish_task, "
                "or finish/abandon the task explicitly before stopping."
            )
        failures = validate(evidence.read_text(errors="replace"))
        if failures:
            return block(f"Evidence for task {task_id} is incomplete: " + "; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
