#!/usr/bin/env python3
"""Generic pre-tool guard for local harness sessions."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HOME = str(Path.home())
MODE = os.environ.get("AGENT_HARNESS_MODE", "run")

SENSITIVE_PATH_RE = re.compile(
    r"(^|[/\s\"'])("
    r"\.env(?:\.[^/\s\"']*)?|\.npmrc|\.netrc|\.ssh/[^/\s\"']+|"
    r"\.config/gh/hosts\.yml|\.docker/config\.json|"
    r"(?:credential|credentials|secret|secrets)\.(?:json|ya?ml|toml|env)"
    r")(?=$|[/\s\"'])",
    re.I,
)
SENSITIVE_HOME_FRAGMENTS = [
    ".codex/auth.json",
    ".codex/config.toml",
    ".claude/settings.json",
    ".aws/" + "credentials",
    ".git-" + "credentials",
]
LEAK_TOOL_RE = re.compile(r"\b(base64|tar|zip|curl|wget|scp|rsync|pbcopy)\b.*(\.codex|\.claude|\.ssh|\.env|credential|sensitive)", re.I | re.S)
PROD_RE = re.compile(r"\b(gh\s+pr\s+merge|kubectl\s+(apply|delete)|helm\s+upgrade|terraform\s+(apply|destroy)|pulumi\s+(up|destroy))\b", re.I)
DESTRUCTIVE_RE = re.compile(r"\b(rm\s+-rf|git\s+reset\s+--hard|git\s+clean\s+-xdf|git\s+checkout\s+--|find\s+.+\s+-delete)\b", re.I | re.S)
CONNECTOR_WRITE_RE = re.compile(r"(update|create|delete|comment|send|schedule|transition|post|publish)", re.I)
READ_ONLY_CONNECTOR_RE = re.compile(r"(fetch|get|list|read|search|query|view|find|lookup)", re.I)


def load_payload() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(iter_strings(item))
        return out
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(iter_strings(item))
        return out
    return []


def command_text(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input") or payload.get("toolInput") or payload.get("input") or payload
    return "\n".join(iter_strings(tool_input))


def tool_name(payload: dict[str, Any]) -> str:
    return str(payload.get("tool_name") or payload.get("toolName") or payload.get("name") or "")


def active_intent_exists(provider: str, operation_hint: str) -> bool:
    task_id = os.environ.get("AGENT_HARNESS_TASK_ID")
    root = Path(os.environ.get("AGENT_HARNESS_ROOT", Path.home() / ".agent-harness" / "default")).expanduser()
    if not task_id:
        return False
    intents = root / "tasks" / task_id / "external-writes" / "intents"
    if not intents.exists():
        return False
    for path in intents.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        if data.get("provider") == provider and operation_hint in str(data.get("operation", "")):
            return True
    return False


def block(reason: str) -> int:
    print(json.dumps({"decision": "block", "reason": reason}))
    print(reason, file=sys.stderr)
    return 2


def main() -> int:
    payload = load_payload()
    text = command_text(payload)
    name = tool_name(payload)
    normalized = text.replace("~/", HOME + "/").replace("$HOME/", HOME + "/")
    if any(fragment in normalized for fragment in SENSITIVE_HOME_FRAGMENTS) or SENSITIVE_PATH_RE.search(normalized):
        return block("Blocked by agent harness: sensitive file path.")
    if LEAK_TOOL_RE.search(normalized):
        return block("Blocked by agent harness: possible sensitive data exfiltration.")
    if PROD_RE.search(normalized):
        return block("Blocked by agent harness: production-affecting command requires explicit human-owned scope.")
    if MODE != "yolo" and DESTRUCTIVE_RE.search(normalized):
        return block("Blocked by agent harness: destructive local command outside yolo mode.")
    lowered_name = name.lower()
    if ("github" in lowered_name or "slack" in lowered_name or "jira" in lowered_name or "confluence" in lowered_name or "atlassian" in lowered_name) and CONNECTOR_WRITE_RE.search(lowered_name):
        if READ_ONLY_CONNECTOR_RE.search(lowered_name):
            return 0
        provider = "github" if "github" in lowered_name else "slack" if "slack" in lowered_name else "jira" if "jira" in lowered_name else "confluence"
        operation = "review-comment" if "review" in lowered_name and "comment" in lowered_name else "comment" if "comment" in lowered_name else "update"
        if not active_intent_exists(provider, operation):
            return block("Blocked by agent harness: connector write requires a matching external_write_intent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
