#!/usr/bin/env python3
"""Convert golden PR fixtures into run-ready eval cases.

Runner-visible input bundles NEVER contain the `expected` ground truth.
Ground truth stays in the eval case metadata, which the runner harness
withholds from child agents (task.json is written only after the run).
"""
from __future__ import annotations

import json
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "handoff" / "agentic-code-review-live-eval-handoff-v1" / "agentic-code-review-skills-v2.0.0"
FIXTURES = PKG / "evaluation" / "fixtures" / "golden_prs"
OUT = Path(__file__).resolve().parent / "golden"


def bundle_markdown(fx: dict) -> str:
    parts = [
        f"# Pull request: {fx['title']}",
        "",
        "## Description",
        fx["description"],
        "",
        "## Diff",
        "```diff",
        fx["diff"].rstrip("\n"),
        "```",
        "",
        "## Repository / reviewer context",
        fx["context"],
    ]
    if fx.get("existing_review"):
        parts += ["", "## Existing review state", json.dumps(fx["existing_review"], indent=2)]
    parts.append("")
    return "\n".join(parts)


def main() -> None:
    inputs_dir = OUT / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    for path in sorted(FIXTURES.glob("*.json")):
        if path.name == "index.json":
            continue
        fx = json.loads(path.read_text(encoding="utf-8"))
        md_name = f"{fx['id']}.md"
        (inputs_dir / md_name).write_text(bundle_markdown(fx), encoding="utf-8")
        cases.append(
            {
                "id": f"golden-{fx['id']}",
                "prompt": (
                    "Review the pull request described in the attached PR bundle file and "
                    "show me the proposed review as a preview. Do not post or submit anything."
                ),
                "files": [f"inputs/{md_name}"],
                "expected_output": (
                    f"decision={fx['expected'].get('decision')} "
                    f"priority={fx['expected'].get('priority')} — {fx['expected'].get('finding')}"
                ),
                "assertions": [],
                "metadata": {"source_fixture": path.name, "expected": fx["expected"]},
            }
        )
    out = {"skill_name": "reviewing-pull-requests", "evals": cases}
    (OUT / "golden_evals.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} golden cases -> {OUT / 'golden_evals.json'}")


if __name__ == "__main__":
    main()
