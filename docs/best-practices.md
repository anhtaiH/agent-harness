# Best Practices

## Start Small

Use bounded tasks with a clear finish line. A good prompt names the goal, risk tolerance, expected verification, and whether yolo mode is allowed.

Good:

```text
Use the harness to fix the flaky test in this package. Work in a harness worktree, run the affected test, and finish with evidence.
```

## Prefer Measurable Loops

Treat agent work as small experiments:

1. State the hypothesis or task goal.
2. Run the smallest useful check.
3. Record the result.
4. Adjust the next step.
5. Promote only source-backed lessons.

This keeps long-running autonomy grounded in observable progress instead of narrative confidence.

## Use Review Lanes For Risk

For green tasks, code inspection plus targeted tests may be enough. For yellow/red tasks, ask for independent review before completion:

```text
Before finishing, run the harness review loop with at least one independent reviewer lane and synthesize the findings.
```

## Keep PR Review Precise

PR review should reduce review load. Ask for a fast pass first, then escalate only when risk or evidence justifies it:

```text
Review this PR stack quickly with the harness. Use lane:auto, keep the draft under five comments, and discard low-confidence findings.
```

## Let Knowledge Compound

Use local memory for source-backed candidates only. Do not store secrets, raw logs with tokens, or uncited claims. Promote stable project rules into project-owned docs after human review.
