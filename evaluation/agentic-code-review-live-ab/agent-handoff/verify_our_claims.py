#!/usr/bin/env python3
"""Recompute every headline number in this package from the raw data.

Run this BEFORE believing anything in the report. It reads only the raw
verdict/manifest files shipped in `raw/` and prints its own numbers next to
the numbers we claimed, marking each MATCH or MISMATCH.

    python3 verify_our_claims.py

Exit code is non-zero if any claim fails to reproduce.

If a number here disagrees with the report, the report is wrong — say so.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent
# `raw/` sits beside this script in the handoff zip, and one level up when the
# package is checked into the repository. Accept either layout.
RAW = next((c for c in (ROOT / "raw", ROOT.parent / "raw") if c.is_dir()), ROOT / "raw")

# What we claimed, hard-coded so it can be contradicted.
CLAIMED = {
    "stage1_primary": {"new": 17, "old": 13, "tie": 39},
    "stage1_secondary": {"new": 21, "old": 18, "tie": 30},
    "stage2_primary": {"new": 15, "old": 2, "tie": 60},
    "stage2_secondary": {"new": 33, "old": 13, "tie": 116},
    "stage1_decision_old": (65, 72),
    "stage1_decision_new": (61, 69),
    "stage2_primary_p": 0.0024,
    "stage2_secondary_p": 0.0045,
}

failures: list[str] = []


def check(label: str, got, expected, tol=None) -> None:
    if tol is not None:
        ok = abs(got - expected) <= tol
    else:
        ok = got == expected
    status = "MATCH   " if ok else "MISMATCH"
    print(f"  [{status}] {label}: recomputed={got}  claimed={expected}")
    if not ok:
        failures.append(label)


def load_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def binom_two_sided(k: int, n: int) -> float:
    """Exact two-sided sign test (McNemar without continuity correction)."""
    if n == 0:
        return 1.0
    pmf = lambda i: math.comb(n, i) * 0.5 ** n
    p_obs = pmf(k)
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= p_obs + 1e-12))


def wilson(s: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = s / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - m), min(1.0, c + m))


def tally(stage: str, tag: str) -> dict:
    jdir = RAW / stage / "judging" / tag
    mapping = {(str(m["case_id"]), int(m["run"])): m for m in load_jsonl(jdir / "mapping.jsonl")}
    wins = defaultdict(int)
    for v in load_jsonl(jdir / "verdicts.jsonl"):
        if not v.get("ok"):
            continue
        m = mapping.get((str(v["case_id"]), int(v["run"])))
        if not m:
            continue
        label = v["winner_label"]
        wins["tie" if label == "tie" else m[label]] += 1
    return {"new": wins["new_skill"], "old": wins["old_prompt"], "tie": wins["tie"]}


def main() -> int:
    print("=" * 78)
    print("INDEPENDENT RECOMPUTATION OF EVERY HEADLINE CLAIM")
    print("=" * 78)

    print("\n1. Blind-judge win/loss/tie tallies (decoded from sealed A/B mappings)")
    for stage, tag, key in [
        ("stage1-golden", "primary", "stage1_primary"),
        ("stage1-golden", "secondary", "stage1_secondary"),
        ("stage2-official", "primary", "stage2_primary"),
        ("stage2-official", "secondary", "stage2_secondary"),
    ]:
        got = tally(stage, tag)
        check(f"{stage}/{tag}", got, CLAIMED[key])

    print("\n2. Paired sign tests on decided (non-tie) pairs")
    for stage, tag, key in [
        ("stage2-official", "primary", "stage2_primary_p"),
        ("stage2-official", "secondary", "stage2_secondary_p"),
    ]:
        t = tally(stage, tag)
        decided = t["new"] + t["old"]
        p = binom_two_sided(t["new"], decided)
        check(f"{stage}/{tag} p-value", round(p, 4), CLAIMED[key], tol=0.0005)
        print(f"            (new={t['new']}, old={t['old']}, decided={decided};"
              f" ties are DISCARDED by a sign test — a design choice you may reject)")

    print("\n3. Ground-truth merge-decision accuracy (Stage 1 fixtures)")
    dec = RAW / "stage1-golden" / "final-decisions.csv"
    if dec.exists():
        import csv
        rows = list(csv.DictReader(dec.open(encoding="utf-8")))
        for variant, key in (("old_prompt", "stage1_decision_old"), ("new_skill", "stage1_decision_new")):
            sub = [r for r in rows if r["variant"] == variant]
            correct = sum(1 for r in sub if r["correct"] == "True")
            check(f"decision accuracy {variant}", (correct, len(sub)), CLAIMED[key])
            p, lo, hi = wilson(correct, len(sub))
            print(f"            Wilson 95% CI: [{lo:.1%}, {hi:.1%}]")
        pair = defaultdict(dict)
        for r in rows:
            pair[(r["case_id"], r["run"])][r["variant"]] = r["correct"] == "True"
        b = sum(1 for d in pair.values() if d.get("new_skill") and not d.get("old_prompt"))
        c = sum(1 for d in pair.values() if d.get("old_prompt") and not d.get("new_skill"))
        print(f"  [INFO    ] McNemar: new-only-correct={b} old-only-correct={c} "
              f"p={binom_two_sided(b, b + c):.4f}")
        print("            NOTE: 'correct' comes from a REGEX that parses the decision out of")
        print("            prose. Spot-check it yourself — a parser bug here would move this number.")
    else:
        print("  [SKIP] final-decisions.csv not shipped")

    print("\n4. Inter-judge agreement (how much you should trust the judges at all)")
    for stage in ("stage1-golden", "stage2-official"):
        w = {}
        for tag in ("primary", "secondary"):
            jdir = RAW / stage / "judging" / tag
            mapping = {(str(m["case_id"]), int(m["run"])): m for m in load_jsonl(jdir / "mapping.jsonl")}
            d = {}
            for v in load_jsonl(jdir / "verdicts.jsonl"):
                if not v.get("ok"):
                    continue
                m = mapping.get((str(v["case_id"]), int(v["run"])))
                if m:
                    d[(str(v["case_id"]), int(v["run"]))] = "tie" if v["winner_label"] == "tie" else m[v["winner_label"]]
            w[tag] = d
        common = set(w["primary"]) & set(w["secondary"])
        if not common:
            continue
        agree = sum(1 for k in common if w["primary"][k] == w["secondary"][k])
        labels = ["new_skill", "old_prompt", "tie"]
        po = agree / len(common)
        m1 = {l: sum(1 for k in common if w["primary"][k] == l) / len(common) for l in labels}
        m2 = {l: sum(1 for k in common if w["secondary"][k] == l) / len(common) for l in labels}
        pe = sum(m1[l] * m2[l] for l in labels)
        kappa = (po - pe) / (1 - pe) if pe < 1 else float("nan")
        print(f"  [INFO    ] {stage}: n={len(common)} raw agreement={po:.1%} Cohen's kappa={kappa:.3f}")
        if kappa < 0.45:
            print("            kappa below 0.45 = fair-to-slight. Treat single-judge results as weak.")

    print("\n5. Usable-pair denominators (what fraction of the plan actually ran)")
    for stage, planned in (("stage1-golden", 75), ("stage2-official", 300), ("stage3-real-prs", 30)):
        runs = load_jsonl(RAW / stage / "runs.jsonl")
        units = {(r["case_id"], r["run"], r["variant"]): r for r in runs}
        att = len(units)
        print(f"  [INFO    ] {stage}: attempted units={att}, planned pairs={planned}")
    print("            Cross-check against RUN_MANIFEST.json 'usable_pairs'. If usable_pairs")
    print("            is far below planned, every p-value here is under-powered.")

    print("\n" + "=" * 78)
    if failures:
        print(f"RESULT: {len(failures)} CLAIM(S) FAILED TO REPRODUCE: {failures}")
        print("The report is wrong on these points. Trust this script, not the report.")
        return 1
    print("RESULT: all hard-coded claims reproduced from raw data.")
    print("This proves ARITHMETIC, not VALIDITY. The judges could still be wrong,")
    print("the rubric could be mis-specified, and the sample could be unrepresentative.")
    print("See CRITIQUE_THIS_EVALUATION.md before accepting any conclusion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
