#!/usr/bin/env python3
"""Register Ultragoal's hooks in a Claude Code settings file.

The skill's frontmatter arms the Stop gate and the guard for the session that
invokes `/ultragoal`, but frontmatter hooks die with the session and their
locator depends on the install layout. `activate` therefore installs all three
hooks here with ABSOLUTE paths — Stop (the gate), SessionStart (resume after
restart, `/clear`, or compaction — the one hook frontmatter can never supply),
and PreToolUse (the AskUserQuestion block plus the optional guard) — so an
active goal keeps its machinery across sessions regardless of layout.

Default scope is the project's `.claude/settings.local.json` (personal, not
committed). `--user` writes `~/.claude/settings.json` instead.

Every entry this writes is identified by `ultragoal.py` appearing in its
command, so `uninstall` removes exactly what it added and nothing else.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MARKER = "ultragoal.py"


def project_root() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except Exception:
        pass
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path.cwd()


def settings_path(scope: str) -> Path:
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    return project_root() / ".claude" / "settings.local.json"


def load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ultragoal: {path} is not valid JSON ({exc}); "
                         "fix or move it, then retry.")


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        backup = path.with_suffix(path.suffix + ".ultragoal-bak")
        if not backup.exists():
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _entry(script: Path, event_arg: str) -> dict:
    return {"type": "command",
            "command": f'python3 "{script}" hook {event_arg}',
            "timeout": 30}


def _has_ours(group_list: list) -> bool:
    for group in group_list:
        for hook in group.get("hooks", []):
            if MARKER in str(hook.get("command", "")):
                return True
    return False


def _strip_ours(group_list: list) -> list:
    kept = []
    for group in group_list:
        hooks = [h for h in group.get("hooks", [])
                 if MARKER not in str(h.get("command", ""))]
        if hooks:
            group = dict(group, hooks=hooks)
            kept.append(group)
        elif not group.get("hooks"):
            kept.append(group)
    return kept


def git_exclude(path: Path) -> str:
    """Keep settings.local.json out of git without touching tracked files."""
    root = project_root()
    exclude = root / ".git" / "info" / "exclude"
    rel = str(path.relative_to(root)) if str(path).startswith(str(root)) else None
    if rel is None or not exclude.parent.is_dir():
        return ""
    try:
        check = subprocess.run(["git", "check-ignore", "-q", rel],
                               cwd=str(root), capture_output=True, timeout=10)
        if check.returncode == 0:
            return ""
        current = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        if rel in current:
            return ""
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write(f"\n# added by ultragoal\n{rel}\n")
        return f" (added {rel} to .git/info/exclude)"
    except Exception:
        return ""


def install(scope: str = "project", script: Path = None,
            include_stop: bool = False, include_guard: bool = False) -> str:
    script = Path(script or (Path(__file__).resolve().parent / "ultragoal.py")).resolve()
    if not script.is_file():
        raise SystemExit(f"ultragoal: cannot find {script}")

    path = settings_path(scope)
    data = load(path)
    hooks = data.setdefault("hooks", {})
    added = []

    sess = hooks.setdefault("SessionStart", [])
    if not _has_ours(sess):
        sess.append({"matcher": "startup|resume|clear|compact",
                     "hooks": [_entry(script, "session-start")]})
        added.append("SessionStart")

    if include_stop:
        stop = hooks.setdefault("Stop", [])
        if not _has_ours(stop):
            stop.append({"hooks": [_entry(script, "stop")]})
            added.append("Stop")

    if include_guard:
        pre = hooks.setdefault("PreToolUse", [])
        if not _has_ours(pre):
            pre.append({"matcher": "Bash|Edit|Write|NotebookEdit|AskUserQuestion",
                        "hooks": [_entry(script, "pre-tool")]})
            added.append("PreToolUse")

    rule = f"Bash(python3 \"{script}\" *)"
    perms = data.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])
    for candidate in (rule, f"Bash(python3 {script} *)"):
        if candidate not in allow:
            allow.append(candidate)
            added.append("permission allow rule")

    save(path, data)
    note = git_exclude(path) if scope == "project" else ""
    if not added:
        return f"already installed in {path}"
    return f"installed {', '.join(sorted(set(added)))} in {path}{note}"


def uninstall(scope: str = "project") -> str:
    path = settings_path(scope)
    if not path.is_file():
        return f"nothing to remove: {path} does not exist"
    data = load(path)
    removed = []

    for event, groups in list((data.get("hooks") or {}).items()):
        if _has_ours(groups):
            kept = _strip_ours(groups)
            if kept:
                data["hooks"][event] = kept
            else:
                del data["hooks"][event]
            removed.append(event)
    if data.get("hooks") == {}:
        del data["hooks"]

    allow = (data.get("permissions") or {}).get("allow")
    if allow:
        kept = [r for r in allow if MARKER not in r]
        if len(kept) != len(allow):
            removed.append("permission allow rule")
            if kept:
                data["permissions"]["allow"] = kept
            else:
                del data["permissions"]["allow"]
                if not data["permissions"]:
                    del data["permissions"]

    save(path, data)
    if not removed:
        return f"no ultragoal entries found in {path}"
    return f"removed {', '.join(sorted(set(removed)))} from {path}"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    scope = "user" if "--user" in argv else "project"
    if "--uninstall" in argv:
        print(uninstall(scope=scope))
        return
    print(install(scope=scope,
                  include_stop="--include-stop" in argv,
                  include_guard="--include-guard" in argv))


if __name__ == "__main__":
    main()
