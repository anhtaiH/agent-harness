#!/usr/bin/env python3
"""Pre-tool policy gate for harness sessions.

Reads a tool-call payload on stdin and decides allow / ask / deny.

Output contract (stdout, exit 0):
  Claude Code PreToolUse `hookSpecificOutput.permissionDecision` JSON. Other
  callers (verify-gates, the opencode plugin, the Cursor shim) parse the same
  JSON, so this file is the single policy engine for every surface.

Decisions:
  deny  hard stops in every mode: sensitive files, exfiltration, remote code
        piped into a shell, production-affecting actions, protected-branch
        force pushes, connector writes without a matching write intent.
  ask   destructive-but-legitimate local commands in run mode.
  allow everything else; yolo mode converts ask into allow.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HOME = str(Path.home())
ROOT = Path(os.environ.get("AGENT_HARNESS_ROOT", Path.home() / ".agent-harness" / "default")).expanduser()

SENSITIVE_PATH_RE = re.compile(
    r"(^|[/\s\"'=])("
    r"\.env(?:\.[^/\s\"']*)?|\.npmrc|\.netrc|\.pgpass|\.ssh/[^/\s\"']+|"
    r"\.config/gh/hosts\.yml|\.docker/config\.json|\.kube/config|"
    r"\.aws/(?:credentials|config)|\.git-credentials|"
    r"\.codex/auth\.json|\.claude/\.credentials\.json|\.gemini/oauth_creds\.json|"
    r"(?:credential|credentials|secret|secrets)\.(?:json|ya?ml|toml|env)|"
    r"(?:id_rsa|id_ecdsa|id_ed25519)(?:\.pub)?|[^/\s\"']*\.pem|[^/\s\"']*\.p12|[^/\s\"']*\.keystore"
    r")(?=$|[/\s\"'])",
    re.I,
)
# Piping a remote body into an interpreter, or executing a process-substituted download.
REMOTE_EXEC_RE = re.compile(
    r"(\b(?:curl|wget|fetch)\b[^|;&\n]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b"
    r"|\b(?:ba|z|da|k)?sh\s+<\(\s*(?:curl|wget)\b"
    r"|\b(?:curl|wget)\b[^|;&\n]*\|\s*(?:sudo\s+)?(?:python3?|node|perl|ruby)\b)",
    re.I,
)
LEAK_TOOL_RE = re.compile(
    r"\b(base64|tar|zip|curl|wget|scp|rsync|nc|pbcopy|xclip)\b[^\n]*(\.codex|\.claude|\.gemini|\.ssh|\.aws|\.env|\.netrc|\.npmrc|credential|secrets?)",
    re.I,
)
PROD_RE = re.compile(
    r"\b(gh\s+pr\s+merge|gh\s+release\s+(create|upload|edit)"
    r"|kubectl\s+(apply|delete|scale|drain|rollout)|helm\s+(upgrade|install|uninstall|rollback)"
    r"|terraform\s+(apply|destroy)|pulumi\s+(up|destroy)"
    r"|npm\s+publish|pnpm\s+publish|yarn\s+(npm\s+)?publish|cargo\s+publish|gem\s+push|twine\s+upload"
    r"|docker\s+push|flyctl\s+deploy|fly\s+deploy|vercel\s+(deploy\s+)?--prod|netlify\s+deploy[^\n]*--prod"
    r"|aws\s+\S+\s+(delete|terminate|remove)\S*|gcloud\s+\S+\s+delete|az\s+\S+\s+delete)\b",
    re.I,
)
FORCE_PUSH_RE = re.compile(r"\bgit\s+push\b[^\n]*(\s--force(?:-with-lease|-if-includes)?\b|\s-f\b)", re.I)
PROTECTED_BRANCH_RE = re.compile(r"\b(main|master|release[/\w.-]*|production|prod)\b", re.I)
DESTRUCTIVE_RE = re.compile(
    r"(\brm\s+(-[A-Za-z]*[rR][A-Za-z]*f|-[A-Za-z]*f[A-Za-z]*[rR])[A-Za-z]*\b"
    r"|\bsudo\s+rm\b|\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-[a-z]*x?[df]{1,2}\b"
    r"|\bfind\s+[^\n]+\s+-delete\b|\bchmod\s+(-R\s+)?777\s+/"
    r"|\bdd\s+[^\n]*of=/dev/|\bmkfs(\.\w+)?\b|\bshutdown\b|\breboot\b)",
    re.I,
)
CONNECTOR_WRITE_RE = re.compile(r"(update|create|delete|comment|send|schedule|transition|post|publish|merge|close)", re.I)
READ_ONLY_CONNECTOR_RE = re.compile(r"(fetch|get|list|read|search|query|view|find|lookup|download)", re.I)
CONNECTOR_PROVIDERS = ["github", "slack", "jira", "confluence", "atlassian"]
# Command-execution patterns only apply to tools that execute shell commands.
# Content-carrying tools (Write bodies, Agent prompts, MCP payloads) may
# legitimately MENTION dangerous commands; those commands are gated at
# execution time when a shell tool actually runs them.
EXEC_TOOL_RE = re.compile(r"(bash|shell|terminal|cmd|exec)", re.I)


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


def session_mode(payload: dict[str, Any]) -> str:
    mode = os.environ.get("AGENT_HARNESS_MODE")
    if mode:
        return mode
    cwd = str(payload.get("cwd") or os.getcwd())
    try:
        active = json.loads((ROOT / "state" / "active-tasks.json").read_text())
    except Exception:
        return "run"
    best = ""
    best_mode = "run"
    for repo_path, entry in active.items():
        if not isinstance(entry, dict):
            continue
        if (cwd == repo_path or cwd.startswith(repo_path.rstrip("/") + "/")) and len(repo_path) > len(best):
            best = repo_path
            best_mode = str(entry.get("mode", "run"))
    return best_mode


def active_intent_exists(provider: str, operation_hint: str) -> bool:
    task_id = os.environ.get("AGENT_HARNESS_TASK_ID")
    task_dirs: list[Path] = []
    if task_id:
        task_dirs.append(ROOT / "tasks" / task_id)
    else:
        try:
            active = json.loads((ROOT / "state" / "active-tasks.json").read_text())
            for entry in active.values():
                if isinstance(entry, dict) and entry.get("task_id"):
                    task_dirs.append(ROOT / "tasks" / str(entry["task_id"]))
        except Exception:
            return False
    for task_dir in task_dirs:
        intents = task_dir / "external-writes" / "intents"
        if not intents.exists():
            continue
        for path in intents.glob("*.json"):
            try:
                data = json.loads(path.read_text())
            except Exception:
                continue
            if data.get("provider") == provider and operation_hint in str(data.get("operation", "")):
                return True
    return False


def emit(decision: str, reason: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    if decision == "deny":
        print(reason, file=sys.stderr)
    return 0


def decide(payload: dict[str, Any]) -> tuple[str, str]:
    text = command_text(payload)
    name = tool_name(payload)
    mode = session_mode(payload)
    normalized = text.replace("~/", HOME + "/").replace("$HOME/", HOME + "/")
    is_exec_tool = bool(EXEC_TOOL_RE.search(name)) or not name

    if SENSITIVE_PATH_RE.search(normalized):
        return "deny", "Agent harness: blocked access to a credential or secret file path. Use scoped config or ask the human."
    if is_exec_tool and REMOTE_EXEC_RE.search(normalized):
        return "deny", "Agent harness: blocked piping remote content into an interpreter. Download, inspect, then run explicitly."
    if is_exec_tool and LEAK_TOOL_RE.search(normalized):
        return "deny", "Agent harness: blocked a possible secret-exfiltration pattern."
    if is_exec_tool and PROD_RE.search(normalized):
        return "deny", "Agent harness: production-affecting command requires explicit human-owned scope (see task packet stop conditions)."
    if is_exec_tool and FORCE_PUSH_RE.search(normalized):
        if PROTECTED_BRANCH_RE.search(normalized):
            return "deny", "Agent harness: force-push to a protected branch is blocked."
        if mode != "yolo":
            return "ask", "Agent harness: force-push to a feature branch. Confirm before proceeding."
    if is_exec_tool and DESTRUCTIVE_RE.search(normalized):
        if mode != "yolo":
            return "ask", "Agent harness: destructive local command outside yolo mode. Confirm before proceeding."

    lowered_name = name.lower()
    if any(provider in lowered_name for provider in CONNECTOR_PROVIDERS) and CONNECTOR_WRITE_RE.search(lowered_name):
        if READ_ONLY_CONNECTOR_RE.search(lowered_name):
            return "allow", ""
        provider = next(p for p in CONNECTOR_PROVIDERS if p in lowered_name)
        provider = "confluence" if provider == "atlassian" else provider
        operation = "review-comment" if "review" in lowered_name and "comment" in lowered_name else "comment" if "comment" in lowered_name else "update"
        if not active_intent_exists(provider, operation):
            return "deny", "Agent harness: connector write requires a matching external_write_intent for the active task."
    return "allow", ""


def main() -> int:
    payload = load_payload()
    try:
        decision, reason = decide(payload)
    except Exception as exc:  # fail-open with a trace so a policy bug never bricks the session
        print(f"agent-harness pre-tool-policy internal error: {exc}", file=sys.stderr)
        return 0
    if decision == "allow":
        return 0
    return emit(decision, reason)


if __name__ == "__main__":
    raise SystemExit(main())
