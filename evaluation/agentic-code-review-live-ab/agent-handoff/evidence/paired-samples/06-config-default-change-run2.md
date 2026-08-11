# Paired sample — a case where the CONTROL won (primary judge)

These are the cases most useful for challenging our conclusions. Read both
outputs and form your own view before reading the judge's reason.

- case: `golden-config-default-change` · repetition 2 · judge `primary`
- fixture ground truth: `{"decision": "request_changes", "priority": "P1", "finding": "The default change sends all users onto a rollout path without deployment/rollback proof.", "specialists": ["release_supply_chain", "history_completeness"], "proof": "gap_proof"}`

## Judge's stated reason (read LAST, after forming your own view)

> Ground truth specifies decision=request_changes with a P1 finding that the default flip sends all users onto a rollout path without deployment/rollback proof. Output A matches exactly: Request Changes, P1 inline comment on the missing rollout/rollback plan, correct mechanism (default flip onto separate worker/dashboard infrastructure), clear bounded resolution options, honest caveats about the bundle-only workspace, and preview-only compliance. Output B identifies the same underlying risk and localizes it correctly, but classifies it as two P2 open questions and proposes Comment, failing the fixture's expected decision and priority — a rubric-level critical failure since the other output finds the P1 correctly. Both outputs have strong QA specs, readability, and no fabricated verification; B's rollback QA section is a nice touch but cannot offset the wrong merge action.

---

## Output A — CONTROL (frozen v19)

```
I've reviewed the PR bundle. The workspace contains only the bundle file itself (no repository to inspect), so the review is based on the one-line diff and the stated reviewer context, with claims qualified accordingly.

**TLDR:** This one-line change flips the `asyncExport` default from `false` to `true`, moving every export that doesn't override the flag onto the separate worker-and-dashboard path. The change itself is trivial, but the bundle explicitly notes there is no rollout or rollback note, and nothing in the PR confirms the async infrastructure is ready to take default traffic or that existing callers tolerate the contract change. I'm proposing **Request Changes** with one P1 (missing rollout/rollback plan for a default flip onto separate infrastructure) and one P2 open question (whether callers depend on the synchronous completion contract). Nothing has been posted; this is a preview only.

~~~markdown
## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This PR flips the `asyncExport` default in `config/export.ts` from `false` to `true`, which moves every export that doesn't explicitly override the flag onto the asynchronous path backed by the separate worker and dashboard. I reviewed the config change itself, the rollout implications of changing a default, and the caller-facing contract implications; the flag flip is mechanically fine, but there is one blocker: the PR changes the default execution path for all exports with no rollout or rollback note, and nothing here confirms the worker path is ready to take that traffic in every environment. There is also an open question about whether any existing callers depend on synchronous completion. Once the rollout/rollback plan is in the PR and the caller question is settled, this looks safe to land.

## QA Spec

### Setup

1. An environment where the export worker and its dashboard are running, with at least one exportable item available.

### Default export path

- When a user triggers an export without any explicit `asyncExport` override:
  - [ ] The export runs through the asynchronous worker path and shows up on the dashboard
  - [ ] The completed export produces the same artifact as the previous synchronous default
  - [ ] The export is not silently dropped or left permanently pending

### Explicit sync override

- When a caller explicitly sets `asyncExport: false`:
  - [ ] The synchronous path still works as before

### Worker unavailable

- When the export worker is stopped and a user triggers a default export:
  - [ ] The failure is visible to the user or operator (error or dashboard state), not a silent loss of the export

### Regression smoke

Spend a few minutes around:
- Any flow that consumes an export result immediately after requesting it, since the default no longer completes synchronously

### Proposed inline comments

#### 1. `config/export.ts` (the changed `asyncExport` line)

[P1 · Change request]

Can we add a rollout and rollback note before flipping this default?

This one-line change moves every export that doesn't override the flag onto the async path, which runs on a separate worker and dashboard. The PR has no note confirming the worker is provisioned and monitored wherever this default applies, no signal to watch after the flip, and no rollback guidance. I'd treat this as P1 because the flip puts the entire default export flow onto infrastructure this PR doesn't show is ready, and if the worker path degrades there's currently no written path back.

Two ways to resolve it:

1. Add a short rollout note to the PR: which environments this applies to, confirmation the worker is deployed and has capacity there, the dashboard or metric to watch after the change, and the revert step (flip the flag back) with any caveats for exports in flight.
2. If readiness varies by environment, stage the default instead of flipping it globally, and note the sequencing.

Either one unblocks this; the change itself doesn't need to grow.

#### 2. `config/export.ts` (the changed `asyncExport` line)

[P2 · Open question]

Do any existing callers depend on the export completing synchronously?

Callers that never set `asyncExport` are the ones this PR changes: if any of them read the export result inline, block on completion, or surface errors from the synchronous return path, their behavior shifts even though their code didn't change. If all call sites already handle the async job shape (or explicitly pass the flag), this is fine as is. A quick pointer to the call sites that rely on the default, or a test that exercises an export through the new default end to end, would settle it.
~~~

A note on process: the frozen review policy calls for repository inspection, multi-stream review, and tool-backed verification, but this bundle contains only the PR description and diff with no repository attached. Both findings therefore rest on what the bundle itself states (the async path's dependence on a separate worker, and the absence of a rollout note), and the caller-contract concern is deliberately framed as an open question rather than a blocker since I couldn't inspect call sites.
```

