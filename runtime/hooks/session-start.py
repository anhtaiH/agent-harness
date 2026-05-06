#!/usr/bin/env python3
"""Emit a compact startup capsule for harness-aware sessions."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_HARNESS_ROOT", Path.home() / ".agent-harness" / "default")).expanduser()
INDEX = ROOT / "memory" / "index.md"

print(f"Agent harness root: {ROOT}")
if INDEX.exists():
    lines = INDEX.read_text(errors="replace").splitlines()
    print(f"Memory index: {INDEX} ({min(len(lines), 200)} startup lines available)")
print("Use task packets, one writer, source-backed context, and evidence before done.")
