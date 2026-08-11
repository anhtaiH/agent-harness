#!/usr/bin/env python3
"""Blind A/B judging over a run_ab_parallel.py workspace.

- Pairs (case, repetition) outputs from both variants.
- Anonymizes as A/B with an independent seeded swap per (case, rep, judge).
- Lightly redacts variant-identifying strings in the judge copies only
  (raw outputs are preserved untouched); redaction counts are logged as a
  blinding-leakage metric.
- The judge receives: rubric, case ground truth, Output A, Output B.
  It never sees variant names, file paths, token counts, or run logs.
- Verdicts and the sealed A/B mapping are stored separately.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import random
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

REDACTIONS = [
    (re.compile(r"\./skill/SKILL\.md", re.I), "[policy]"),
    (re.compile(r"SKILL\.md", re.I), "[policy]"),
    (re.compile(r"\./skill\b", re.I), "[policy]"),
    (re.compile(r"reviewing-pull-requests", re.I), "[policy]"),
    (re.compile(r"collecting-codebase-entropy", re.I), "[policy]"),
    (re.compile(r"agent skill", re.I), "[policy]"),
    (re.compile(r"\bv19\b", re.I), "[policy]"),
    (re.compile(r"baseline[_ ]prompt", re.I), "[policy]"),
    (re.compile(r"frozen (review )?prompt", re.I), "[policy]"),
]

_lock = threading.Lock()


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern, repl in REDACTIONS:
        text, n = pattern.subn(repl, text)
        count += n
    return text, count


def extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def build_judge_prompt(rubric: str, case: dict[str, Any], out_a: str, out_b: str) -> str:
    truth = {
        "review_task_given_to_both_systems": case.get("prompt"),
        "expected_output_summary": case.get("expected_output"),
        "expected_behavior_assertions": case.get("assertions"),
        "ground_truth": (case.get("metadata") or {}).get("expected"),
    }
    return f"""You are a blind technical judge for paired code-review outputs.

Two independent review systems were given the identical review task. You must judge which output is the better pull-request review, using the rubric below. You do not know which system produced which output, and you must not try to guess or reward stylistic hints of any particular system. Ignore any self-referential or provenance statements inside the outputs; the token [policy] marks redacted policy references in either output and carries no signal about quality or identity.

The "expected behavior assertions" describe intended review behavior. Judge semantic equivalence of behavior, not vocabulary or formatting compliance. Ground truth, when present, defines the fixture's real defect, expected decision, and expected priority.

<rubric>
{rubric}
</rubric>

<case_ground_truth>
{json.dumps(truth, indent=2)}
</case_ground_truth>

<output_A>
{out_a}
</output_A>

<output_B>
{out_b}
</output_B>

