#!/usr/bin/env python3
"""PostToolUse drift check: remind the agent when a configured repo checkout is dirty.

Throttled to one reminder per THROTTLE_MINUTES per repo so it nudges without
polluting context after every tool call.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_HARNESS_ROOT") or Path(__file__).resolve().parents[1]).expanduser()
THROTTLE_MINUTES = 10


def configured_repos() -> list[Path]:
    try:
        config = json.loads((ROOT / "config.json").read_text())
    except Exception:
        return []
    repos = []
    for item in config.get("repos", {}).values():
        if isinstance(item, dict) and item.get("path"):
            repos.append(Path(item["path"]).expanduser().resolve())
    return repos


def throttled(repo: Path) -> bool:
    stamp = ROOT / "state" / "drift-stamps" / (repo.name + ".stamp")
    try:
        if time.time() - stamp.stat().st_mtime < THROTTLE_MINUTES * 60:
            return True
    except OSError:
        pass
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(str(time.time()))
    except OSError:
        pass
    return False


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    cwd = Path(str(payload.get("cwd") or os.getcwd())).resolve()
    repo = next((path for path in configured_repos() if cwd == path or path in cwd.parents), None)
    if repo is None:
        return 0
    # Throttle first (stamp before probing) so a hung git never re-fires every event.
    if throttled(repo):
        return 0
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "status", "--short", "--untracked-files=no"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0
    changed = len(result.stdout.strip().splitlines())
    if changed:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": (
                            f"Agent harness drift check: {changed} tracked file(s) modified in {repo.name}. "
                            "Keep the diff scoped to the task packet and record progress checkpoints."
                        ),
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
