#!/usr/bin/env python3
"""Summarize per-run telemetry for a stage: tokens, cost, latency, denials, models."""
from __future__ import annotations

import argparse
import collections
import glob
import json
import statistics
from pathlib import Path


def q(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * len(s)))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    per = collections.defaultdict(lambda: collections.defaultdict(list))
    denials = collections.Counter()
    models = collections.Counter()
    errors = collections.Counter()
    n_runs = collections.Counter()

    for tf in glob.glob(f"/srv/ab/live/{args.stage}/shard-*/run-*/eval-*/*/telemetry.json"):
        variant = Path(tf).parent.name
        n_runs[variant] += 1
        try:
            d = json.loads(Path(tf).read_text(encoding="utf-8"))
        except Exception:
            errors[f"{variant}:unparseable_telemetry"] += 1
            continue
        if d.get("is_error"):
            errors[f"{variant}:{d.get('terminal_reason', 'error')}"] += 1
        u = d.get("usage", {}) or {}
        per[variant]["duration_ms"].append(d.get("duration_ms") or 0)
        per[variant]["api_ms"].append(d.get("duration_api_ms") or 0)
        per[variant]["turns"].append(d.get("num_turns") or 0)
        per[variant]["cost_usd"].append(d.get("total_cost_usd") or 0.0)
        per[variant]["out_tokens"].append(u.get("output_tokens") or 0)
        per[variant]["cache_read"].append(u.get("cache_read_input_tokens") or 0)
        per[variant]["cache_create"].append(u.get("cache_creation_input_tokens") or 0)
        per[variant]["total_billable_in"].append(
            (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0))
        for m in (d.get("modelUsage") or {}):
            models[f"{variant}:{m}"] += 1
        for pd in (d.get("permission_denials") or []):
            denials[f"{variant}:{pd.get('tool_name', 'unknown')}"] += 1

    summary = {"stage": args.stage, "runs_with_telemetry": dict(n_runs),
               "permission_denials": dict(denials) or "none",
               "models_seen": dict(models), "telemetry_errors": dict(errors) or "none",
               "per_variant": {}}
    for variant, metrics in per.items():
        summary["per_variant"][variant] = {
            k: {"n": len(v), "mean": round(statistics.fmean(v), 4) if v else None,
                "median": round(statistics.median(v), 4) if v else None,
                "p90": q(v, 0.9), "max": max(v) if v else None, "sum": round(sum(v), 4)}
            for k, v in metrics.items()
        }
    text = json.dumps(summary, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
