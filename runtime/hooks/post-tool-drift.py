#!/usr/bin/env python3
"""Warn when tracked files changed during a harness-managed repo session."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_HARNESS_ROOT", Path.home() / ".agent-harness" / "default")).expanduser()


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


def main() -> int:
    cwd = Path(os.getcwd()).resolve()
    repo = next((path for path in configured_repos() if cwd == path or path in cwd.parents), None)
    if repo is None:
        return 0
    result = subprocess.run(["git", "-C", str(repo), "status", "--short", "--untracked-files=no"], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if result.stdout.strip():
        print("Tracked repo changes are present. Keep the diff scoped and verify before done.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
