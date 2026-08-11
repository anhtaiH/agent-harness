# Treatment output preamble — CLEAN counterexample 2

The same skill, same conditions, no orchestration narration *by our regex*.
Any fix must keep outputs like this unchanged.

**Caveat we found ourselves:** this one is not perfectly clean. It says "run in
preview mode per the skill" and "the skill's convergence rule says this
approves" — self-reference to the governing policy that our pattern has no term
for. Evidence that our 55% leak rate is a floor, not a ceiling. See
`REPRODUCE_FINDING_4.md` weakness #5.

- stage: `stage1-golden`
- case: `eval-golden-fix-verification-clean`
- repetition: `run-02`
- source: `workspace/stage1-golden/run-02/eval-golden-fix-verification-clean/new_skill/outputs/response.md`

## Verbatim preamble

```
The fix checks out. This was a fix-verification pass against the prior blocker ("P1: duplicate refund records on retry"), run in preview mode per the skill — nothing was posted. The one-line change keys refund persistence on `provider_event_id` via `refunds.upsertByProviderEvent`, which makes webhook handling idempotent on redelivery, and the branch's tests cover the webhook-first, poll-first, and retry orderings that the original P1 was about. No new P0/P1 surfaced in the adjacent sweep, so the skill's convergence rule says this approves. Here is the exact proposed review:

---
```
