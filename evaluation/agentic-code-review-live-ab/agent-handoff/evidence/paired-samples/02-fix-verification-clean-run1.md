# Paired sample — a case where the CONTROL won (primary judge)

These are the cases most useful for challenging our conclusions. Read both
outputs and form your own view before reading the judge's reason.

- case: `golden-fix-verification-clean` · repetition 1 · judge `primary`
- fixture ground truth: `{"decision": "approve", "priority": null, "finding": "Verify the prior blocker first, omit it once fixed, and do not invent a new blocker.", "specialists": ["reliability_concurrency"], "proof": "fix_verification"}`

## Judge's stated reason (read LAST, after forming your own view)

> Both outputs match ground truth: approve, preview-only, treat the prior P1 as fixed without restating it, and invent no new blocker. Both correctly explain the idempotency mechanism (upsert keyed on provider event id) and the ordering tests. The difference is marginal: A surfaces the one genuinely unproven residue — atomicity of the upsert under truly concurrent duplicate deliveries, which sequential retry tests cannot demonstrate — as a well-calibrated, non-blocking P2 open question with a bounded resolution path (point to the unique constraint or note it in the helper). B recognizes the same gap but relegates it to a QA regression-smoke line, which is less actionable for the author and harder for QA to actually execute (forcing near-simultaneous deliveries). B is slightly more concise and scannable; A delivers slightly more author value without compromising the approve decision. The ga

---

## Output A — CONTROL (frozen v19)

```
The bundle describes a fix-verification pass: a prior P1 ("duplicate refund records on retry") that the author has addressed by writing refund webhooks through an idempotent upsert keyed on the provider event id, with new tests covering webhook-first, poll-first, and retry ordering. The fix directly targets the mechanism behind the prior blocker, so the review outcome is an approval, with one non-blocking open question about atomicity under truly concurrent duplicate deliveries — a case sequential retry tests can't demonstrate.

Here is the proposed review as a preview. Nothing has been posted or submitted.

~~~markdown
## Review preview

### Proposed submission type

Approve

### Top-level review body

This follow-up addresses the prior P1 on duplicate refund records by routing the webhook write through `upsertByProviderEvent`, keyed on the provider event id, so redelivered events converge on a single record. The new tests for webhook-first, poll-first, and retry ordering line up with the orderings that produced the duplicates, and this pass focused on the fix itself, the webhook write path, and whether the change introduces new risk. No P0/P1 blockers remain. The one open question below is about concurrent duplicate deliveries and does not block merge.

## QA Spec

Delta from the prior review pass only.

### Setup

1. A refund in a state where the provider emits a refund webhook, with webhook redelivery available (retry or manual replay).

### Refund webhook idempotency

- When the provider delivers the same refund webhook more than once:
  - [ ] exactly one refund record exists for that provider event id
  - [ ] no duplicate refund records or double-applied refund amounts appear
- When the poller records the refund before the webhook arrives, and the reverse:
  - [ ] both paths converge on a single refund record

### Regression smoke

Spend a few minutes around:
- a first-time, non-retried refund webhook still creating its refund record normally

### Proposed inline comments

#### 1. `refunds/webhook.ts` (added `upsertByProviderEvent` line)

[P2 · Open question]

Is `upsertByProviderEvent` atomic under concurrent deliveries, for example backed by a unique constraint on the provider event id?

The retry-ordering tests cover sequential redelivery, but providers can deliver the same event twice nearly simultaneously. If the upsert is implemented as a read-then-insert without a uniqueness guarantee underneath, two concurrent deliveries could each miss the other's read and both insert, reintroducing the duplicate this PR fixes. If there is a unique index or an atomic upsert at the storage layer, this is settled and nothing needs to change; a pointer to that constraint, or a note in the upsert helper, would be enough.
~~~

Summary of the pass: the prior P1 is classified as fixed. The idempotency key choice is sound — retries of the same provider event share `providerEventId`, and the claimed poll-first/webhook-first tests indicate both ingestion paths converge on the same record. The only thing I'd want an answer on (non-blocking) is whether the upsert is atomic at the storage layer, since sequential-retry tests can't prove behavior under simultaneous duplicate delivery. If you'd like, I can prepare this for actual submission on your go-ahead.
```

---

## Output B — TREATMENT (skill v2.0.0)

```
The fix checks out, so this is a clean approval. This pass is a fix verification: the prior review's only blocker was "P1: duplicate refund records on retry," and the diff routes the webhook write through `refunds.upsertByProviderEvent(providerEventId, refund)`, which makes the provider event id the idempotency key. A retried delivery of the same event now lands on the existing record instead of inserting a second one, and the stated new tests cover the three orderings that produced duplicates (webhook-first, poll-first, retry). No new risk surface was added, so nothing warrants a fresh inline comment, and per the re-review rules the fixed P1 is not restated as a comment.

Nothing has been posted. Here is the proposed review, in preview form:

## Review preview

### Proposed submission type

Approve

### Top-level review body

This resolves the prior P1 on duplicate refund records. Keying the webhook write on the provider event id through `upsertByProviderEvent` makes a retried delivery update the existing refund instead of inserting a new one, and the new tests cover the webhook-first, poll-first, and retry orderings where the duplicates appeared. No remaining blockers, so this is good to merge.

## QA Spec (follow-up delta)

### Setup

1. Use an environment where a refund webhook can be replayed with the same provider event id, or run the new webhook ordering tests.

### Refund deduplication

- When the same refund webhook is delivered twice:
  - [ ] One refund record exists for one provider event.
  - [ ] The second delivery updates the existing record and does not create a new one.
- When polling records the refund before the webhook arrives:
  - [ ] The later webhook leaves a single record with the final refund state.

### Regression smoke

Spend a few minutes around:
- two deliveries of the same event arriving near-simultaneously, since concurrent writes are the one duplicate path a sequential retry test does not exercise

*(No inline comments proposed; no private follow-up artifacts.)*

If you'd like, I can submit this as an approval on the PR.
```
