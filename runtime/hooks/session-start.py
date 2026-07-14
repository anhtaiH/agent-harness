#!/usr/bin/env python3
"""SessionStart hook: inject a compact harness capsule as session context.

Stdout from a SessionStart hook is added to the agent's context, so this stays
short: where the runtime lives, whether the current repo has an active task to
resume, and the two rules that matter (task packets, evidence before done).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_HARNESS_ROOT", Path.home() / ".agent-harness" / "default")).expanduser()


def payload_cwd() -> str:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return str(data.get("cwd") or os.getcwd())
    except Exception:
        return os.getcwd()


def active_task(cwd: str) -> dict | None:
    try:
        active = json.loads((ROOT / "state" / "active-tasks.json").read_text())
    except Exception:
        return None
    best_path = ""
    best = None
    for repo_path, entry in active.items():
        if not isinstance(entry, dict) or not entry.get("task_id"):
            continue
        if (cwd == repo_path or cwd.startswith(repo_path.rstrip("/") + "/")) and len(repo_path) > len(best_path):
            best_path = repo_path
            best = entry
    return best


def main() -> int:
    lines = [f"Agent Harness is installed (runtime: {ROOT})."]
    entry = active_task(payload_cwd())
    if entry:
        lines.append(
            f"Active harness task for this repo: {entry['task_id']} (mode: {entry.get('mode', 'run')}). "
            "Resume it via the resume_task MCP tool or `harness resume` before starting new work."
        )
    else:
        lines.append("For non-trivial work: start a harness task packet first (start_task MCP tool or `harness start`).")
    lines.append("Finish through evidence: write_evidence -> evidence_doctor -> finish_task. Draft-only PR reviews; external writes need a write intent.")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