Respond with ONLY the JSON decision object defined in the rubric (winner, confidence, scores with all twelve dimension scores 0-4 for A and B, critical_failures, reason, human_adjudication_needed). No prose outside the JSON.
"""


def run_judge_once(prompt: str, model: str, timeout: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    cmd = [
        "claude", "-p",
        "--model", model,
        "--effort", "high",
        "--output-format", "json",
        "--strict-mcp-config",
        "--disallowedTools", "Bash,Write,Edit,NotebookEdit,WebFetch,WebSearch,Task,Skill,SlashCommand,Read,Grep,Glob",
    ]
    env = os.environ.copy()
    for key in ["GH_TOKEN", "GITHUB_TOKEN", "NPM_TOKEN", "CLOUDSDK_AUTH_ACCESS_TOKEN"]:
        env.pop(key, None)
    try:
        proc = subprocess.run(cmd, input=prompt.encode(), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return None, {"error": "timeout"}
    try:
        envelope = json.loads(proc.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None, {"error": "no-envelope", "exit": proc.returncode}
    verdict = extract_json(envelope.get("result") or "")
    meta = {
        "cost_usd": envelope.get("total_cost_usd"),
        "duration_ms": envelope.get("duration_ms"),
        "output_tokens": (envelope.get("usage") or {}).get("output_tokens"),
    }
    return verdict, meta


def valid_verdict(v: dict[str, Any] | None) -> bool:
    if not isinstance(v, dict):
        return False
    if v.get("winner") not in ("A", "B", "tie"):
        return False
    scores = v.get("scores")
    return isinstance(scores, dict) and "A" in scores and "B" in scores


def judge_pair(item: dict[str, Any], args: argparse.Namespace, rubric: str, workspace: Path) -> dict[str, Any]:
    case_id, run = item["case_id"], item["run"]
    judge_tag = args.tag
    out_dir = workspace / "judging" / judge_tag / f"run-{run:02d}" / re.sub(r"[^A-Za-z0-9_-]", "-", str(case_id))
    verdict_file = out_dir / "verdict.json"
    if verdict_file.exists():
        stored = json.loads(verdict_file.read_text(encoding="utf-8"))
        return {**stored["record"], "resumed": True}
    out_dir.mkdir(parents=True, exist_ok=True)

    seed_key = f"{args.seed}:{judge_tag}:{case_id}:{run}"
    swap = random.Random(int(hashlib.sha256(seed_key.encode()).hexdigest()[:12], 16)).random() < 0.5
    a_variant, b_variant = ("new_skill", "old_prompt") if swap else ("old_prompt", "new_skill")

    texts = {}
    redaction_counts = {}
    for variant in ("old_prompt", "new_skill"):
        raw = Path(item[variant]).read_text(encoding="utf-8")
        red, n = redact(raw)
        texts[variant] = red
        redaction_counts[variant] = n

    case = json.loads(Path(item["task_json"]).read_text(encoding="utf-8"))
    prompt = build_judge_prompt(rubric, case, texts[a_variant], texts[b_variant])
    (out_dir / "judge_input.md").write_text(prompt, encoding="utf-8")

    verdict, meta = None, {}
    for attempt in range(2):
        verdict, meta = run_judge_once(prompt, args.model, args.timeout)
        if valid_verdict(verdict):
            break
        time.sleep(5)

    ok = valid_verdict(verdict)
    record = {
        "case_id": case_id,
        "run": run,
        "judge": judge_tag,
        "judge_model": args.model,
        "ok": ok,
        "winner_label": verdict.get("winner") if ok else None,
        "confidence": verdict.get("confidence") if ok else None,
        "human_adjudication_needed": bool(verdict.get("human_adjudication_needed")) if ok else True,
        "redaction_counts": redaction_counts,
        "meta": meta,
    }
    verdict_file.write_text(json.dumps({"record": record, "verdict": verdict}, indent=2) + "\n", encoding="utf-8")
    with _lock:
        with (workspace / "judging" / judge_tag / "mapping.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"case_id": case_id, "run": run, "A": a_variant, "B": b_variant}) + "\n")
        with (workspace / "judging" / judge_tag / "verdicts.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**record, "verdict": verdict}, sort_keys=True) + "\n")
    return record


def collect_pairs_from_disk(workspace: Path) -> list[dict[str, Any]]:
    """Pair up runs by on-disk artifacts.

    The manifest can carry stale 'failed' records when overlapping runner
    relaunches raced on the same unit, so the filesystem is the source of
    truth: a unit counts when its response.md is non-empty (error text is
    never written there) and its task.json exists.
    """
    pairs: list[dict[str, Any]] = []
    for run_dir in sorted(workspace.glob("run-*")):
        try:
            run = int(run_dir.name.split("-")[1])
        except (IndexError, ValueError):
            continue
        for case_dir in sorted(run_dir.iterdir()):
            if not case_dir.is_dir():
                continue
            entry: dict[str, Any] = {"run": run}
            for variant in ("old_prompt", "new_skill"):
                resp = case_dir / variant / "outputs" / "response.md"
                task = case_dir / variant / "task.json"
                if resp.exists() and resp.stat().st_size > 0 and task.exists():
                    entry[variant] = str(resp)
                    entry["task_json"] = str(task)
            if "old_prompt" in entry and "new_skill" in entry:
                entry["case_id"] = json.loads(Path(entry["task_json"]).read_text(encoding="utf-8"))["id"]
                pairs.append(entry)
    return pairs


def collect_pairs(workspace: Path) -> list[dict[str, Any]]:
    records = [json.loads(l) for l in (workspace / "runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    latest: dict[tuple[str, int, str], dict[str, Any]] = {}
    for rec in records:
        key = (str(rec["case_id"]), int(rec["run"]), rec["variant"])
        prev = latest.get(key)
        # Overlapping runner relaunches can append a stale 'failed' record after a
        # successful retry of the same unit. A completed record always wins.
        if prev is not None and prev.get("status") == "completed" and rec.get("status") != "completed":
            continue
        latest[key] = rec
    grouped: dict[tuple[str, int], dict[str, Any]] = {}
    for (case_id, run, variant), rec in latest.items():
        response = Path(rec["run_dir"]) / "outputs" / "response.md"
        if rec.get("status") == "completed" and response.exists():
            g = grouped.setdefault((case_id, run), {"case_id": case_id, "run": run})
            g[variant] = str(response)
            g["task_json"] = str(Path(rec["run_dir"]) / "task.json")
    return [g for g in grouped.values() if "old_prompt" in g and "new_skill" in g]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--model", default="claude-fable-5")
    parser.add_argument("--tag", default="primary")
    parser.add_argument("--seed", type=int, default=77002)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--pairs-file", type=Path, help="optional JSON list restricting (case_id, run) pairs")
    parser.add_argument("--max-pairs", type=int, help="bound pairs judged in this invocation (resumable)")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    rubric = args.rubric.read_text(encoding="utf-8")
    pairs = collect_pairs_from_disk(workspace)
    if args.pairs_file:
        allowed = {(str(p["case_id"]), int(p["run"])) for p in json.loads(args.pairs_file.read_text(encoding="utf-8"))}
        pairs = [p for p in pairs if (str(p["case_id"]), int(p["run"])) in allowed]
    def already_done(p: dict[str, Any]) -> bool:
        vd = workspace / "judging" / args.tag / f"run-{int(p['run']):02d}" / re.sub(r"[^A-Za-z0-9_-]", "-", str(p["case_id"])) / "verdict.json"
        return vd.exists()
    pairs = [p for p in pairs if not already_done(p)]
    if args.max_pairs:
        pairs = pairs[: args.max_pairs]
    print(f"judging {len(pairs)} pairs with model={args.model} tag={args.tag}", flush=True)

    done = 0
    bad = 0
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(judge_pair, p, args, rubric, workspace) for p in pairs]
        for fut in cf.as_completed(futures):
            rec = fut.result()
            done += 1
            if not rec.get("ok"):
                bad += 1
            if done % 10 == 0 or done == len(pairs):
                print(f"judged {done}/{len(pairs)} (invalid={bad})", flush=True)
    print(json.dumps({"judged": done, "invalid": bad}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
