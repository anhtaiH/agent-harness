#!/usr/bin/env python3
"""Cursor hooks bridge: translate Cursor hook payloads to the shared policy engine.

Wired into ~/.cursor/hooks.json for beforeShellExecution and beforeMCPExecution.
Cursor sends JSON on stdin and expects {"permission": "allow"|"deny"|"ask"}
(optionally with userMessage/agentMessage) on stdout.

The actual decision comes from pre-tool-policy.py, so Claude Code, Cursor,
opencode, and verify-gates all enforce one policy.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    event = str(payload.get("hook_event_name") or payload.get("event") or "")
    if "MCP" in event or payload.get("tool_name"):
        tool_name = str(payload.get("tool_name") or "mcp")
        tool_input = payload.get("tool_input") or payload.get("params") or {}
    else:
        tool_name = "Bash"
        tool_input = {"command": str(payload.get("command") or "")}

    translated = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": str(payload.get("cwd") or payload.get("workspace_root") or os.getcwd()),
    }
    decision = "allow"
    reason = ""
    try:
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "pre-tool-policy.py")],
            input=json.dumps(translated),
            text=True,
            capture_output=True,
            timeout=15,
            env=os.environ.copy(),
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            data = json.loads(line)
            specific = data.get("hookSpecificOutput", {})
            if specific.get("permissionDecision") in {"allow", "ask", "deny"}:
                decision = specific["permissionDecision"]
                reason = str(specific.get("permissionDecisionReason") or "")
                break
    except Exception:
        decision = "allow"  # fail open on bridge errors

    response: dict[str, object] = {"permission": decision}
    if reason:
        response["userMessage"] = reason
        response["agentMessage"] = reason
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
