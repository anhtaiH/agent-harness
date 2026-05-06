#!/usr/bin/env python3
"""Generic local agent harness.

This module is intentionally dependency-light. It owns the reusable local
runtime contract: task packets, evidence, generated profiles, MCP backend
commands, peer-agent wrappers, PR-review artifacts, external-write intents,
memory inboxes, and local metrics.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fnmatch
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

SOURCE_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = SOURCE_ROOT / "runtime"
DEFAULT_WORKSPACE = os.environ.get("AGENT_HARNESS_WORKSPACE", "default")
DEFAULT_RUNTIME_ROOT = Path.home() / ".agent-harness" / DEFAULT_WORKSPACE
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,95}$")
SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,199}$")
RISK_LEVELS = {"auto", "green", "yellow", "red", "low", "medium", "high", "critical"}
MODES = {"plan", "run", "yolo"}
WRITE_PROVIDERS = {"confluence", "jira", "slack", "github"}
WRITE_OPERATIONS = {"create", "update", "comment", "review-comment", "send", "schedule", "transition", "maintenance"}
MCP_TOOLS = [
    "start_task",
    "resume_task",
    "status",
    "read_artifact",
    "record_progress",
    "write_evidence",
    "evidence_doctor",
    "finish_task",
    "agent_capabilities",
    "agent_run",
    "review_plan",
    "review_run",
    "review_status",
    "review_synthesize",
    "pr_review_start",
    "pr_review_run",
    "pr_review_synthesize",
    "pr_review_feedback",
    "external_write_intent",
    "external_write_status",
    "external_write_doctor",
    "memory_query",
    "memory_candidate",
    "profile_generate",
    "self_check",
]
RUNTIME_DIRS = [
    "agents",
    "bin",
    "docs",
    "evals/golden-tasks",
    "evals/results",
    "hooks",
    "instructions",
    "mcp",
    "memory/inbox",
    "memory/patterns",
    "memory/reports",
    "metrics",
    "policy",
    "profiles",
    "schemas",
    "state/status",
    "tasks",
    "templates",
    "worktrees",
]
SOURCE_EXCLUDES = {".git", "__pycache__", "node_modules", "dist", "build", ".agent-harness-runtime", "tmp"}
LEAK_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9._-]+/Documents/webflow[23]?\b"),
    re.compile(r"\bwebflow" + r"[23]\b"),
    re.compile(r"\btai" + r"huynh\b", re.I),
]
DEFAULT_REDACTION_PATTERNS = [
    r"ATATT[0-9A-Za-z=_\-]{24,}",
    r"gh[pousr]_[0-9A-Za-z_]{24,}",
    r"sk-[0-9A-Za-z]{24,}",
    r"sk_live_[0-9A-Za-z]{20,}",
    r"sk_test_[0-9A-Za-z]{20,}",
    r"sk-ant-[0-9A-Za-z_\-]{20,}",
    r"xox[baprs]-[0-9A-Za-z-]{24,}",
    r"AKIA[0-9A-Z]{16}",
    r"ASIA[0-9A-Z]{16}",
    r"AIza[0-9A-Za-z_\-]{20,}",
    r"ya29\.[0-9A-Za-z_\-]+",
    r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----",
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    r"(?:mongodb(?:\+srv)?|postgres|postgresql|mysql|redis|rediss)://[^:@/\s]+:[^@/\s]{8,}@[^/\s]+",
    r"authorization\s*[:=]\s*(?:bearer\s+)?[\"']?(?!<redacted>|\$)[0-9A-Za-z._~+/=\-]{24,}",
    r"(api[_-]?key|token|secret|password)\s*[:=]\s*[\"']?[0-9A-Za-z._=+\-/]{24,}",
]


class HarnessError(Exception):
    """User-facing harness failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def runtime_root(args: argparse.Namespace | None = None) -> Path:
    if args is not None and getattr(args, "runtime_root", None):
        return expand(args.runtime_root)
    if os.environ.get("AGENT_HARNESS_ROOT"):
        return expand(os.environ["AGENT_HARNESS_ROOT"])
    workspace = getattr(args, "workspace", None) if args is not None else None
    workspace = workspace or DEFAULT_WORKSPACE
    return Path.home() / ".agent-harness" / workspace


def config_path(root: Path) -> Path:
    return root / "config.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HarnessError(f"Invalid JSON: {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_config(root: Path) -> dict[str, Any]:
    data = load_json(config_path(root), {})
    if not data:
        workspace = root.name
        data = {
            "workspace": workspace,
            "runtime_root": str(root),
            "source_root": str(SOURCE_ROOT),
            "repos": {},
            "created_at": utc_now(),
            "schema_version": 1,
        }
    return data


def save_config(root: Path, config: dict[str, Any]) -> None:
    config["runtime_root"] = str(root)
    config.setdefault("schema_version", 1)
    write_json(config_path(root), config)


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def valid_task_id(value: str) -> str:
    if not TASK_ID_RE.match(value):
        raise HarnessError(f"Invalid task id: {value}")
    return value


def slugify(text: str, fallback: str = "task") -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (value[:48].strip("-") or fallback)


def default_task_id(description: str, prefix: str = "task") -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return valid_task_id(f"{prefix}-{slugify(description)}-{stamp}"[:96].strip("-"))


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def run_text(args: list[str], cwd: Path | None = None, timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd) if cwd else None, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=check)


def redaction_patterns(root: Path) -> list[re.Pattern[str]]:
    raw = load_json(root / "policy" / "redaction-patterns.json", DEFAULT_REDACTION_PATTERNS)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raw = DEFAULT_REDACTION_PATTERNS
    return [re.compile(item, re.I) for item in raw]


def assert_no_sensitive_text(root: Path, text: str, label: str) -> None:
    for pattern in redaction_patterns(root):
        if pattern.search(text):
            raise HarnessError(f"Refusing {label}: text appears to contain sensitive material")


def ensure_runtime_dirs(root: Path) -> None:
    for rel in RUNTIME_DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    for file_name, content in {
        "memory/index.md": "# Harness Memory Index\n\nCurated memory is local. Agents may append source-backed candidates to `memory/inbox/`.\n",
        "memory/claims.jsonl": "",
        "memory/failures.jsonl": "",
        "metrics/runs.jsonl": "",
        "metrics/pr-review-runs.jsonl": "",
        "metrics/pr-review-findings.jsonl": "",
    }.items():
        path = root / file_name
        if not path.exists():
            path.write_text(content)


def copy_runtime_tree(root: Path) -> None:
    for item in RUNTIME_SOURCE.iterdir():
        destination = root / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, destination)


def write_runtime_launcher(root: Path, source_root: Path) -> None:
    launcher = root / "bin" / "harness"
    launcher.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"export AGENT_HARNESS_ROOT=\"${{AGENT_HARNESS_ROOT:-{root}}}\"",
                f"export AGENT_HARNESS_SOURCE=\"${{AGENT_HARNESS_SOURCE:-{source_root}}}\"",
                "exec \"$AGENT_HARNESS_SOURCE/bin/agent-harness\" \"$@\"",
                "",
            ]
        )
    )
    launcher.chmod(0o755)


