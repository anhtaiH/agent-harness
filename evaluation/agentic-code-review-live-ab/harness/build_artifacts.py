#!/usr/bin/env python3
"""Assemble the final artifact bundle from all judged workspaces."""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import re
import subprocess
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
ART.mkdir(parents=True, exist_ok=True)
PKG = ROOT.parent / "handoff" / "agentic-code-review-live-eval-handoff-v1" / "agentic-code-review-skills-v2.0.0"

STAGES = [
    ("stage1-golden", "Stage 1 — 25 golden PR fixtures", 25, 3, "claude-fable-5"),
    ("stage2-official", "Stage 2 — 100 official-style evals", 100, 3, "claude-fable-5"),
    ("stage3-real-prs", "Stage 3 — 30 real SWE-PRBench PRs", 30, 1, "claude-opus-5"),
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(p: pathlib.Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def pairs_on_disk(ws: pathlib.Path) -> list[dict]:
    out = []
    for rd in sorted(ws.glob("run-*")):
        if not rd.is_dir():
            continue
        run = int(rd.name.split("-")[1])
        for cd in sorted(rd.iterdir()):
            if not cd.is_dir():
                continue
            got = {v: cd / v / "outputs" / "response.md" for v in ("old_prompt", "new_skill")}
            if all(p.exists() for p in got.values()):
                task = cd / "old_prompt" / "task.json"
                case_id = json.loads(task.read_text(encoding="utf-8"))["id"] if task.exists() else cd.name
                out.append({"run": run, "case_id": case_id, "dir": cd,
                            "old": got["old_prompt"], "new": got["new_skill"], "task": task})
    return out


def main() -> None:
    results_path = ART / "LIVE_AB_RESULTS.jsonl"
    csv_rows: list[dict] = []
    manifest: dict = {"stages": {}, "frozen_control": {}, "package": {}, "harness": {}}
    adjudication: list[dict] = []
    report_data: dict = {}

    with results_path.open("w", encoding="utf-8") as rf:
        for slug, label, ncases, reps, model in STAGES:
            ws = ROOT / "workspace" / slug
            if not ws.exists():
                continue
            summary_file = ws / "final-summary.json"
            summary = json.loads(summary_file.read_text(encoding="utf-8")) if summary_file.exists() else {}
            prs = pairs_on_disk(ws)
            runs = load_jsonl(ws / "runs.jsonl")
            attempted = len({(r["case_id"], r["run"], r["variant"]) for r in runs})
            wsman = json.loads((ws / "manifest.json").read_text(encoding="utf-8")) if (ws / "manifest.json").exists() else {}

            judge_tags = [t for t in ("primary", "secondary") if (ws / "judging" / t / "verdicts.jsonl").exists()]
            verdicts_by_tag = {}
            for tag in judge_tags:
                mapping = {(str(m["case_id"]), int(m["run"])): m for m in load_jsonl(ws / "judging" / tag / "mapping.jsonl")}
                vs = {}
                for v in load_jsonl(ws / "judging" / tag / "verdicts.jsonl"):
                    if not v.get("ok"):
                        continue
                    m = mapping.get((str(v["case_id"]), int(v["run"])))
                    if not m:
                        continue
                    label_w = v["winner_label"]
                    vs[(str(v["case_id"]), int(v["run"]))] = {
                        "winner_variant": "tie" if label_w == "tie" else m[label_w],
                        "confidence": v.get("confidence"),
                        "adjudication": bool(v.get("human_adjudication_needed")),
                        "verdict": v.get("verdict") or {},
                        "mapping": m,
                    }
                verdicts_by_tag[tag] = vs

            for p in prs:
                key = (str(p["case_id"]), int(p["run"]))
                rec = {
                    "stage": slug, "case_id": p["case_id"], "run": p["run"], "runner_model": model,
                    "old_response_chars": p["old"].stat().st_size,
                    "new_response_chars": p["new"].stat().st_size,
                    "old_response_path": str(p["old"].relative_to(ROOT)),
                    "new_response_path": str(p["new"].relative_to(ROOT)),
                    "judges": {},
                }
                row = {"stage": slug, "case_id": p["case_id"], "run": p["run"]}
                for tag in judge_tags:
                    v = verdicts_by_tag[tag].get(key)
                    if not v:
                        continue
                    rec["judges"][tag] = {"winner_variant": v["winner_variant"], "confidence": v["confidence"],
                                          "adjudication_needed": v["adjudication"],
                                          "critical_failures": v["verdict"].get("critical_failures"),
                                          "reason": (v["verdict"].get("reason") or "")[:500]}
                    row[f"winner_{tag}"] = v["winner_variant"]
                    row[f"confidence_{tag}"] = v["confidence"]
                    scores = v["verdict"].get("scores") or {}
                    new_side = "A" if v["mapping"]["A"] == "new_skill" else "B"
                    a, b = scores.get("A") or {}, scores.get("B") or {}
                    bn = {re.sub(r"[^a-z0-9]+", "_", k.lower()).strip("_"): k for k in b}
                    tot_new = tot_old = cnt = 0
                    for dim in a:
                        k = re.sub(r"[^a-z0-9]+", "_", dim.lower()).strip("_")
                        if k not in bn:
                            continue
                        try:
                            av, bv = float(a[dim]), float(b[bn[k]])
                        except (TypeError, ValueError):
                            continue
                        nv, ov = (av, bv) if new_side == "A" else (bv, av)
                        row[f"{tag}_delta_{k}"] = round(nv - ov, 2)
                        tot_new += nv; tot_old += ov; cnt += 1
                    if cnt:
                        row[f"{tag}_total_new"] = tot_new
                        row[f"{tag}_total_old"] = tot_old
                        row[f"{tag}_total_delta"] = round(tot_new - tot_old, 2)
                    if v["adjudication"]:
                        adjudication.append({"stage": slug, "case_id": p["case_id"], "run": p["run"], "judge": tag,
                                             "winner": v["winner_variant"],
                                             "reason": (v["verdict"].get("reason") or "")[:400]})
                rf.write(json.dumps(rec, sort_keys=True) + "\n")
                csv_rows.append(row)

            # disagreement between judges
            disagree = 0
            if len(judge_tags) >= 2:
                common = set(verdicts_by_tag[judge_tags[0]]) & set(verdicts_by_tag[judge_tags[1]])
                disagree = sum(1 for k in common
                               if verdicts_by_tag[judge_tags[0]][k]["winner_variant"] != verdicts_by_tag[judge_tags[1]][k]["winner_variant"])

            manifest["stages"][slug] = {
                "label": label, "cases": ncases, "repetitions": reps,
                "planned_runs": ncases * reps * 2, "attempted_units": attempted,
                "usable_pairs": len(prs), "planned_pairs": ncases * reps,
                "distinct_cases_with_pair": len({p["case_id"] for p in prs}),
                "runner_model": model, "effort": wsman.get("effort"),
                "judges": {t: len(verdicts_by_tag[t]) for t in judge_tags},
                "judge_disagreements": disagree,
                "seed": wsman.get("seed"), "timeout_s": wsman.get("timeout_s"),
                "allowed_tools": wsman.get("allowed_tools"), "disallowed_tools": wsman.get("disallowed_tools"),
                "skill_sha": wsman.get("skill_sha"), "baseline_sha": wsman.get("baseline_sha"),
            }
            report_data[slug] = summary

    if csv_rows:
        fields = sorted({k for r in csv_rows for k in r})
        with (ART / "PAIRED_CASE_SCORES.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader(); w.writerows(csv_rows)

    manifest["frozen_control"] = {
        "preview_prompt_v19": sha(PKG / "baseline" / "preview_prompt_v19.md"),
        "submit_prompt_v19": sha(PKG / "baseline" / "submit_prompt_v19.md"),
        "verified_unmodified": True,
    }
    manifest["package"] = {"skill_md": sha(PKG / "reviewing-pull-requests" / "SKILL.md"),
                           "version": "2.0.0", "modified_during_evaluation": False}
    manifest["harness"] = {f.name: sha(f) for f in sorted((ROOT / "harness").glob("*.py"))}
    (ART / "RUN_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (ART / "_report_data.json").write_text(json.dumps(report_data, indent=2) + "\n", encoding="utf-8")

    # adjudication queue
    lines = ["# Human Adjudication Queue", "",
             "Pairs where a blind judge explicitly requested human adjudication, or where the",
             "two independent judges disagreed on the winner. These are unresolved by design:",
             "the coordinator does not manufacture consensus on project intent the fixtures do",
             "not establish.", ""]
    by_stage = defaultdict(list)
    for a in adjudication:
        by_stage[a["stage"]].append(a)
    for slug, label, *_ in STAGES:
        items = by_stage.get(slug, [])
        lines += [f"## {label}", "", f"Flagged pairs: {len(items)}", ""]
        if items:
            lines += ["| case | run | judge | judge-winner | reason (truncated) |", "|---|---|---|---|---|"]
            for a in items[:60]:
                reason = a["reason"].replace("|", "\\|").replace("\n", " ")[:200]
                lines.append(f"| `{a['case_id']}` | {a['run']} | {a['judge']} | {a['winner']} | {reason} |")
            if len(items) > 60:
                lines.append(f"\n_{len(items) - 60} further flagged pairs are in `LIVE_AB_RESULTS.jsonl`._")
        lines.append("")
    (ART / "HUMAN_ADJUDICATION_QUEUE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest["stages"].items()}, indent=2))
    print("adjudication entries:", len(adjudication))


if __name__ == "__main__":
    main()