---

## Output B — TREATMENT (skill v2.0.0)

```
I reviewed the PR bundle following the skill's workflow in **preview mode** — nothing was posted or submitted. Here's the outcome and the exact proposed review payload.

The change itself is a one-line, mechanically correct default flip (`asyncExport: false → true` in `config/export.ts`). The review risk isn't in the diff — it's in what the diff switches on: the async path runs through a separate worker and dashboard, and the flip changes behavior for every deployment that relies on the default, yet the PR carries no rollout or rollback note. I found no confirmed blocker (the async path may well be fully deployed and battle-tested behind the flag — the bundle doesn't say either way), so this doesn't meet the bar for Request Changes. But two bounded readiness questions prevent an honest approval, which per the skill's merge-decision model makes the proposed submission type **Comment**.

---

## Review preview

### Proposed submission type

Comment

### Top-level review body

This PR flips the `asyncExport` default from `false` to `true`, which switches every deployment that doesn't set the flag explicitly onto the async export path (separate worker plus dashboard). The code change itself is trivial and correct as written; the review surface is rollout and compatibility, not the diff. I don't see a confirmed blocker, but the PR includes no rollout or rollback note, so I've left two open questions about environment readiness and default-consumer behavior that I'd like answered before this is approved. If the async path has already been running broadly behind the flag and the infrastructure is live everywhere this default reaches, a short note or a link to that evidence resolves both.

## QA Spec

### Setup

1. Deploy a build of this branch to an environment that does **not** set `asyncExport` explicitly, so the new default applies.
2. Confirm the export worker and its dashboard are running in that environment.

### Export with the new default

- When a user triggers an export in the default-configured environment:
  - [ ] The export is handed to the async path (worker picks it up) rather than running synchronously.
  - [ ] The user can find the export's status and result through the dashboard.
  - [ ] The export does not silently hang with no visible status anywhere.

### Worker unavailable

- When the export worker is stopped and a user triggers an export:
  - [ ] The user or the dashboard shows a clear pending or failed state.
  - [ ] The request does not appear to succeed while producing nothing.

### Rollback

- When `asyncExport` is set back to `false` after async exports have run:
  - [ ] New exports complete synchronously as before.
  - [ ] Async jobs that were in flight at the time of the flip are not stranded invisibly.

### Regression smoke

Spend a few minutes around:
- An environment that explicitly sets `asyncExport: false`, to confirm it keeps the synchronous behavior.

### Proposed inline comments

#### 1. `config/export.ts` (the changed `asyncExport: true` line)

[P2 · Open question]

What is the rollout plan for this default flip, and how do we roll it back if the async path misbehaves?

Flipping the default switches every deployment that doesn't set `asyncExport` explicitly onto the async path, which depends on the separate export worker and dashboard being live in each of those environments. The PR has no rollout or rollback note, so I can't tell whether the worker is already deployed everywhere this default reaches, or what the revert story is (presumably setting the flag back to `false`, but it's worth stating what happens to jobs already in flight).

A short note in the PR description covering environment readiness, ordering relative to worker deployment, and the revert step would settle this, or a link to the rollout ticket if one exists.

#### 2. `config/export.ts` (the changed `asyncExport: true` line)

[P2 · Open question]

Are the surfaces that rely on the default prepared for export becoming asynchronous?

Users and callers that previously got a synchronous export by default will now get the async flow, where the result is reached through the dashboard instead of returned immediately. If any caller, UI flow, or integration assumes the synchronous behavior when the flag is unset, this flip changes its observable behavior without any accompanying code change in this PR.

A pointer to where the default consumers were already exercised against the async path, or to tests covering the async-by-default case, would resolve this.

---

**Not posted.** This is a preview only; no review, comments, or PR edits were submitted. If you'd like, I can adjust the wording or priorities, or you can ask me to submit it.
```