def chmod_runtime(root: Path) -> None:
    for path in list((root / "bin").glob("*")) + list((root / "hooks").glob("*")) + list((root / "mcp").glob("*.mjs")):
        if path.is_file():
            path.chmod(path.stat().st_mode | 0o755)


def repo_alias_from_path(repo: Path, workspace: str) -> str:
    if workspace != "default":
        return workspace
    return slugify(repo.name, "repo")


def repo_remote(repo: Path) -> str:
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        return ""
    result = run_text(["git", "-C", str(repo), "remote", "get-url", "origin"], timeout=15)
    return result.stdout.strip() if result.returncode == 0 else ""


def git_root(path: Path) -> Path:
    result = run_text(["git", "-C", str(path), "rev-parse", "--show-toplevel"], timeout=15)
    if result.returncode != 0:
        return path
    return expand(result.stdout.strip())


def install(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    workspace = args.workspace
    source_root = SOURCE_ROOT
    repo = git_root(expand(args.repo)) if args.repo else None
    if root.exists() and not config_path(root).exists() and any(root.iterdir()) and not args.force:
        raise HarnessError(
            f"Refusing to install over existing unmanaged runtime: {root}. "
            "Use --runtime-root for a pilot install, or rerun with --force after backing up local state."
        )
    ensure_runtime_dirs(root)
    copy_runtime_tree(root)
    write_runtime_launcher(root, source_root)
    chmod_runtime(root)

    config = load_config(root)
    config.update(
        {
            "workspace": workspace,
            "source_root": str(source_root),
            "installed_at": utc_now(),
            "mcp": {
                "name": f"{workspace}-agent-harness",
                "server": str(root / "mcp" / "server.mjs"),
            },
        }
    )
    config.setdefault("repos", {})
    if repo:
        alias = args.repo_alias or repo_alias_from_path(repo, workspace)
        config["repos"][alias] = {
            "path": str(repo),
            "default": True,
            "origin": repo_remote(repo),
            "added_at": utc_now(),
        }
    save_config(root, config)
    if repo:
        profile_generate(argparse.Namespace(runtime_root=str(root), workspace=workspace, repo=str(repo), repo_alias=args.repo_alias, json=False, quiet=True))
    if not args.no_register:
        write_adapter_snippets(root, config)
    check = collect_self_check(root, source_root)
    data = {
        "ok": True,
        "runtime_root": str(root),
        "workspace": workspace,
        "config": str(config_path(root)),
        "repo": str(repo) if repo else None,
        "registered": not args.no_register,
        "self_check": {"ok": check["ok"], "failures": check["failures"], "warnings": check["warnings"]},
    }
    if check["failures"]:
        data["ok"] = False
    if args.json:
        print_json(data)
    else:
        print(f"Installed agent harness runtime: {root}")
        print(f"Config: {config_path(root)}")
        print("Self-check passed." if check["ok"] else "Self-check failed.")
        if args.no_register:
            print("Adapter registration skipped (--no-register).")
    return 0 if check["ok"] else 1


def write_adapter_snippets(root: Path, config: dict[str, Any]) -> None:
    snippets = root / "state" / "adapter-snippets"
    snippets.mkdir(parents=True, exist_ok=True)
    mcp_command = str(root / "mcp" / "server.mjs")
    (snippets / "codex-mcp.json").write_text(json.dumps({"mcpServers": {config["mcp"]["name"]: {"command": mcp_command, "env": {"AGENT_HARNESS_ROOT": str(root)}}}}, indent=2) + "\n")
    (snippets / "claude-mcp.txt").write_text(f"claude mcp add {config['mcp']['name']} {mcp_command} --env AGENT_HARNESS_ROOT={root}\n")
    (snippets / "cursor-mcp.json").write_text(json.dumps({"mcpServers": {config["mcp"]["name"]: {"command": mcp_command, "env": {"AGENT_HARNESS_ROOT": str(root)}}}}, indent=2) + "\n")


def uninstall(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    if not root.exists():
        print_json({"ok": True, "removed": False, "runtime_root": str(root)}) if args.json else print(f"No runtime found: {root}")
        return 0
    if args.dry_run:
        data = {"ok": True, "dry_run": True, "would_remove": str(root)}
    else:
        shutil.rmtree(root)
        data = {"ok": True, "removed": True, "runtime_root": str(root)}
    print_json(data) if args.json else print(data)
    return 0


def repo_entries(config: dict[str, Any]) -> dict[str, Path]:
    repos: dict[str, Path] = {}
    for alias, data in config.get("repos", {}).items():
        if isinstance(data, dict) and data.get("path"):
            repos[alias] = expand(data["path"])
    return repos


def default_repo(config: dict[str, Any]) -> tuple[str, Path] | None:
    repos = repo_entries(config)
    for alias, data in config.get("repos", {}).items():
        if isinstance(data, dict) and data.get("default") and alias in repos:
            return alias, repos[alias]
    return next(iter(repos.items()), None)


def resolve_repo(root: Path, repo_name: str | None) -> tuple[str, Path]:
    config = load_config(root)
    repos = repo_entries(config)
    if repo_name:
        if repo_name not in repos:
            raise HarnessError(f"Unknown repo alias: {repo_name}")
        return repo_name, repos[repo_name]
    default = default_repo(config)
    if not default:
        raise HarnessError("No repo configured. Run install --repo <checkout> or profile generate --repo <checkout>.")
    return default


def source_manifest(repo: Path) -> dict[str, Any]:
    sources = []
    candidates = [
        "AGENTS.md",
        ".github/CODEOWNERS",
        ".agentflow/README.md",
        ".agentflow/mcp-servers.json",
        ".agentflow/settings.json",
    ]
    for rel in candidates:
        path = repo / rel
        if path.exists():
            sources.append({"path": rel, "sha256": sha256(path), "bytes": path.stat().st_size})
    for directory in [".agentflow/rules", ".agentflow/docs", ".agentflow/skills", ".agentflow/agents"]:
        path = repo / directory
        if path.is_dir():
            count = sum(1 for item in path.rglob("*") if item.is_file())
            sources.append({"path": directory, "file_count": count})
    return {
        "generated_at": utc_now(),
        "repo": str(repo),
        "git_remote": repo_remote(repo),
        "sources": sources,
    }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_codeowners(repo: Path) -> list[dict[str, Any]]:
    path = repo / ".github" / "CODEOWNERS"
    owners: list[dict[str, Any]] = []
    if not path.exists():
        return owners
    for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) >= 2:
            owners.append({"pattern": parts[0], "owners": parts[1:], "line": line_number})
    return owners[:1000]


def profile_generate(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    workspace = args.workspace or root.name
    repo = git_root(expand(args.repo))
    ensure_runtime_dirs(root)
    config = load_config(root)
    config.setdefault("repos", {})
    alias = args.repo_alias or repo_alias_from_path(repo, workspace)
    config["workspace"] = workspace
    config["repos"][alias] = {
        "path": str(repo),
        "default": True,
        "origin": repo_remote(repo),
        "profile_generated_at": utc_now(),
    }
    save_config(root, config)
    profile_dir = root / "profiles" / workspace
    profile_dir.mkdir(parents=True, exist_ok=True)
    manifest = source_manifest(repo)
    owners = parse_codeowners(repo)
    agentflow = {
        "present": (repo / ".agentflow").is_dir(),
        "rules_present": (repo / ".agentflow" / "rules").is_dir(),
        "docs_present": (repo / ".agentflow" / "docs").is_dir(),
    }
    profile = {
        "schema_version": 1,
        "workspace": workspace,
        "repo_alias": alias,
        "generated_at": utc_now(),
        "profile_mode": "generated-local",
        "sources": manifest["sources"],
        "agentflow": agentflow,
        "knowledge_policy": {
            "canonical": "current code/tests and project-owned agent docs",
            "local_candidates": "memory/inbox",
            "promotion": "human-reviewed upstream to project-owned docs",
        },
    }
    policy = {
        "schema_version": 1,
        "workspace": workspace,
        "default_mode": "run",
        "yolo_available": True,
        "hard_stops": ["sensitive file reads", "token exfiltration", "production-affecting actions without explicit scope"],
        "external_writes": "task-scoped connector-native write intents",
    }
    risk_rules = {
        "schema_version": 1,
        "risk_keywords": {
            "critical": ["auth", "permission", "payment", "billing", "migration", "secret", "token", "production"],
            "high": ["api", "schema", "database", "cache", "queue", "job", "deploy", "flag"],
            "medium": ["ui", "routing", "state", "performance", "test"],
        },
        "owner_patterns": owners[:200],
    }
    write_json(profile_dir / "source-manifest.json", manifest)
    write_json(profile_dir / "profile.json", profile)
    write_json(profile_dir / "policy.json", policy)
    write_json(profile_dir / "risk-rules.json", risk_rules)
    specialists = profile_dir / "specialists"
    specialists.mkdir(exist_ok=True)
    (specialists / "README.md").write_text(
        "# Generated Specialist Seeds\n\n"
        "This profile intentionally stores source-backed seeds only. Agents derive domain lanes from changed files, CODEOWNERS, project agent docs, and connector evidence during each task.\n"
    )
    data = {"ok": True, "profile": str(profile_dir / "profile.json"), "source_manifest": str(profile_dir / "source-manifest.json"), "owners": len(owners)}
    if getattr(args, "quiet", False):
        return 0
    if args.json:
        print_json(data)
    else:
        print(f"Generated profile: {profile_dir}")
    return 0


def render_template(root: Path, name: str, values: dict[str, str]) -> str:
    text = (root / "templates" / name).read_text()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def task_dir(root: Path, task_id: str) -> Path:
    return root / "tasks" / valid_task_id(task_id)


def write_status(root: Path, task_id: str | None = None) -> dict[str, Any]:
    status_dir = root / "state" / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    for path in sorted((root / "tasks").glob("*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:25]:
        manifest = load_json(path / "task.json", {})
        if manifest:
            tasks.append(manifest)
    latest = task_id or (tasks[0]["task_id"] if tasks else None)
    data = {"generated_at": utc_now(), "latest_task_id": latest, "tasks": tasks}
    write_json(status_dir / "latest.json", data)
    lines = ["# Agent Harness Status", "", f"Generated: {data['generated_at']}", ""]
    for item in tasks[:10]:
        lines.append(f"- `{item.get('task_id')}` {item.get('status', 'unknown')} {item.get('description', '')}")
    (status_dir / "latest.md").write_text("\n".join(lines) + "\n")
    (status_dir / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Agent Harness</title>"
        "<h1>Agent Harness</h1><pre>"
        + html.escape(json.dumps(data, indent=2, sort_keys=True))
        + "</pre>\n"
    )
    return data


def start_task(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    ensure_runtime_dirs(root)
    config = load_config(root)
    repo_name, repo = resolve_repo(root, args.repo)
    description = args.prompt
    assert_no_sensitive_text(root, description, "task prompt")
    task_id = valid_task_id(args.task_id) if args.task_id else default_task_id(description, "task")
    worktree_path = root / "worktrees" / repo_name / task_id
    task_path = task_dir(root, task_id)
    task_path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "task_id": task_id,
        "workspace": config.get("workspace", root.name),
        "repo": repo_name,
        "repo_path": str(repo),
        "description": description,
        "kind": args.kind,
        "risk": args.risk,
        "mode": args.mode,
        "status": "started",
        "created_at": utc_now(),
        "worktree": str(worktree_path),
    }
    write_json(task_path / "task.json", manifest)
    values = {
        "TASK_ID": task_id,
        "WORKSPACE": manifest["workspace"],
        "REPO_NAME": repo_name,
        "REPO_PATH": str(repo),
        "WORKTREE_PATH": str(worktree_path),
        "GOAL": description,
        "RISK": args.risk,
        "MODE": args.mode,
    }
    (task_path / "packet.md").write_text(render_template(root, "task-packet.md", values))
    (task_path / "progress.md").write_text(render_template(root, "progress.md", values))
    if args.risk in {"yellow", "red", "high", "critical"}:
        (task_path / "contract.md").write_text(render_template(root, "sprint-contract.md", values))
    write_status(root, task_id)
    data = {"ok": True, "task_id": task_id, "task_dir": str(task_path), "packet": str(task_path / "packet.md"), "worktree": str(worktree_path)}
    print_json(data) if args.json else print(f"Started task {task_id}: {task_path}")
    return 0


def latest_task_id(root: Path) -> str:
    status = load_json(root / "state" / "status" / "latest.json", {})
    if status.get("latest_task_id"):
        return valid_task_id(status["latest_task_id"])
    tasks = sorted((root / "tasks").glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not tasks:
        raise HarnessError("No harness tasks found")
    return valid_task_id(tasks[0].name)


def resume_task(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    path = task_dir(root, task_id)
    manifest = load_json(path / "task.json", {})
    if not manifest:
        raise HarnessError(f"Task not found: {task_id}")
    manifest["status"] = "resumed"
    manifest["resumed_at"] = utc_now()
    write_json(path / "task.json", manifest)
    write_status(root, task_id)
    data = {"ok": True, "task_id": task_id, "task_dir": str(path), "packet": str(path / "packet.md"), "evidence": str(path / "evidence.md")}
    print_json(data) if args.json else print(f"Resume task {task_id}: {path}")
    return 0


def status(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    data = write_status(root)
    if args.json:
        print_json(data)
    else:
        print((root / "state" / "status" / "latest.md").read_text())
    return 0


def read_artifact(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    safe_names = {
        "packet": "packet.md",
        "progress": "progress.md",
        "contract": "contract.md",
        "evidence": "evidence.md",
        "task-json": "task.json",
        "pr-comments-draft": "pr-review/public-comments-draft.md",
        "pr-risk": "pr-review/risk.json",
        "pr-brief": "pr-review/private-review-brief.md",
    }
    if args.artifact not in safe_names:
        raise HarnessError(f"Unknown artifact: {args.artifact}")
    path = task_dir(root, task_id) / safe_names[args.artifact]
    if not path.exists():
        raise HarnessError(f"Artifact does not exist: {path}")
    text = path.read_text(errors="replace")
    assert_no_sensitive_text(root, text, "artifact output")
    print(text)
    return 0


def record_progress(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    path = task_dir(root, task_id) / "progress.md"
    assert_no_sensitive_text(root, args.note, "progress note")
    with path.open("a") as handle:
        handle.write(f"\n## Checkpoint {utc_now()}\n\n{args.note.strip()}\n")
    write_status(root, task_id)
    print_json({"ok": True, "progress": str(path)}) if args.json else print(f"Recorded progress: {path}")
    return 0


def evidence_text(args: argparse.Namespace) -> str:
    if args.content:
        return args.content
    return "\n".join(
        [
            f"# Evidence: {args.task_id}",
            "",
            "## Summary",
            "",
            args.summary or "Completed through the agent harness.",
            "",
            "## Positive Proof",
            "",
            f"- Command or inspection: {args.positive_proof or 'code/task inspection'}",
            f"- Result: {args.positive_result or 'PASS'}",
            "",
            "## Negative Proof",
            "",
            f"- Regression or failure-mode check: {args.negative_proof or 'primary failure mode considered'}",
            f"- Result: {args.negative_result or 'PASS'}",
            "",
            "## Commands Run",
            "",
            "```text",
            args.commands_run or "not run; inspection-only task",
            "```",
            "",
            "## Skipped Checks",
            "",
            args.skipped_checks or "- Check: none\n- Reason: no skipped checks\n- Residual risk: none identified",
            "",
            "## Diff Risk Notes",
            "",
            args.diff_risk_notes or "- Risk: local task state only\n- Mitigation: evidence gate",
            "",
            "## Memory Candidates",
            "",
            args.memory_candidates or "- Candidate: none\n- Source: this task\n- Confidence: n/a",
            "",
        ]
    )


def write_evidence(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    args.task_id = task_id
    text = evidence_text(args)
    assert_no_sensitive_text(root, text, "evidence")
    path = task_dir(root, task_id) / "evidence.md"
    path.write_text(text if text.endswith("\n") else text + "\n")
    print_json({"ok": True, "evidence": str(path)}) if args.json else print(f"Wrote evidence: {path}")
    return 0


def evidence_failures(text: str) -> list[str]:
    failures = []
    for heading in ["Summary", "Positive Proof", "Negative Proof", "Commands Run", "Skipped Checks", "Diff Risk Notes", "Memory Candidates"]:
        if not re.search(rf"^## {re.escape(heading)}\s*$", text, re.M):
            failures.append(f"missing {heading}")
    placeholders = ["What changed or what was learned.", "Command or inspection:", "Result:"]
    if all(item in text for item in placeholders):
        failures.append("evidence appears to be the unfilled template")
    return failures


def evidence_doctor(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    path = task_dir(root, task_id) / "evidence.md"
    failures = ["missing evidence.md"] if not path.exists() else evidence_failures(path.read_text(errors="replace"))
    data = {"ok": not failures, "task_id": task_id, "failures": failures, "evidence": str(path)}
    print_json(data) if args.json else print("ok" if not failures else "\n".join(failures))
    return 0 if not failures else 2


def finish_task(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    doctor_args = argparse.Namespace(runtime_root=str(root), task_id=task_id, json=True)
    path = task_dir(root, task_id)
    failures = evidence_failures((path / "evidence.md").read_text(errors="replace")) if (path / "evidence.md").exists() else ["missing evidence.md"]
    if failures and not args.force:
        print_json({"ok": False, "task_id": task_id, "failures": failures})
        return 2
    manifest = load_json(path / "task.json", {})
    manifest["status"] = "finished"
    manifest["finished_at"] = utc_now()
    write_json(path / "task.json", manifest)
    write_status(root, task_id)
    data = {"ok": True, "task_id": task_id, "task_dir": str(path), "evidence": str(path / "evidence.md")}
    print_json(data) if args.json else print(f"Finished task {task_id}")
    return 0


def make_worktree(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    repo_name, repo = resolve_repo(root, args.repo)
    task_id = valid_task_id(args.task_id)
    target = root / "worktrees" / repo_name / task_id
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        data = {"ok": True, "exists": True, "worktree": str(target)}
    else:
        branch = args.branch or f"agent/{task_id}"
        result = run_text(["git", "-C", str(repo), "worktree", "add", "-b", branch, str(target)], timeout=120)
        if result.returncode != 0:
            raise HarnessError(result.stderr.strip() or result.stdout.strip())
        data = {"ok": True, "exists": False, "worktree": str(target), "branch": branch}
    print_json(data) if args.json else print(data["worktree"])
    return 0


def agent_capabilities(args: argparse.Namespace) -> int:
    agents = {
        "codex": {"available": command_available("codex"), "wrapper": "ah-codex"},
        "claude": {"available": command_available("claude"), "wrapper": "ah-claude"},
        "cursor": {"available": command_available("cursor-agent") or command_available("agent"), "wrapper": "ah-cursor"},
    }
    data = {"ok": True, "peer_invocation": "wrapper-bridge", "agents": agents}
    print_json(data)
    return 0


def wrapper_for(root: Path, agent: str) -> Path:
    return root / "bin" / {"codex": "ah-codex", "claude": "ah-claude", "cursor": "ah-cursor"}[agent]


def agent_run(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    run_id = args.run_id or f"{args.agent}-{args.role}-{int(time.time())}"
    run_dir = task_dir(root, task_id) / "agent-runs" / slugify(run_id, "run")
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt = args.prompt
    assert_no_sensitive_text(root, prompt, "agent prompt")
    (run_dir / "prompt.md").write_text(prompt if prompt.endswith("\n") else prompt + "\n")
    command = [str(wrapper_for(root, args.agent)), "--task", task_id]
    if args.agent == "codex":
        command += ["exec", "--output-last-message", str(run_dir / "final.md"), prompt]
    elif args.agent == "claude":
        command += ["-p", "--output-format", "json", prompt]
    else:
        command += ["-p", "--output-format", "json", prompt]
    metadata = {"task_id": task_id, "agent": args.agent, "role": args.role, "run_id": run_id, "command": command, "started_at": utc_now(), "dry_run": args.dry_run}
    write_json(run_dir / "metadata.json", metadata)
    if args.dry_run:
        (run_dir / "final.md").write_text("Dry run: peer agent not launched.\n")
        metadata.update({"ok": True, "status": "dry-run", "finished_at": utc_now()})
        write_json(run_dir / "metadata.json", metadata)
    else:
        result = run_text(command, cwd=Path.cwd(), timeout=args.timeout)
        (run_dir / "stdout.txt").write_text(result.stdout)
        (run_dir / "stderr.txt").write_text(result.stderr)
        if not (run_dir / "final.md").exists():
            (run_dir / "final.md").write_text(result.stdout or result.stderr or "")
        metadata.update({"ok": result.returncode == 0, "status": "complete" if result.returncode == 0 else "failed", "returncode": result.returncode, "finished_at": utc_now()})
        write_json(run_dir / "metadata.json", metadata)
    print_json({"ok": metadata["ok"], "run_dir": str(run_dir), "metadata": str(run_dir / "metadata.json")})
    return 0 if metadata["ok"] else 1


def review_plan(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    review_dir = task_dir(root, task_id) / "reviews" / f"review-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    review_dir.mkdir(parents=True, exist_ok=True)
    lanes = ["scope", "tests", "standards"]
    manifest = load_json(task_dir(root, task_id) / "task.json", {})
    if manifest.get("risk") in {"red", "critical", "high"}:
        lanes.append("security")
    plan = {"task_id": task_id, "run_id": review_dir.name, "lanes": [{"lane": lane, "agent": "auto", "status": "planned"} for lane in lanes], "created_at": utc_now()}
    write_json(review_dir / "plan.json", plan)
    (review_dir / "plan.md").write_text("# Review Plan\n\n" + "\n".join(f"- {lane}" for lane in lanes) + "\n")
    write_json(task_dir(root, task_id) / "reviews" / "latest.json", {"run_id": review_dir.name})
    print_json({"ok": True, "review_dir": str(review_dir), "lanes": lanes})
    return 0


def review_run(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    lane = args.lane
    prompt = f"Review task {task_id} for lane {lane}. Use only task artifacts, current code, diff, and evidence. Return a concise verdict with concrete findings only."
    return agent_run(argparse.Namespace(runtime_root=str(root), task_id=task_id, agent=args.agent, role="reviewer", run_id=f"review-{lane}-{args.agent}", prompt=prompt, dry_run=args.dry_run, timeout=args.timeout, json=True))


def review_status(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    runs = []
    base = task_dir(root, task_id) / "agent-runs"
    if base.exists():
        for meta in base.glob("*/metadata.json"):
            runs.append(load_json(meta, {}))
    print_json({"ok": True, "task_id": task_id, "runs": runs})
    return 0


def review_synthesize(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    base = task_dir(root, task_id) / "reviews" / "synthesis.md"
    status_data = []
    run_base = task_dir(root, task_id) / "agent-runs"
    if run_base.exists():
        for final in run_base.glob("*/final.md"):
            status_data.append(f"- {final.parent.name}: {final.read_text(errors='replace')[:800]}")
    text = "# Review Synthesis\n\n## Verdict\n\nREVIEW\n\n## Lane Outputs\n\n" + ("\n".join(status_data) if status_data else "No review lanes have run.\n")
    base.write_text(text if text.endswith("\n") else text + "\n")
    print_json({"ok": True, "synthesis": str(base)})
    return 0


def validate_pr_source(value: str) -> str:
    if value.startswith("https://"):
        if not re.search(r"/pull/\d+$", value):
            raise HarnessError("PR URL must end with /pull/<number>")
        return value
    if value.isdigit():
        return value
    if not SAFE_REF_RE.match(value) or ".." in value or value.startswith("-"):
        raise HarnessError(f"Unsafe PR source/ref: {value}")
    return value


def classify_pr(files: list[str], diff: str, metadata: dict[str, Any]) -> dict[str, Any]:
    text = "\n".join(files) + "\n" + diff[:200000] + "\n" + json.dumps(metadata)
    lowered = text.lower()
    triggers = []
    risk = "low"
    for level, words in {
        "critical": ["auth", "permission", "payment", "billing", "migration", "secret", "token"],
        "high": ["api", "schema", "database", "job", "queue", "cache", "deploy", "flag"],
        "medium": ["ui", "state", "routing", "test", "performance"],
    }.items():
        hits = [word for word in words if word in lowered]
        if hits:
            triggers.append({"level": level, "matches": hits})
            if level == "critical":
                risk = "critical"
            elif level == "high" and risk not in {"critical"}:
                risk = "high"
            elif level == "medium" and risk == "low":
                risk = "medium"
    if len(files) > 30 or len(diff.splitlines()) > 1500:
        risk = "high" if risk != "critical" else risk
        triggers.append({"level": "high", "matches": ["large-diff"]})
    lanes = ["intake", "correctness-regression", "test-integrity"]
    if risk in {"high", "critical"}:
        lanes.extend(["security-permissions", "release-rollout", "context-historian"])
    if any(re.search(r"\.(tsx|jsx|css|scss)$", path) for path in files):
        lanes.append("ui-ux-a11y")
    return {"risk_level": risk, "triggers": triggers, "required_lenses": sorted(set(lanes))}


def pr_review_start(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    repo_name, repo = resolve_repo(root, args.repo)
    source = validate_pr_source(args.source)
    task_id = args.task_id or default_task_id(f"pr-review-{source}", "pr-review")
    start_task(argparse.Namespace(runtime_root=str(root), repo=repo_name, prompt=f"Review PR/ref {source}", task_id=task_id, kind="pr-review", risk="auto", mode="run", json=True))
    pr_dir = task_dir(root, task_id) / "pr-review"
    pr_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {"source": source, "repo": repo_name, "base": args.base or "origin/dev", "generated_at": utc_now()}
    diff = ""
    body = ""
    if command_available("gh") and (source.isdigit() or source.startswith("https://")):
        view = run_text(["gh", "pr", "view", source, "--json", "number,title,body,url,baseRefName,headRefName,isDraft,labels,author,changedFiles,additions,deletions"], cwd=repo, timeout=60)
        if view.returncode == 0 and view.stdout.strip():
            metadata.update(json.loads(view.stdout))
            body = str(metadata.get("body") or "")
            metadata["base"] = metadata.get("baseRefName") or metadata["base"]
        patch = run_text(["gh", "pr", "diff", source, "--patch"], cwd=repo, timeout=120)
        diff = patch.stdout if patch.returncode == 0 else ""
    if not diff:
        base = args.base or metadata["base"]
        diff_result = run_text(["git", "-C", str(repo), "diff", f"{base}...HEAD"], timeout=120)
        diff = diff_result.stdout if diff_result.returncode == 0 else ""
    files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
    risk = classify_pr(files, diff, metadata)
    write_json(pr_dir / "metadata.json", metadata)
    (pr_dir / "pr-body.md").write_text(body if body.endswith("\n") else body + "\n")
    (pr_dir / "changed-files.txt").write_text("\n".join(files) + ("\n" if files else ""))
    (pr_dir / "diff.patch").write_text(diff)
    write_json(pr_dir / "risk.json", risk)
    (pr_dir / "private-review-brief.md").write_text(f"# Private Review Brief\n\nSource: {source}\nRisk: {risk['risk_level']}\nRequired lenses: {', '.join(risk['required_lenses'])}\n")
    (pr_dir / "author-contract.md").write_text("# Author Proof Request\n\nAsk for targeted proof only when the PR body or artifacts do not already provide it.\n")
    (pr_dir / "public-comments-draft.md").write_text("---\nsynthesis_source: empty\n---\n\nNo comments drafted yet. Run `pr-review synthesize`.\n")
    context_dir = pr_dir / "context"
    context_dir.mkdir(exist_ok=True)
    profile_generate(argparse.Namespace(runtime_root=str(root), workspace=load_config(root).get("workspace", root.name), repo=str(repo), repo_alias=repo_name, json=False))
    write_json(context_dir / "source-manifest.json", source_manifest(repo))
    (context_dir / "context-brief.md").write_text("# Context Brief\n\nGenerated from local repo sources. Add connector evidence during review when needed.\n")
    write_status(root, task_id)
    print_json({"ok": True, "task_id": task_id, "pr_review_dir": str(pr_dir), "risk": risk})
    return 0


def pr_review_run(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    pr_dir = task_dir(root, task_id) / "pr-review"
    risk = load_json(pr_dir / "risk.json", {})
    lanes = risk.get("required_lenses", ["intake"]) if args.lane == "auto" else [args.lane]
    max_lanes = args.max_lanes or (3 if risk.get("risk_level") in {"low", "medium"} else 5)
    selected = lanes[:max_lanes]
    run_root = pr_dir / "agents"
    findings_dir = pr_dir / "findings"
    run_root.mkdir(exist_ok=True)
    findings_dir.mkdir(exist_ok=True)
    results = []
    for lane in selected:
        prompt = f"Review PR task {task_id} lane {lane}. Read pr-review artifacts. Return only schema-shaped high-confidence findings."
        if args.dry_run:
            lane_dir = run_root / f"pr-{lane}-dry-run"
            lane_dir.mkdir(exist_ok=True)
            (lane_dir / "prompt.md").write_text(prompt + "\n")
            write_json(lane_dir / "metadata.json", {"lane": lane, "status": "dry-run", "agent": args.agent, "created_at": utc_now()})
            write_json(findings_dir / f"{lane}.json", {"lane": lane, "findings": []})
            results.append({"lane": lane, "status": "dry-run"})
        else:
            agent_run(argparse.Namespace(runtime_root=str(root), task_id=task_id, agent=args.agent, role="reviewer", run_id=f"pr-{lane}-{args.agent}", prompt=prompt, dry_run=False, timeout=args.timeout, json=True))
            results.append({"lane": lane, "status": "launched"})
    write_json(pr_dir / "review-evidence.json", {"task_id": task_id, "runs": results, "updated_at": utc_now()})
    print_json({"ok": True, "task_id": task_id, "lanes": results})
    return 0


def pr_review_synthesize(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    pr_dir = task_dir(root, task_id) / "pr-review"
    findings = []
    for path in sorted((pr_dir / "findings").glob("*.json")) if (pr_dir / "findings").exists() else []:
        data = load_json(path, {})
        findings.extend(data.get("findings", []))
    accepted = [item for item in findings if item.get("confidence", 0) >= 0.75 and not item.get("discard_reason")][:5]
    lines = ["---", "synthesis_source: harness", f"synthesis_run_at: {utc_now()}", f"task_id: {task_id}", "---", "", "# Public Comments Draft", ""]
    if not accepted:
        lines.append("No high-confidence comments drafted.")
    for index, finding in enumerate(accepted, start=1):
        lines.extend([
            f"## {index}. [{finding.get('severity', 'medium')}] {finding.get('title', 'Finding')}",
            "",
            str(finding.get("failure_scenario", "")).strip(),
            "",
            str(finding.get("minimal_fix", "")).strip(),
            "",
            f"File: `{finding.get('file', '')}` line {finding.get('line', '')}",
            "",
        ])
    draft = pr_dir / "public-comments-draft.md"
    draft.write_text("\n".join(lines) + "\n")
    print_json({"ok": True, "draft": str(draft), "drafted": len(accepted), "candidates": len(findings)})
    return 0


def pr_review_feedback(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    record = {"task_id": task_id, "finding_id": args.finding_id, "outcome": args.outcome, "note": args.note or "", "recorded_at": utc_now()}
    append_jsonl(root / "metrics" / "pr-review-findings.jsonl", record)
    print_json({"ok": True, "record": record})
    return 0


def external_write_intent(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    if args.provider not in WRITE_PROVIDERS:
        raise HarnessError(f"Unsupported provider: {args.provider}")
    if args.operation not in WRITE_OPERATIONS:
        raise HarnessError(f"Unsupported operation: {args.operation}")
    text = "\n".join([args.provider, args.operation, args.target, args.summary or "", args.content_preview or ""])
    assert_no_sensitive_text(root, text, "external write intent")
    intent_id = hashlib.sha256(f"{task_id}:{text}:{utc_now()}".encode()).hexdigest()[:16]
    intent = {
        "intent_id": intent_id,
        "task_id": task_id,
        "provider": args.provider,
        "operation": args.operation,
        "target": args.target,
        "summary": args.summary,
        "content_sha256": hashlib.sha256((args.content_preview or "").encode()).hexdigest(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=args.ttl_hours)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "created_at": utc_now(),
        "status": "active",
    }
    path = task_dir(root, task_id) / "external-writes" / "intents" / f"{intent_id}.json"
    write_json(path, intent)
    append_jsonl(task_dir(root, task_id) / "external-writes" / "log.jsonl", {"event": "intent-created", **intent})
    print_json({"ok": True, "intent": intent, "path": str(path)})
    return 0


def external_write_status(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    intents = [load_json(path, {}) for path in (task_dir(root, task_id) / "external-writes" / "intents").glob("*.json")] if (task_dir(root, task_id) / "external-writes" / "intents").exists() else []
    print_json({"ok": True, "task_id": task_id, "intents": intents})
    return 0


def external_write_doctor(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    task_id = latest_task_id(root) if args.task_id == "latest" else valid_task_id(args.task_id)
    intents = [load_json(path, {}) for path in (task_dir(root, task_id) / "external-writes" / "intents").glob("*.json")] if (task_dir(root, task_id) / "external-writes" / "intents").exists() else []
    failures = []
    now = datetime.now(timezone.utc)
    for intent in intents:
        try:
            expiry = datetime.fromisoformat(str(intent.get("expires_at", "")).replace("Z", "+00:00"))
        except ValueError:
            failures.append(f"invalid expiry: {intent.get('intent_id')}")
            continue
        if expiry < now:
            failures.append(f"expired intent: {intent.get('intent_id')}")
    print_json({"ok": not failures, "task_id": task_id, "failures": failures, "active_intents": len(intents)})
    return 0 if not failures else 2


def memory_query(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    query = args.query.lower()
    results = []
    for path in [root / "memory" / "claims.jsonl", root / "memory" / "failures.jsonl", root / "memory" / "index.md"]:
        if path.exists():
            for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
                if query in line.lower():
                    results.append({"path": str(path), "line": line_no, "text": line[:500]})
    print_json({"ok": True, "query": args.query, "results": results[:50]})
    return 0


def memory_candidate(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    text = "\n".join([args.claim, args.source, args.confidence])
    assert_no_sensitive_text(root, text, "memory candidate")
    path = root / "memory" / "inbox" / f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{slugify(args.claim)}.md"
    path.write_text(f"# Memory Candidate\n\nClaim: {args.claim}\n\nSource: {args.source}\n\nConfidence: {args.confidence}\n")
    print_json({"ok": True, "candidate": str(path)})
    return 0


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def metrics_export(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    tasks = []
    for task_json in (root / "tasks").glob("*/task.json"):
        data = load_json(task_json, {})
        if data:
            tasks.append(data)
    report = {
        "generated_at": utc_now(),
        "workspace": load_config(root).get("workspace", root.name),
        "task_count": len(tasks),
        "finished_tasks": sum(1 for item in tasks if item.get("status") == "finished"),
        "pr_review_runs": count_jsonl(root / "metrics" / "pr-review-runs.jsonl"),
        "pr_review_findings": count_jsonl(root / "metrics" / "pr-review-findings.jsonl"),
    }
    out = root / "memory" / "reports" / f"metrics-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    write_json(out, report)
    print_json({"ok": True, "report": str(out), "summary": report})
    return 0


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(errors="replace").splitlines() if line.strip())


def eval_run(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    failures = []
    if not (root / "templates" / "task-packet.md").exists():
        failures.append("missing task packet template")
    if not (root / "mcp" / "server.mjs").exists():
        failures.append("missing MCP server")
    data = {"ok": not failures, "failures": failures, "checked_at": utc_now()}
    if not args.no_record:
        append_jsonl(root / "evals" / "results" / "eval-runs.jsonl", data)
    print_json(data)
    return 0 if data["ok"] else 1


def collect_self_check(root: Path, source_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    for rel in RUNTIME_DIRS:
        if not (root / rel).is_dir():
            failures.append(f"missing runtime directory: {rel}")
    for rel in ["bin/harness", "mcp/server.mjs", "hooks/pre-tool-policy.py", "hooks/prompt-secret-scan.py", "hooks/stop-requires-evidence.py"]:
        path = root / rel
        if not path.exists():
            failures.append(f"missing runtime file: {rel}")
        elif not os.access(path, os.X_OK):
            failures.append(f"runtime file is not executable: {rel}")
    if not config_path(root).exists():
        failures.append("missing config.json")
    config = load_config(root)
    if not config.get("repos"):
        warnings.append("no repo aliases configured")
    server = root / "mcp" / "server.mjs"
    if server.exists() and command_available("node"):
        result = run_text(["node", str(server), "--self-test"], timeout=30)
        if result.returncode != 0:
            failures.append("MCP self-test failed")
        else:
            try:
                data = json.loads(result.stdout)
                missing = sorted(set(MCP_TOOLS) - set(data.get("tools", [])))
                if missing:
                    failures.append("MCP self-test missing tools: " + ", ".join(missing))
            except json.JSONDecodeError:
                failures.append("MCP self-test did not return JSON")
    elif not command_available("node"):
        warnings.append("node unavailable; MCP self-test skipped")
    failures.extend(scan_source_for_leaks(source_root))
    failures.extend(scan_tree_for_sensitive_material(root, max_files=2000))
    return {"ok": not failures, "runtime_root": str(root), "source_root": str(source_root), "failures": failures, "warnings": warnings}


def self_check(args: argparse.Namespace) -> int:
    root = runtime_root(args)
    source_root = expand(args.source_root) if args.source_root else SOURCE_ROOT
    data = collect_self_check(root, source_root)
    if args.json:
        print_json(data)
    else:
        print("Agent harness self-check passed." if data["ok"] else "Agent harness self-check failed.")
        for failure in data["failures"]:
            print(f"- {failure}")
        for warning in data["warnings"]:
            print(f"- warning: {warning}")
    return 0 if data["ok"] else 1


def scan_source_for_leaks(source_root: Path) -> list[str]:
    failures = []
    for path in source_root.rglob("*"):
        if any(part in SOURCE_EXCLUDES for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.stat().st_size > 1024 * 1024:
            continue
        text = path.read_text(errors="ignore")
        for pattern in LEAK_PATTERNS:
            if pattern.search(text):
                failures.append(f"source leak pattern {pattern.pattern!r}: {path.relative_to(source_root)}")
                break
    return failures


def scan_tree_for_sensitive_material(root: Path, max_files: int = 5000) -> list[str]:
    failures = []
    patterns = redaction_patterns(root)
    count = 0
    for path in root.rglob("*"):
        if any(part in {"worktrees", ".git", "__pycache__"} for part in path.parts):
            continue
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            continue
        count += 1
        if count > max_files:
            break
        text = path.read_text(errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            failures.append(f"possible sensitive material: {path}")
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-harness")
    parser.add_argument("--runtime-root", help="Override runtime root")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE, help="Workspace slug")
    sub = parser.add_subparsers(dest="cmd", required=True)

    install_p = sub.add_parser("install")
    install_p.add_argument("--workspace", required=True)
    install_p.add_argument("--repo")
    install_p.add_argument("--repo-alias")
    install_p.add_argument("--runtime-root")
    install_p.add_argument("--no-register", action="store_true")
    install_p.add_argument("--force", action="store_true")
    install_p.add_argument("--json", action="store_true")
    install_p.set_defaults(func=install)

    uninstall_p = sub.add_parser("uninstall")
    uninstall_p.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    uninstall_p.add_argument("--runtime-root")
    uninstall_p.add_argument("--dry-run", action="store_true")
    uninstall_p.add_argument("--json", action="store_true")
    uninstall_p.set_defaults(func=uninstall)

    profile_p = sub.add_parser("profile")
    profile_sub = profile_p.add_subparsers(dest="profile_cmd", required=True)
    gen_p = profile_sub.add_parser("generate")
    gen_p.add_argument("--repo", required=True)
    gen_p.add_argument("--repo-alias")
    gen_p.add_argument("--runtime-root")
    gen_p.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    gen_p.add_argument("--json", action="store_true")
    gen_p.set_defaults(func=profile_generate)

    start_p = sub.add_parser("start")
    start_p.add_argument("repo", nargs="?")
    start_p.add_argument("--prompt", required=True)
    start_p.add_argument("--task-id")
    start_p.add_argument("--kind", default="general")
    start_p.add_argument("--risk", default="auto", choices=sorted(RISK_LEVELS))
    start_p.add_argument("--mode", default="run", choices=sorted(MODES))
    start_p.add_argument("--json", action="store_true")
    start_p.set_defaults(func=start_task)

    resume_p = sub.add_parser("resume")
    resume_p.add_argument("task_id", nargs="?", default="latest")
    resume_p.add_argument("--json", action="store_true")
    resume_p.set_defaults(func=resume_task)

    status_p = sub.add_parser("status")
    status_p.add_argument("--json", action="store_true")
    status_p.set_defaults(func=status)

    read_p = sub.add_parser("read-artifact")
    read_p.add_argument("task_id")
    read_p.add_argument("artifact")
    read_p.set_defaults(func=read_artifact)

    progress_p = sub.add_parser("record-progress")
    progress_p.add_argument("task_id")
    progress_p.add_argument("--note", required=True)
    progress_p.add_argument("--json", action="store_true")
    progress_p.set_defaults(func=record_progress)

    evidence_p = sub.add_parser("evidence")
    evidence_sub = evidence_p.add_subparsers(dest="evidence_cmd", required=True)
    write_p = evidence_sub.add_parser("write")
    write_p.add_argument("task_id")
    write_p.add_argument("--content")
    write_p.add_argument("--summary")
    write_p.add_argument("--positive-proof")
    write_p.add_argument("--positive-result")
    write_p.add_argument("--negative-proof")
    write_p.add_argument("--negative-result")
    write_p.add_argument("--commands-run")
    write_p.add_argument("--skipped-checks")
    write_p.add_argument("--diff-risk-notes")
    write_p.add_argument("--memory-candidates")
    write_p.add_argument("--json", action="store_true")
    write_p.set_defaults(func=write_evidence)
    doctor_p = evidence_sub.add_parser("doctor")
    doctor_p.add_argument("task_id", nargs="?", default="latest")
    doctor_p.add_argument("--json", action="store_true")
    doctor_p.set_defaults(func=evidence_doctor)

    finish_p = sub.add_parser("finish")
    finish_p.add_argument("task_id", nargs="?", default="latest")
    finish_p.add_argument("--force", action="store_true")
    finish_p.add_argument("--json", action="store_true")
    finish_p.set_defaults(func=finish_task)

    wt_p = sub.add_parser("worktree")
    wt_sub = wt_p.add_subparsers(dest="worktree_cmd", required=True)
    wt_create = wt_sub.add_parser("create")
    wt_create.add_argument("repo")
    wt_create.add_argument("task_id")
    wt_create.add_argument("--branch")
    wt_create.add_argument("--json", action="store_true")
    wt_create.set_defaults(func=make_worktree)

    agent_p = sub.add_parser("agent")
    agent_sub = agent_p.add_subparsers(dest="agent_cmd", required=True)
    caps_p = agent_sub.add_parser("capabilities")
    caps_p.set_defaults(func=agent_capabilities)
    run_p = agent_sub.add_parser("run")
    run_p.add_argument("task_id")
    run_p.add_argument("--agent", choices=["codex", "claude", "cursor"], required=True)
    run_p.add_argument("--role", default="reviewer")
    run_p.add_argument("--run-id")
    run_p.add_argument("--prompt", required=True)
    run_p.add_argument("--timeout", type=int, default=120)
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--json", action="store_true")
    run_p.set_defaults(func=agent_run)

    review_p = sub.add_parser("review")
    review_sub = review_p.add_subparsers(dest="review_cmd", required=True)
    for name, func in [("plan", review_plan), ("status", review_status), ("synthesize", review_synthesize)]:
        p = review_sub.add_parser(name)
        p.add_argument("task_id", nargs="?", default="latest")
        p.set_defaults(func=func)
    rr = review_sub.add_parser("run")
    rr.add_argument("task_id")
    rr.add_argument("--lane", default="scope")
    rr.add_argument("--agent", choices=["codex", "claude", "cursor"], default="codex")
    rr.add_argument("--timeout", type=int, default=120)
    rr.add_argument("--dry-run", action="store_true")
    rr.set_defaults(func=review_run)

    pr_p = sub.add_parser("pr-review")
    pr_sub = pr_p.add_subparsers(dest="pr_cmd", required=True)
    prs = pr_sub.add_parser("start")
    prs.add_argument("source")
    prs.add_argument("--repo")
    prs.add_argument("--base")
    prs.add_argument("--task-id")
    prs.set_defaults(func=pr_review_start)
    prr = pr_sub.add_parser("run")
    prr.add_argument("task_id")
    prr.add_argument("--lane", default="auto")
    prr.add_argument("--agent", choices=["codex", "claude", "cursor"], default="codex")
    prr.add_argument("--max-lanes", type=int)
    prr.add_argument("--timeout", type=int, default=120)
    prr.add_argument("--dry-run", action="store_true")
    prr.set_defaults(func=pr_review_run)
    prsynth = pr_sub.add_parser("synthesize")
    prsynth.add_argument("task_id")
    prsynth.set_defaults(func=pr_review_synthesize)
    prfb = pr_sub.add_parser("feedback")
    prfb.add_argument("task_id")
    prfb.add_argument("--finding-id", required=True)
    prfb.add_argument("--outcome", required=True, choices=["posted", "accepted", "fixed", "rejected", "ignored"])
    prfb.add_argument("--note")
    prfb.set_defaults(func=pr_review_feedback)

    ew_p = sub.add_parser("external-write")
    ew_sub = ew_p.add_subparsers(dest="external_cmd", required=True)
    ewi = ew_sub.add_parser("intent")
    ewi.add_argument("task_id")
    ewi.add_argument("--provider", required=True)
    ewi.add_argument("--operation", required=True)
    ewi.add_argument("--target", required=True)
    ewi.add_argument("--summary", required=True)
    ewi.add_argument("--content-preview")
    ewi.add_argument("--ttl-hours", type=int, default=24)
    ewi.set_defaults(func=external_write_intent)
    for name, func in [("status", external_write_status), ("doctor", external_write_doctor)]:
        p = ew_sub.add_parser(name)
        p.add_argument("task_id", nargs="?", default="latest")
        p.set_defaults(func=func)

    mem_p = sub.add_parser("memory")
    mem_sub = mem_p.add_subparsers(dest="memory_cmd", required=True)
    mq = mem_sub.add_parser("query")
    mq.add_argument("query")
    mq.set_defaults(func=memory_query)
    mc = mem_sub.add_parser("candidate")
    mc.add_argument("--claim", required=True)
    mc.add_argument("--source", required=True)
    mc.add_argument("--confidence", default="medium")
    mc.set_defaults(func=memory_candidate)

    metrics_p = sub.add_parser("metrics")
    metrics_sub = metrics_p.add_subparsers(dest="metrics_cmd", required=True)
    export_p = metrics_sub.add_parser("export")
    export_p.set_defaults(func=metrics_export)

    eval_p = sub.add_parser("eval")
    eval_sub = eval_p.add_subparsers(dest="eval_cmd", required=True)
    er = eval_sub.add_parser("run")
    er.add_argument("which", nargs="?", default="all")
    er.add_argument("--no-record", action="store_true")
    er.set_defaults(func=eval_run)

    sc = sub.add_parser("self-check")
    sc.add_argument("--source-root")
    sc.add_argument("--json", action="store_true")
    sc.set_defaults(func=self_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except HarnessError as exc:
        print(f"agent-harness: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
