#!/usr/bin/env python3
"""Select (case, run) pairs for second-judge escalation per START_HERE_WORK_ULTRA.md:

- all pairs on ground-truth P0/P1 fixtures where the primary judge saw a real
  quality difference (non-tie) or flagged critical failures
- all pairs where one variant approves and the other blocks (parsed decisions)
- all structural-simplification-family pairs with a non-tie primary verdict
- all pairs the primary judge flagged for human adjudication
- a seeded 20% random sample of the remaining pairs
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

STRUCTURAL_HINTS = re.compile(
    r"false-dry|large-cohesive|legitimate-adapter|duplicate-business-rule|"
    r"dynamic-registry|stale-flag|structural|refactor|dry", re.I)

APPROVE = re.compile(r"proposed submission type\s*\n+\s*approve", re.I)
BLOCK = re.compile(r"proposed submission type\s*\n+\s*request", re.I)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def parse_decision(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if BLOCK.search(text):
        return "block"
    if APPROVE.search(text):
        return "approve"
    if re.search(r"request[\s_-]*changes", text[:3000], re.I):
        return "block"
    if re.search(r"\bapprove\b", text[:3000], re.I):
        return "approve"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--primary-tag", default="primary")
    parser.add_argument("--seed", type=int, default=90210)
    parser.add_argument("--sample-rate", type=float, default=0.2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()

    runs = load_jsonl(workspace / "runs.jsonl")
    latest: dict[tuple[str, int, str], dict] = {}
    for rec in runs:
        latest[(str(rec["case_id"]), int(rec["run"]), rec["variant"])] = rec

    verdicts = {(str(v["case_id"]), int(v["run"])): v
                for v in load_jsonl(workspace / "judging" / args.primary_tag / "verdicts.jsonl") if v.get("ok")}

    selected: dict[tuple[str, int], list[str]] = {}

    def add(key: tuple[str, int], reason: str) -> None:
        selected.setdefault(key, []).append(reason)

    for key, v in verdicts.items():
        case_id, run = key
        verdict = v.get("verdict") or {}
        crit = verdict.get("critical_failures") or {}
        old_rec = latest.get((case_id, run, "old_prompt"))
        new_rec = latest.get((case_id, run, "new_skill"))
        if not (old_rec and new_rec):
            continue
        task = json.loads((Path(old_rec["run_dir"]) / "task.json").read_text(encoding="utf-8"))
        expected = ((task.get("metadata") or {}).get("expected") or {})
        gt_priority = expected.get("priority") or ""

        if gt_priority in ("P0", "P1") and (v["winner_label"] != "tie" or crit.get("A") or crit.get("B")):
            add(key, f"gt-{gt_priority}-difference")
        d_old = parse_decision(Path(old_rec["run_dir"]) / "outputs" / "response.md")
        d_new = parse_decision(Path(new_rec["run_dir"]) / "outputs" / "response.md")
        if d_old and d_new and d_old != d_new:
            add(key, f"decision-divergence({d_old}-vs-{d_new})")
        if STRUCTURAL_HINTS.search(case_id) and v["winner_label"] != "tie":
            add(key, "structural-non-tie")
        if v.get("human_adjudication_needed"):
            add(key, "primary-flagged-adjudication")

    remaining = [k for k in verdicts if k not in selected]
    rng = random.Random(args.seed)
    sample_n = round(len(remaining) * args.sample_rate)
    for key in rng.sample(remaining, min(sample_n, len(remaining))):
        add(key, "random-20pct-sample")

    out = [{"case_id": c, "run": r, "reasons": reasons} for (c, r), reasons in sorted(selected.items())]
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"escalated_pairs": len(out), "of_total": len(verdicts),
                      "reasons_histogram": {reason: sum(1 for o in out for rr in o['reasons'] if rr.startswith(reason.split('(')[0]))
                                            for reason in {r.split('(')[0] for o in out for r in o['reasons']}}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
