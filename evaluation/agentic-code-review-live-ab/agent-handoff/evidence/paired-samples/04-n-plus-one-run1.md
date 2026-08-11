# Paired sample — a case where the CONTROL won (primary judge)

These are the cases most useful for challenging our conclusions. Read both
outputs and form your own view before reading the judge's reason.

- case: `golden-n-plus-one` · repetition 1 · judge `primary`
- fixture ground truth: `{"decision": "request_changes", "priority": "P1", "finding": "The loop adds one database query per result on a known hot path.", "specialists": ["performance"], "proof": "code_path_proof"}`

## Judge's stated reason (read LAST, after forming your own view)

> Both outputs correctly identify the N+1 owner lookup as a P1 request-changes blocker with the right mechanism (per-result User.find, up to 500 sequential queries on a measured hot endpoint), offer near-identical batched-load fixes, respect preview-only, and correctly handle the RecordNotFound secondary concern without inflating it. A wins narrowly: it quotes the exact added line, keeps the preview free of process narration, and every finding and QA item is grounded in the diff. B adds a QA check about serialized owner-field exposure that rests on an assumption the diff does not establish, leads with meta-narration about internal review passes and 'adversarial verification' (unverifiable process claims that dilute reader trust and readability), and concedes its line anchors were not validated. B's caveats section is a genuine honesty strength, but the net difference is small, so confidenc

---

## Output A — CONTROL (frozen v19)

```
The bundle is a one-line diff, so the whole evidence base is in that file. The change adds a per-result `User.find` on a search path that returns up to 500 results and is a measured hot endpoint — a classic N+1 query, plus a secondary failure mode (`User.find` raises `ActiveRecord::RecordNotFound` on a dangling `owner_id`, which would fail the whole search request). Here is the proposed review preview; nothing has been posted.

~~~markdown
## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This PR loads the owner for each search result so owners can be shown in results. I reviewed the query behavior on the results path, failure handling for missing owners, and test coverage.

There is one P1 blocker: the per-result `User.find` issues one query per result on an endpoint that is a measured hot path and can return up to 500 results, so a single search can trigger up to 500 sequential owner queries. Batch-loading the owners resolves it. There is also a P2 open question about what should happen when a result's `owner_id` no longer matches a user, since `User.find` raises and would fail the whole request today.

## QA Spec

### Setup

1. A dataset where a search returns a large number of results (ideally the 500-result cap) with owners spread across many distinct users.
2. At least one result whose `owner_id` points at a deleted or missing user.

### Search results with owners

- When a user runs a search that returns many results:
  - [ ] Each result shows its owner.
  - [ ] The owner lookup runs as a constant number of queries (not one query per result), and response time stays in line with the endpoint's current baseline.

- When a result's owner record no longer exists:
  - [ ] The search still returns successfully with the agreed behavior for that result (for example no owner shown).
  - [ ] The request does not fail with a 500.

### Regression smoke

Spend a few minutes around:
- Searches returning zero and one result, to confirm the owner-loading step doesn't change those paths.

### Proposed inline comments

#### 1. `search/results.rb` (added line: `results.each { |r| r.owner = User.find(r.owner_id) }`)

[P1 · Change request]

Can we batch-load the owners instead of calling `User.find` once per result?

As written, a single search issues one owner query per result, and this endpoint is a measured hot path that returns up to 500 results, so one request can run up to 500 sequential queries. I'd treat this as P1 because it adds a linear query fanout to a known hot endpoint at its normal working size, not just in an edge case.

One shape that keeps the same assignment structure:

```ruby
owners = User.where(id: results.map(&:owner_id).uniq).index_by(&:id)
results.each { |r| r.owner = owners[r.owner_id] }
```

(Sketch only, adjust to the local relation types. If results come from an ActiveRecord relation with an `owner` association, `includes(:owner)`/`preload(:owner)` at the query site is the more idiomatic fix.)

It would also help to add a test on the multi-result search path that asserts the owner lookup uses a constant number of queries, so the fanout can't quietly come back.

#### 2. `search/results.rb` (same added line)

[P2 · Open question]

What should happen when a result's `owner_id` no longer matches an existing user?

`User.find` raises `ActiveRecord::RecordNotFound` for a missing id, so one dangling `owner_id` fails the entire search request rather than just that result. The batch-load shape above happens to degrade to a `nil` owner instead of raising, but that's a behavior choice worth making explicitly: should the result render without an owner, be filtered out, or is a dangling `owner_id` impossible by construction here? A short test pinning the chosen behavior would settle it.
~~~

The P1 is the only blocker; once owner loading is batched (and the missing-owner behavior is decided), this looks ready to approve. Nothing was posted or submitted — this is preview only.
```

