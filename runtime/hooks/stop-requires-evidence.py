#!/usr/bin/env python3
"""Require evidence before a guarded task stops."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_HARNESS_ROOT", Path.home() / ".agent-harness" / "default")).expanduser()


def section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)", text, re.M)
    return match.group(1).strip() if match else ""


def validate(text: str) -> list[str]:
    failures: list[str] = []
    for heading in ["Summary", "Positive Proof", "Negative Proof", "Commands Run", "Skipped Checks", "Diff Risk Notes", "Memory Candidates"]:
        if not section(text, heading):
            failures.append(f"missing {heading}")
    if "What changed or what was learned." in text:
        failures.append("evidence template is not filled")
    return failures


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--validate-file":
        failures = validate(Path(sys.argv[2]).read_text(errors="replace"))
        if failures:
            print("Evidence file is incomplete: " + "; ".join(failures), file=sys.stderr)
            return 2
        return 0
    if os.environ.get("AGENT_HARNESS_REQUIRE_EVIDENCE") != "1":
        return 0
    task_id = os.environ.get("AGENT_HARNESS_TASK_ID")
    if not task_id:
        print("AGENT_HARNESS_REQUIRE_EVIDENCE=1 but AGENT_HARNESS_TASK_ID is unset.", file=sys.stderr)
        return 2
    evidence = ROOT / "tasks" / task_id / "evidence.md"
    if not evidence.exists():
        print(f"Evidence required before stopping: {evidence}", file=sys.stderr)
        return 2
    failures = validate(evidence.read_text(errors="replace"))
    if failures:
        print("Evidence file is incomplete: " + "; ".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
