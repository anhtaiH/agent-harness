#!/usr/bin/env python3
"""UserPromptSubmit gate: reject prompts that contain raw secret material.

Blocking here keeps credentials out of the session transcript, out of model
context, and out of any downstream tool call. Patterns come from
policy/redaction-patterns.json with conservative built-in defaults.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("AGENT_HARNESS_ROOT", Path.home() / ".agent-harness" / "default")).expanduser()
PATTERNS = ROOT / "policy" / "redaction-patterns.json"
DEFAULTS = [
    r"gh[pousr]_[0-9A-Za-z_]{24,}",
    r"sk-[0-9A-Za-z]{24,}",
    r"sk-ant-[0-9A-Za-z_\-]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"xox[baprs]-[0-9A-Za-z-]{24,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----",
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    r"(api[_-]?key|token|password)\s*[:=]\s*[\"']?[0-9A-Za-z._=+\-/]{24,}",
]


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


def load_patterns() -> list[re.Pattern[str]]:
    try:
        raw = json.loads(PATTERNS.read_text())
        if not isinstance(raw, list) or not raw:
            raw = DEFAULTS
    except Exception:
        raw = DEFAULTS
    return [re.compile(str(item), re.I) for item in raw]


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
        text = str(payload.get("prompt")) if isinstance(payload, dict) and payload.get("prompt") else "\n".join(iter_strings(payload))
    except Exception:
        text = raw
    if any(pattern.search(text) for pattern in load_patterns()):
        reason = (
            "Agent harness blocked this prompt: it appears to contain a raw credential or secret. "
            "Remove the secret (reference it by name or use env/keychain indirection) and resend."
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        print(reason, file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
