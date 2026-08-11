#!/usr/bin/env python3
"""Paired statistics over a judged A/B workspace.

Reports paired results with counts and denominators:
- win/tie/loss counts per judge, exact sign-test (McNemar-style) p-values
- case-level majority aggregation across repetitions
- per-dimension score deltas with case-clustered bootstrap 95% CIs
- Wilson intervals for win rates and decision accuracy
- golden-fixture decision accuracy per variant (parsed from responses)
- efficiency medians/percentiles (tokens, cost, wall time, turns)
- blinding-leakage (redaction) summary and inter-judge agreement
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

DIMENSIONS = [
    "blocker recall and correctness", "false-positive control", "priority and merge action",
    "exact localization", "disconfirmation and evidence", "repairability", "lifecycle awareness",
    "useful non-blocking value", "QA feasibility", "public readability", "scope discipline", "author trust",
]


def binom_two_sided(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    def pmf(i: int) -> float:
        return math.comb(n, i) * 0.5 ** n
    p_obs = pmf(k)
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= p_obs + 1e-12))


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float, float]:
    if total == 0:
        return (0.0, 0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (p, max(0.0, centre - margin), min(1.0, centre + margin))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def latest_runs(workspace: Path) -> dict[tuple[str, int, str], dict[str, Any]]:
    latest: dict[tuple[str, int, str], dict[str, Any]] = {}
    for rec in load_jsonl(workspace / "runs.jsonl"):
        key = (str(rec["case_id"]), int(rec["run"]), rec["variant"])
        prev = latest.get(key)
        # A completed record wins over a stale 'failed' record appended by an
        # overlapping runner relaunch of the same unit.
        if prev is not None and prev.get("status") == "completed" and rec.get("status") != "completed":
            continue
        latest[key] = rec
    return latest


DECISION_PATTERNS = [
    ("request_changes", re.compile(r"request[\s_-]*changes", re.I)),
    ("approve", re.compile(r"\bapprove[sd]?\b|\bapproval\b", re.I)),
    ("comment", re.compile(r"^\s*decision[:\s]*comment\b|\breview (state|decision)[:\s]*comment\b", re.I | re.M)),
]


def parse_decision(text: str) -> str | None:
    scores: dict[str, int] = {}
    head = text[:4000]
    for name, pattern in DECISION_PATTERNS:
        hits = pattern.findall(head)
        if hits:
            scores[name] = len(hits) if isinstance(hits[0], str) else len(hits)
    if not scores:
        return None
    if "request_changes" in scores:
        return "request_changes"
    return max(scores, key=lambda k: scores[k])


def clustered_bootstrap_ci(pairs_by_case: dict[str, list[float]], iters: int = 5000, seed: int = 4242) -> tuple[float, float, float]:
    cases = sorted(pairs_by_case)
    if not cases:
        return (0.0, 0.0, 0.0)
    all_vals = [v for c in cases for v in pairs_by_case[c]]
    mean = sum(all_vals) / len(all_vals)
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        sample_cases = [cases[rng.randrange(len(cases))] for _ in cases]
        vals = [v for c in sample_cases for v in pairs_by_case[c]]
        means.append(sum(vals) / len(vals))
    means.sort()
    return (mean, means[int(0.025 * iters)], means[int(0.975 * iters) - 1])


def pct(values: list[float], q: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    idx = min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))
    return vals[idx]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--judges", nargs="*", default=["primary"])
    parser.add_argument("--out-prefix", default="stats")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    runs = latest_runs(workspace)

    summary: dict[str, Any] = {"workspace": str(workspace)}

    # ---- efficiency ----
    eff: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    status_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (case_id, run, variant), rec in runs.items():
        status_counts[variant][rec.get("status", "?")] += 1
        u = rec.get("usage") or {}
        if rec.get("status") == "completed":
            eff[variant]["wall_ms"].append(rec.get("wall_ms"))
            for key in ["input_tokens", "output_tokens", "cache_creation_input_tokens",
                        "cache_read_input_tokens", "total_cost_usd", "num_turns"]:
                if u.get(key) is not None:
                    eff[variant][key].append(u[key])
    summary["run_status_counts"] = {k: dict(v) for k, v in status_counts.items()}
    summary["efficiency"] = {
        variant: {
            key: {"n": len(vals), "median": pct(vals, 0.5), "p90": pct(vals, 0.9),
                  "mean": (sum(v for v in vals if v is not None) / len(vals)) if vals else None}
            for key, vals in metrics.items()
        }
        for variant, metrics in eff.items()
    }

    # ---- mechanical grading (bundled grade_live_ab.py output) ----
    mech: dict[str, list[float]] = defaultdict(list)
    mech_by_case: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (case_id, run, variant), rec in runs.items():
        gpath = Path(rec["run_dir"]) / "grading.json"
        if gpath.exists():
            rate = json.loads(gpath.read_text(encoding="utf-8"))["summary"]["pass_rate"]
            mech[variant].append(rate)
            mech_by_case[variant][case_id].append(rate)
    if mech:
        summary["mechanical"] = {
            variant: {"n": len(vals), "mean_pass_rate": round(sum(vals) / len(vals), 4)}
            for variant, vals in mech.items()
        }
        deltas_by_case: dict[str, list[float]] = defaultdict(list)
        for case_id in mech_by_case.get("new_skill", {}):
            new_vals = mech_by_case["new_skill"].get(case_id, [])
            old_vals = mech_by_case["old_prompt"].get(case_id, [])
            for n_v, o_v in zip(new_vals, old_vals):
                deltas_by_case[case_id].append(n_v - o_v)
        if deltas_by_case:
            mean, lo, hi = clustered_bootstrap_ci(deltas_by_case)
            summary["mechanical"]["paired_delta_new_minus_old"] = {"mean": round(mean, 4), "ci95": [round(lo, 4), round(hi, 4)]}

    # ---- decision accuracy vs ground truth (golden fixtures) ----
    decision_rows = []
    dec_correct: dict[str, int] = defaultdict(int)
    dec_total: dict[str, int] = defaultdict(int)
    dec_pair: dict[tuple[str, int], dict[str, bool]] = defaultdict(dict)
    for (case_id, run, variant), rec in runs.items():
        if rec.get("status") != "completed":
            continue
        task_file = Path(rec["run_dir"]) / "task.json"
        resp_file = Path(rec["run_dir"]) / "outputs" / "response.md"
        if not (task_file.exists() and resp_file.exists()):
            continue
        case = json.loads(task_file.read_text(encoding="utf-8"))
        expected = ((case.get("metadata") or {}).get("expected") or {}).get("decision")
        if not expected:
            continue
        parsed = parse_decision(resp_file.read_text(encoding="utf-8"))
        correct = parsed == expected
        dec_total[variant] += 1
        dec_correct[variant] += int(correct)
        dec_pair[(case_id, run)][variant] = correct
        decision_rows.append({"case_id": case_id, "run": run, "variant": variant,
                              "expected": expected, "parsed": parsed, "correct": correct})
    if dec_total:
        b = sum(1 for d in dec_pair.values() if d.get("new_skill") and not d.get("old_prompt"))
        c = sum(1 for d in dec_pair.values() if d.get("old_prompt") and not d.get("new_skill"))
        summary["decision_accuracy"] = {
            variant: {"correct": dec_correct[variant], "total": dec_total[variant],
                      "wilson": [round(x, 4) for x in wilson(dec_correct[variant], dec_total[variant])]}
            for variant in dec_total
        }
        summary["decision_accuracy"]["mcnemar"] = {
            "new_only_correct": b, "old_only_correct": c, "p_two_sided": round(binom_two_sided(b, b + c), 5)
        }

    # ---- blind judge verdicts ----
    judge_summaries = {}
    winner_by_pair_by_judge: dict[str, dict[tuple[str, int], str]] = {}
    csv_rows: list[dict[str, Any]] = []
    for tag in args.judges:
        jdir = workspace / "judging" / tag
        mapping = {(str(m["case_id"]), int(m["run"])): m for m in load_jsonl(jdir / "mapping.jsonl")}
        verdicts = load_jsonl(jdir / "verdicts.jsonl")
        wins: dict[str, int] = defaultdict(int)
        dim_deltas_by_case: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        winner_by_pair: dict[tuple[str, int], str] = {}
        redactions = {"old_prompt": 0, "new_skill": 0, "pairs_with_any": 0}
        adjudication = []
        crit_counts: dict[str, int] = defaultdict(int)
        for v in verdicts:
            if not v.get("ok"):
                continue
            key = (str(v["case_id"]), int(v["run"]))
            m = mapping.get(key)
            if not m:
                continue
            label = v["winner_label"]
            winner_variant = "tie" if label == "tie" else m[label]
            wins[winner_variant] += 1
            winner_by_pair[key] = winner_variant
            rc = v.get("redaction_counts") or {}
            redactions["old_prompt"] += rc.get("old_prompt", 0)
            redactions["new_skill"] += rc.get("new_skill", 0)
            if (rc.get("old_prompt", 0) + rc.get("new_skill", 0)) > 0:
                redactions["pairs_with_any"] += 1
            verdict = v.get("verdict") or {}
            scores = verdict.get("scores") or {}
            crit = verdict.get("critical_failures") or {}
            for side in ("A", "B"):
                if crit.get(side):
                    crit_counts[m[side]] += len(crit[side])
            if v.get("human_adjudication_needed"):
                adjudication.append({"case_id": v["case_id"], "run": v["run"],
                                     "reason": (verdict.get("reason") or "")[:400]})
            a_scores, b_scores = scores.get("A") or {}, scores.get("B") or {}
            new_side = "A" if m["A"] == "new_skill" else "B"
            def norm_dim(name: str) -> str:
                return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            b_norm = {norm_dim(k): k for k in b_scores}
            for dim in a_scores:
                key = norm_dim(dim)
                if key not in b_norm:
                    continue
                try:
                    a_val, b_val = float(a_scores[dim]), float(b_scores[b_norm[key]])
                except (TypeError, ValueError):
                    continue
                delta = (a_val - b_val) if new_side == "A" else (b_val - a_val)
                dim_deltas_by_case[key][str(v["case_id"])].append(delta)
            csv_rows.append({
                "judge": tag, "case_id": v["case_id"], "run": v["run"],
                "winner_variant": winner_variant, "confidence": v.get("confidence"),
                "adjudication": v.get("human_adjudication_needed"),
                **{f"delta_{dim.replace(' ', '_')}": round(sum(d) / len(d), 3)
                   for dim, cases in dim_deltas_by_case.items()
                   for cid, d in cases.items() if cid == str(v["case_id"]) and int(v["run"]) == v["run"]},
            })
        n_new, n_old, n_tie = wins.get("new_skill", 0), wins.get("old_prompt", 0), wins.get("tie", 0)
        decided = n_new + n_old
        case_majority: dict[str, str] = {}
        by_case: dict[str, list[str]] = defaultdict(list)
        for (case_id, run), w in winner_by_pair.items():
            by_case[case_id].append(w)
        for case_id, ws in by_case.items():
            counts = {w: ws.count(w) for w in set(ws)}
            case_majority[case_id] = max(counts, key=lambda k: (counts[k], k == "tie"))
        cm_new = sum(1 for w in case_majority.values() if w == "new_skill")
        cm_old = sum(1 for w in case_majority.values() if w == "old_prompt")
        cm_tie = sum(1 for w in case_majority.values() if w == "tie")
        judge_summaries[tag] = {
            "judged_pairs": len(winner_by_pair),
            "wins": {"new_skill": n_new, "old_prompt": n_old, "tie": n_tie},
            "win_rate_new_among_decided": [round(x, 4) for x in wilson(n_new, decided)] if decided else None,
            "sign_test_p_two_sided": round(binom_two_sided(n_new, decided), 5) if decided else None,
            "case_majority": {"new_skill": cm_new, "old_prompt": cm_old, "tie": cm_tie,
                              "cases": len(case_majority)},
            "case_majority_sign_p": round(binom_two_sided(cm_new, cm_new + cm_old), 5) if (cm_new + cm_old) else None,
            "dimension_deltas_new_minus_old": {
                dim: {"mean": round(m, 3), "ci95": [round(lo, 3), round(hi, 3)],
                      "n_pairs": sum(len(v) for v in cases.values())}
                for dim, cases in sorted(dim_deltas_by_case.items())
                for (m, lo, hi) in [clustered_bootstrap_ci(cases)]
            },
            "critical_failures_by_variant": dict(crit_counts),
            "redaction_leakage": redactions,
            "human_adjudication_queue": adjudication,
        }
        winner_by_pair_by_judge[tag] = winner_by_pair

    if len(args.judges) >= 2:
        t1, t2 = args.judges[0], args.judges[1]
        common = set(winner_by_pair_by_judge.get(t1, {})) & set(winner_by_pair_by_judge.get(t2, {}))
        if common:
            agree = sum(1 for k in common if winner_by_pair_by_judge[t1][k] == winner_by_pair_by_judge[t2][k])
            labels = ["new_skill", "old_prompt", "tie"]
            p_o = agree / len(common)
            marg1 = {l: sum(1 for k in common if winner_by_pair_by_judge[t1][k] == l) / len(common) for l in labels}
            marg2 = {l: sum(1 for k in common if winner_by_pair_by_judge[t2][k] == l) / len(common) for l in labels}
            p_e = sum(marg1[l] * marg2[l] for l in labels)
            kappa = (p_o - p_e) / (1 - p_e) if p_e < 1 else None
            summary["inter_judge"] = {"common_pairs": len(common), "raw_agreement": round(p_o, 4),
                                      "cohens_kappa": round(kappa, 4) if kappa is not None else None}

    summary["judges"] = judge_summaries

    out_json = workspace / f"{args.out_prefix}-summary.json"
    out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if csv_rows:
        fieldnames = sorted({k for r in csv_rows for k in r})
        with (workspace / f"{args.out_prefix}-paired-scores.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
    if decision_rows:
        with (workspace / f"{args.out_prefix}-decisions.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=sorted(decision_rows[0]))
            writer.writeheader()
            writer.writerows(decision_rows)
    print(json.dumps(summary, indent=2)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
