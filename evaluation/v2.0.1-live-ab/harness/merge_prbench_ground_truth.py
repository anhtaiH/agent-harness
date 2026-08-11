#!/usr/bin/env python3
"""Inject SWE-PRBench human review comments into the runner-generated judge-private tree.

The shipped importer stores human comments in its own judge-private directory, keyed by
task id, while run_live_ab.py generates a judge-private tree keyed by run/case. The
technical judge needs both in one file. This runs AFTER all Stage 4 inference has exited,
and writes only inside the judge-private tree, which every runner sandbox hides.
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--importer-judge-private", required=True)
    ap.add_argument("--stage-judge-private-glob", required=True)
    args = ap.parse_args()

    src = {Path(p).stem: json.loads(Path(p).read_text(encoding="utf-8"))
           for p in glob.glob(f"{args.importer_judge_private}/*.json")}

    merged = missing = 0
    for gt_path in glob.glob(f"{args.stage_judge_private_glob}/**/ground-truth.json", recursive=True):
        p = Path(gt_path)
        payload = json.loads(p.read_text(encoding="utf-8"))
        case_id = str(payload.get("case_id") or payload.get("source_case") or "")
        task = case_id.replace("swe-prbench-", "")
        entry = src.get(task)
        if not entry:
            missing += 1
            continue
        gt = payload.setdefault("ground_truth", {})
        gt["human_review_comments"] = (entry.get("ground_truth") or {}).get("human_review_comments", [])
        gt["source"] = "SWE-PRBench human maintainer review comments"
        p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        merged += 1

    print(json.dumps({"merged": merged, "missing_source": missing,
                      "importer_cases": len(src)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