---

## Output B — TREATMENT (skill v2.0.0)

```
Review complete — nothing was posted or submitted; below is the preview. All four independent review passes converged on the same blocker, it survived adversarial verification, and a fresh editor pass tightened the wording. One note on the editor's cuts: it removed a QA check about response field exposure as unsupported, but since the change newly attaches a full `User` record to each serialized result, I restored it as a one-line validation item with its rationale inline.

The verdict: **Request Changes**. The added line is a textbook N+1 — one `User.find` per result, up to 500 sequential queries per request on a path the PR context itself describes as a measured hot endpoint. A secondary reliability concern (`find` raising `RecordNotFound` and failing the whole response over one missing owner) rests on unproven data-staleness assumptions, so it was folded into the main comment as a fix-semantics decision rather than standing as its own blocker. A test-coverage suggestion rides along as a non-blocking P2.

---

## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This adds owner loading for each search result so results can show project owners.

One blocker: the owner lookup runs one `User.find` per result, so a full result page issues up to 500 sequential queries on what you've flagged as a hot endpoint. Batching it into a single lookup is a small change, and it also avoids failing the whole response when one owner row is missing. Non-blocking: a query-count test would keep this path from regressing later.

## QA Spec

### Setup

1. Seed a search dataset large enough to return a full result page (ideally near the 500-result cap) across many distinct owners.
2. If the domain allows it, include one result whose owner no longer exists or whose owner_id is empty.

### Search results with owners

- When a user runs a search that returns a large result page:
  - [ ] each result shows its project owner
  - [ ] the request issues a constant number of owner-lookup queries, not one per result, and endpoint latency stays near its pre-change baseline
  - [ ] the serialized response includes only the owner fields the results view needs, since a full `User` record is newly attached to each result
- When a result's owner cannot be resolved:
  - [ ] the other results still render and the request does not fail

### Regression smoke

Spend a few minutes around:
- searches that return zero results and a single result

### Proposed inline comments

#### 1. `search/results.rb` (the added line in the only hunk)

[P1 · Change request]

Can we load the owners in one batched query instead of one `User.find` per result?

A request that returns the full 500 results issues up to 500 single-row SELECTs on top of the search query itself. P1 because this is a measured hot endpoint and both the added latency and the connection-pool pressure grow linearly with result count.

Sketch:

```ruby
owners = User.where(id: results.map(&:owner_id).compact.uniq).index_by(&:id)
results.each { |r| r.owner = owners[r.owner_id] }
```

If `results` is an ActiveRecord relation with a `belongs_to :owner`, `preload(:owner)` at the query source does the same thing in one line.

One behavior difference to decide on: `find` raises `ActiveRecord::RecordNotFound` when an owner row is missing or `owner_id` is nil, so a single bad row fails the whole response. The batched version leaves that result's owner nil instead, so please make the nil case explicit, either by rendering a missing owner safely or by logging the unresolved ids.

#### 2. `search/results.rb` (the added line in the only hunk)

[P2 · Suggestion]

Worth adding a query-count test so this path cannot quietly regress to per-row loading later.

A request spec with a handful of results across at least two distinct owners, asserting that owner loading adds a constant number of queries (`assert_queries_count` on Rails 7.1+, or a `sql.active_record` notification counter), would lock in the batched behavior. The same fixture can cover a result with a missing owner, since that case's expected behavior changes with the fix above.

---

Caveats worth knowing: this review was produced from the PR bundle alone (no repository checkout), so the findings rest on the diff plus standard ActiveRecord semantics — in particular, whether `results` is an ActiveRecord relation or a search-index object determines which of the two fix options applies, and the inline comments say so. Line-level anchors couldn't be validated against a real diff since the bundle's hunk carries no line numbers. If you'd like, I can submit this review as-is — just say the word.
```
