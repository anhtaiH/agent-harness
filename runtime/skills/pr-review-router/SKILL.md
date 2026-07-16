---
name: pr-review-router
description: Route pull request reviews into the draft-only PR review harness. Use for PR numbers, PR URLs, branch reviews, or review queues. Output stays private draft material; nothing is posted to GitHub without an explicit user ask plus a matching write intent.
---

# PR Review Router

For any PR review request:

1. `pr_review_start` builds the packet: metadata, diff, changed files, risk classification, required lenses.
2. Read the PR body, risk, and context artifacts before asking the author for anything.
3. `pr_review_run` with `lane: auto` for the fast private pass; escalate lanes only when risk or evidence justifies it.
4. `pr_review_synthesize` produces the public-comments draft: fewer, high-confidence comments beat broad speculation.
5. Draft-only is the default and is enforced: posting requires the user's explicit ask AND a GitHub `review-comment` write intent, or the policy gate denies the write.
6. Record outcomes with `pr_review_feedback` so precision is measurable over time.
