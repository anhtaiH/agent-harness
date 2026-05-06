---
name: review-orchestrator
description: Run independent limited-context review lanes for a harness task.
---

# Review Orchestrator

Use this after implementation and focused verification for non-trivial work.

- Do not let the implementer self-approve.
- Reviewers receive task artifacts, current code, diff, evidence, and generated profile context.
- Prefer a different tool/model from the writer when available.
- Synthesize review findings before asking the writer to fix them.
- Cite review synthesis in final evidence.
