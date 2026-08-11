#!/usr/bin/env python3
"""Parallel paired A/B runner: frozen v19 prompt (control) vs reviewing-pull-requests skill (treatment).

Derived from the bundled evaluation/scripts/run_live_ab.py. Preserves its
directory layout, manifest, per-case randomized variant order, and prompt
templates, and adds:

  - bounded parallelism (--jobs), since the bundled runner is strictly serial
  - `claude -p` headless invocation with identical model/effort/tools/timeout
    for both variants
  - full token/cost/turn metrics captured from the CLI JSON envelope
  - per-run isolation: cwd is the run dir; the treatment gets a private copy
    of the skill inside its run dir; children get read-only tools only
  - anti-cheat: task.json (which contains graded assertions / ground truth)
    is written only AFTER the child process finishes
  - resumability: completed run dirs are skipped on re-invocation

Both variants receive byte-identical harness treatment; only the policy
payload (embedded v19 prompt vs. skill activation pointer) differs.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import random
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

READ_ONLY_ALLOWED = "Read,Grep,Glob,Task"
DISALLOWED = "Bash,Write,Edit,NotebookEdit,WebFetch,WebSearch,Skill,SlashCommand,KillShell,BashOutput"
STRIP_ENV = ["GH_TOKEN", "GITHUB_TOKEN", "NPM_TOKEN", "CLOUDSDK_AUTH_ACCESS_TOKEN"]

_lock = threading.Lock()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(value: object) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in str(value)).strip("-")


def build_prompt(case: dict[str, Any], variant: str, baseline_text: str, input_rel: list[str]) -> str:
    task = case["prompt"]
    inputs = "\n".join(f"- {p}" for p in input_rel) or "- none"
    common = (
        "Execute this evaluation in a clean context.\n\n"
        f"Task:\n{task}\n\n"
        f"Input files (paths relative to the current working directory):\n{inputs}\n\n"
        "Produce the complete final user-facing output as your final message. "
        "Do not mention that this is an A/B evaluation.\n"
    )
    if variant == "new_skill":
        return (
            f"{common}\n"
            "Activate and follow the Agent Skill located in the local directory:\n"
            "./skill\n\n"
            "Start by reading ./skill/SKILL.md and load its references just in time as it directs.\n"
            "Use preview mode unless the task itself explicitly requests submission. "
            "Do not read or use any frozen baseline prompt.\n"
        )
    return (
        f"{common}\n"
        "Use the following frozen review prompt as the complete review policy. "
        "Do not load any Agent Skill.\n\n"
        f"<baseline_prompt>\n{baseline_text}\n</baseline_prompt>\n"
    )


def parse_envelope(stdout: str) -> dict[str, Any] | None:
    stdout = stdout.strip()
    if not stdout:
        return None
    # The envelope is the last JSON object on stdout.
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        idx = stdout.rfind('\n{"')
        if idx >= 0:
            try:
                return json.loads(stdout[idx:])
            except json.JSONDecodeError:
                return None
    return None


def run_child(prompt_file: Path, run_dir: Path, model: str, effort: str, timeout: int) -> dict[str, Any]:
    cmd = [
        "claude", "-p",
        "--model", model,
        "--effort", effort,
        "--output-format", "json",
        "--strict-mcp-config",
        "--allowedTools", READ_ONLY_ALLOWED,
        "--disallowedTools", DISALLOWED,
    ]
    env = os.environ.copy()
    for key in STRIP_ENV:
        env.pop(key, None)
    started = time.perf_counter()
    try:
        with prompt_file.open("rb") as fh:
            proc = subprocess.run(
                cmd, cwd=run_dir, env=env, stdin=fh,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
            )
        wall_ms = round((time.perf_counter() - started) * 1000)
        stdout = proc.stdout.decode("utf-8", "replace")
        stderr = proc.stderr.decode("utf-8", "replace")
        return {"exit_code": proc.returncode, "wall_ms": wall_ms, "stdout": stdout, "stderr": stderr, "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        wall_ms = round((time.perf_counter() - started) * 1000)
        return {
            "exit_code": None, "wall_ms": wall_ms,
            "stdout": (exc.stdout or b"").decode("utf-8", "replace"),
            "stderr": (exc.stderr or b"").decode("utf-8", "replace"),
            "timed_out": True,
        }


def execute_unit(unit: dict[str, Any], args: argparse.Namespace, baseline_text: str,
                 skill_dir: Path, evals_dir: Path, workspace: Path) -> dict[str, Any]:
    case, run_index, variant, order = unit["case"], unit["run"], unit["variant"], unit["order"]
    case_id = slug(case["id"])
    run_dir = workspace / f"run-{run_index:02d}" / f"eval-{case_id}" / variant
    response_file = run_dir / "outputs" / "response.md"
    timing_file = run_dir / "timing.json"
    if timing_file.exists() and response_file.exists():
        record = json.loads(timing_file.read_text(encoding="utf-8")).get("record")
        if record:
            return {**record, "resumed": True}

    if run_dir.exists():
        shutil.rmtree(run_dir)
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)

    input_rel: list[str] = []
    for raw in case.get("files", []):
        # Mirror the bundled copy_inputs(): "evals/"-prefixed paths resolve
        # against the skill root (evals dir's parent), others against evals dir.
        base = evals_dir.parent if raw.startswith("evals/") else evals_dir
        src = (base / raw).resolve()
        if not src.exists():
            raise FileNotFoundError(f"eval input not found: {raw} -> {src}")
        dst = run_dir / "inputs" / src.name
        # Anti-leak: strip ground-truth keys from runner-visible JSON copies.
        # Judges receive full ground truth separately via task.json.
        if src.suffix == ".json":
            try:
                payload = json.loads(src.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    for leak_key in ("expected", "human_review_comments"):
                        payload.pop(leak_key, None)
                dst.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                shutil.copy2(src, dst)
        else:
            shutil.copy2(src, dst)
        input_rel.append(f"inputs/{src.name}")

    if variant == "new_skill":
        shutil.copytree(skill_dir, run_dir / "skill",
                        ignore=shutil.ignore_patterns("evals", "__pycache__"))

    prompt_file = run_dir / "prompt.md"
    prompt_file.write_text(build_prompt(case, variant, baseline_text, input_rel), encoding="utf-8")

    attempts = 0
    result: dict[str, Any] = {}
    envelope = None
    while attempts < args.max_attempts:
        attempts += 1
        result = run_child(prompt_file, run_dir, args.model, args.effort, args.timeout)
        envelope = parse_envelope(result["stdout"])
        if result["timed_out"]:
            break
        if result["exit_code"] == 0 and envelope and envelope.get("result"):
            break
        time.sleep(5 * attempts)

    (run_dir / "stdout.txt").write_text(result["stdout"], encoding="utf-8")
    (run_dir / "stderr.txt").write_text(result["stderr"], encoding="utf-8")

    response_text = ""
    usage: dict[str, Any] = {}
    if envelope:
        response_text = envelope.get("result") or ""
        u = envelope.get("usage", {})
        usage = {
            "input_tokens": u.get("input_tokens"),
            "output_tokens": u.get("output_tokens"),
            "cache_creation_input_tokens": u.get("cache_creation_input_tokens"),
            "cache_read_input_tokens": u.get("cache_read_input_tokens"),
            "total_cost_usd": envelope.get("total_cost_usd"),
            "num_turns": envelope.get("num_turns"),
            "duration_api_ms": envelope.get("duration_api_ms"),
            "duration_ms": envelope.get("duration_ms"),
            "permission_denials": len(envelope.get("permission_denials") or []),
            "model_usage_models": sorted((envelope.get("modelUsage") or {}).keys()),
            "is_error": envelope.get("is_error"),
            "subtype": envelope.get("subtype"),
        }
    if result["timed_out"]:
        status = "timeout"
    elif result["exit_code"] == 0 and response_text.strip() and not (envelope or {}).get("is_error"):
        status = "completed"
    else:
        status = "failed"

    # Only a genuine model response becomes a gradable artifact. API error text
    # (e.g. safety-classifier refusals) must never be graded as a review.
    if status == "completed":
        response_file.write_text(response_text, encoding="utf-8")
    elif response_file.exists():
        response_file.unlink()
    if status != "completed" and response_text.strip():
        (run_dir / "error_message.txt").write_text(response_text, encoding="utf-8")

    record = {
        "case_id": case["id"],
        "run": run_index,
        "variant": variant,
        "randomized_order": order,
        "run_dir": str(run_dir),
        "status": status,
        "attempts": attempts,
        "exit_code": result["exit_code"],
        "wall_ms": result["wall_ms"],
        "usage": usage,
    }
    # Ground truth is written only after the child has finished (anti-cheat).
    (run_dir / "task.json").write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
    timing_file.write_text(json.dumps({"record": record}, indent=2) + "\n", encoding="utf-8")
    with _lock:
        with (workspace / "runs.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evals", type=Path, required=True)
    parser.add_argument("--skill-dir", type=Path, required=True)
    parser.add_argument("--baseline-prompt", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only", nargs="*", help="restrict to these case ids")
    parser.add_argument("--seed", type=int, default=20260810)
    parser.add_argument("--timeout", type=int, default=1500)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--model", default="claude-fable-5")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--max-attempts", type=int, default=2)
    args = parser.parse_args()

    evals_path = args.evals.resolve()
    skill_dir = args.skill_dir.resolve()
    baseline = args.baseline_prompt.resolve()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    cases = json.loads(evals_path.read_text(encoding="utf-8"))["evals"]
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    if args.limit:
        cases = cases[: args.limit]
    baseline_text = baseline.read_text(encoding="utf-8")

    manifest = {
        "evals": str(evals_path),
        "evals_sha": file_sha(evals_path),
        "skill_dir": str(skill_dir),
        "skill_sha": file_sha(skill_dir / "SKILL.md"),
        "baseline_prompt": str(baseline),
        "baseline_sha": file_sha(baseline),
        "runs": args.runs,
        "seed": args.seed,
        "case_count": len(cases),
        "model": args.model,
        "effort": args.effort,
        "timeout_s": args.timeout,
        "jobs": args.jobs,
        "allowed_tools": READ_ONLY_ALLOWED,
        "disallowed_tools": DISALLOWED,
    }
    (workspace / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    units: list[dict[str, Any]] = []
    for run_index in range(1, args.runs + 1):
        for case in cases:
            pair_seed = f"{args.seed}:{run_index}:{case['id']}"
            rng = random.Random(int(hashlib.sha256(pair_seed.encode()).hexdigest()[:12], 16))
            variants = ["old_prompt", "new_skill"]
            rng.shuffle(variants)
            for order, variant in enumerate(variants, start=1):
                units.append({"case": case, "run": run_index, "variant": variant, "order": order})

    print(f"scheduling {len(units)} runs with jobs={args.jobs}", flush=True)
    done = 0
    failures = 0
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(execute_unit, u, args, baseline_text, skill_dir, evals_path.parent, workspace) for u in units]
        for fut in cf.as_completed(futures):
            record = fut.result()
            done += 1
            if record["status"] != "completed":
                failures += 1
            if done % 10 == 0 or done == len(units):
                print(f"progress {done}/{len(units)} (failures={failures})", flush=True)

    summary = {"total_runs": len(units), "failures": failures, "workspace": str(workspace)}
    (workspace / "run-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
