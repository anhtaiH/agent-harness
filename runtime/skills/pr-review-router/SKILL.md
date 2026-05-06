---
name: pr-review-router
description: Route pull request reviews into the local draft-only PR review harness.
---

# PR Review Router

Use this for PR numbers, PR URLs, local branch reviews, and review queues.

1. Call `pr_review_start`.
2. Read PR body, changed files, risk, and context artifacts before asking for author proof.
3. Prefer `pr_review_run` with `lane: auto` for the first fast private pass.
4. Synthesize through `pr_review_synthesize`.
5. Keep output draft-only unless the user explicitly asks to post and a GitHub `review-comment` write intent exists.
6. Favor fewer high-confidence comments over broad speculative coverage.
