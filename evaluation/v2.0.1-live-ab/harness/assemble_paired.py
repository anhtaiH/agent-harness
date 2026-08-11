#!/usr/bin/env python3
"""Assemble paired per-metric CSVs from graded, judged A/B shards.

Un-blinding happens here and only here: blind-key.json is read AFTER judging has
completed, and is stored in the judge-private tree, outside every runner workspace.

Emits one CSV per metric with the control_correct/treatment_correct columns that
analyze_paired_noninferiority.py requires, plus a manifest of ties, attrition, and
judge agreement.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path

MECH_READABILITY = ("no_process_narration", "priority_labels_valid", "no_false_human_verification")


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace-glob", required=True, help="glob for shard workspaces")
    ap.add_argument("--judge-private-glob", required=True, help="glob for shard judge-private dirs")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--technical-role", default="technical",
                    help="judge role suffix, e.g. 'technical' or 'technical-prbench'")
    ap.add_argument("--metrics", choices=("golden", "prbench"), default="golden")
    args = ap.parse_args()

    METRIC_MAP = {
        "golden": (("blocker_recall", "blocker_recall"),
                   ("decision_accuracy", "decision_match"),
                   ("false_blocker", "false_blocker"),
                   ("useful_secondary", "useful_secondary")),
        "prbench": (("human_recall", "human_recall"),
                    ("any_fabricated", "any_fabricated"),
                    ("confirmed_count", "confirmed_count"),
                    ("plausible_count", "plausible_count")),
    }[args.metrics]

    args.out.mkdir(parents=True, exist_ok=True)
    ws_dirs = sorted(Path().glob(args.workspace_glob)) or [Path(p) for p in __import__("glob").glob(args.workspace_glob)]
    jp_dirs = {Path(p).name: Path(p) for p in __import__("glob").glob(args.judge_private_glob)}

    rows: list[dict] = []
    attrition: list[dict] = []
    counts = collections.Counter()

    for ws in ws_dirs:
        report_path = ws / "grade-report.json"
        if not report_path.exists():
            continue
        report = load_json(report_path)
        jp = jp_dirs.get(ws.name)
        key_path = jp / "blind-key.json" if jp else None
        blind = {}
        if key_path and key_path.exists():
            for entry in load_json(key_path):
                blind[(entry["case_id"], int(entry["run"]))] = {"A": entry["A"], "B": entry["B"]}

        for pair in report["pairs"]:
            cid, run = pair["case_id"], int(pair["run"])
            counts["pairs_total"] += 1
            if not pair.get("gradable"):
                counts["pairs_invalid"] += 1
                attrition.append({"case_id": cid, "run": run, "shard": ws.name,
                                  "reasons": pair.get("invalid_reasons", {})})
                continue
            mapping = blind.get((cid, run))
            if not mapping:
                counts["pairs_missing_blind_key"] += 1
                continue

            jout = Path(pair["judge_output"])
            tech_p = jout.with_suffix(jout.suffix + f".{args.technical_role}.json")
            auth_p = jout.with_suffix(jout.suffix + ".author.json")
            tech = load_json(tech_p) if tech_p.exists() else None
            auth = load_json(auth_p) if auth_p.exists() else None
            if not tech or "a" not in tech:
                counts["pairs_missing_technical_verdict"] += 1
                continue
            counts["pairs_graded"] += 1

            # slot -> variant
            slot_of = {mapping["A"]: "a", mapping["B"]: "b"}
            ctl, trt = slot_of["old_prompt"], slot_of["new_skill"]

            row = {"case_id": cid, "run": run, "shard": ws.name}
            for metric, key in METRIC_MAP:
                cv, tv = tech[ctl].get(key), tech[trt].get(key)
                row[f"{metric}__control"] = cv
                row[f"{metric}__treatment"] = tv

            mech = pair.get("mechanical", {})
            for variant, tag in (("old_prompt", "control"), ("new_skill", "treatment")):
                m = mech.get(variant, {})
                row[f"readability_fail__{tag}"] = 0 if all(m.get(k) for k in MECH_READABILITY) else 1
                row[f"output_contract_pass__{tag}"] = 1 if all(m.values()) else 0

            tp = (tech.get("technical_preference") or "tie").strip()
            row["tech_pref"] = {"A": mapping["A"], "B": mapping["B"]}.get(tp, "tie")
            ap_ = (auth or {}).get("author_preference", "tie")
            ap_ = ap_.strip() if isinstance(ap_, str) else "tie"
            row["author_pref"] = {"A": mapping["A"], "B": mapping["B"]}.get(ap_, "tie")
            counts[f"tech_pref_{row['tech_pref']}"] += 1
            counts[f"author_pref_{row['author_pref']}"] += 1
            if auth is None:
                counts["pairs_missing_author_verdict"] += 1
            rows.append(row)

    # ---- per-metric paired CSVs ----
    written = {}
    for metric in [m for m, _ in METRIC_MAP] + ["readability_fail", "output_contract_pass"]:
        out = args.out / f"paired_{metric}.csv"
        n = 0
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["case_id", "run", "control_correct", "treatment_correct"])
            for r in rows:
                c, t = r.get(f"{metric}__control"), r.get(f"{metric}__treatment")
                if c is None or t is None:      # not applicable (e.g. clean fixture recall)
                    continue
                w.writerow([r["case_id"], r["run"], int(c), int(t)])
                n += 1
        written[metric] = n

    for pref, name in (("tech_pref", "technical_preference"), ("author_pref", "author_preference")):
        out = args.out / f"paired_{name}.csv"
        n = 0
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["case_id", "run", "control_correct", "treatment_correct"])
            for r in rows:
                v = r[pref]
                w.writerow([r["case_id"], r["run"],
                            1 if v == "old_prompt" else 0,
                            1 if v == "new_skill" else 0])
                n += 1
        written[name] = n

    agree = sum(1 for r in rows if r["tech_pref"] == r["author_pref"])
    manifest = {
        "counts": dict(counts),
        "paired_rows_written": written,
        "judge_agreement": {
            "pairs_with_both_verdicts": len(rows),
            "agreeing": agree,
            "disagreeing": len(rows) - agree,
            "agreement_rate": round(agree / len(rows), 4) if rows else None,
            "note": "No human adjudication available in this environment; disagreements are reported unadjudicated.",
        },
        "attrition": attrition,
    }
    (args.out / "assembly-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (args.out / "paired-rows.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))
    print(json.dumps(manifest["judge_agreement"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
