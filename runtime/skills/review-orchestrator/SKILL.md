---
name: review-orchestrator
description: Run independent, limited-context review lanes for a harness task after implementation. Use before finishing yellow/red-risk work, when the user asks for an independent review, or when the diff touches auth, data, payments, schema, or infra. The implementer never self-approves.
---

# Review Orchestrator

After implementation and focused verification:

1. Pick lanes by risk: scope + correctness always; tests lane when behavior changed; security lane (harness-security) for auth/permissions/payments/schema/infra or red/critical packets.
2. Prefer an independent context per lane: Claude Code subagents (harness-reviewer, harness-verifier, harness-security) or cross-tool peer lanes via `agent_run` (codex/claude/cursor) — ideally a different tool or model than the writer.
3. Reviewers get task artifacts, the diff, current code, and evidence — not the writer's chat history.
4. Collect verdicts, then `review_synthesize`; the writer fixes findings and reruns affected lanes.
5. Cite the review synthesis in final evidence; unresolved critical findings block finish.
