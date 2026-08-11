# Paired sample — a case where the CONTROL won (primary judge)

These are the cases most useful for challenging our conclusions. Read both
outputs and form your own view before reading the judge's reason.

- case: `golden-stale-flag-still-rollback-root` · repetition 1 · judge `primary`
- fixture ground truth: `{"decision": "request_changes", "priority": "P1", "finding": "The flag is still a live rollback root and is not proven dead.", "specialists": ["history_completeness", "entropy_full"], "proof": "supporting_context_plus_code"}`

## Judge's stated reason (read LAST, after forming your own view)

> Both outputs match ground truth exactly: request_changes at P1 because the deleted OLD_EXPORT flag is still the live rollback root per the runbook, both stay preview-only, and both offer the same two bounded resolution paths (update runbook first, or keep the flag until the rollback window closes). B is tighter and localizes the exact removed line. A wins on the margins: it adds a worthwhile non-blocking P2 asking whether any readers or the old code path remain (a real cleanup-completeness and build risk B only glances at in regression smoke), and it is candid that its evidence is the bundle context rather than repo inspection. B's opening claims an adversarial verifier confirmed the P1 and asserts revert-and-redeploy as a fallback without shown evidence, and its inline comment then says there is 'no safe fallback' — a mild internal inconsistency that slightly dents evidence-calibrated w

---

## Output A — CONTROL (frozen v19)

```
The bundle describes a one-line PR deleting the `OLD_EXPORT` feature flag, with reviewer context stating the production rollback runbook still depends on that flag. That context is the decisive evidence here: the flag isn't actually stale yet, because it's still the documented rollback lever. Since there's no repository to inspect beyond the bundle, the review is based on the diff and the supplied context. Here is the proposed review as a preview — nothing has been posted or submitted.

~~~markdown
## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This PR deletes the `OLD_EXPORT` flag definition from `flags.ts` on the basis that the flag is enabled everywhere. I reviewed the change for rollout and rollback safety, contract impact, and cleanup completeness. There is one P1 blocker: the production rollback runbook still requires `OLD_EXPORT` to restore the prior export path, so deleting the flag removes our only documented way to roll back. The deletion itself is the right cleanup once that dependency is retired; the ask is to sequence it after the runbook no longer needs the flag. There is also one open question about whether any code still reads the flag or implements the old path.

## QA Spec

### Setup

1. Have the production rollback runbook for the export path open alongside this branch.

### Rollback procedure

- When an operator follows the runbook to restore the prior export path:
  - [ ] Every step in the runbook can still be executed as written on this branch
  - [ ] No step references `OLD_EXPORT` or any other symbol this PR deletes

### Regression smoke

Spend a few minutes around:
- Any remaining reads of `OLD_EXPORT` or code implementing the old export path, to confirm the branch still builds and nothing is stranded

### Proposed inline comments

#### 1. `flags.ts:1`

[P1 · Change request]

Can we hold this deletion until the production rollback runbook no longer depends on `OLD_EXPORT`?

The runbook still requires this flag to restore the prior export path. If we delete it now and an incident forces a rollback, the operator following the documented procedure hits a flag that no longer exists, and there is no other documented recovery path. I'd treat this as P1 because it silently removes our rollback mechanism for a production surface, and the failure only becomes visible during an incident, which is the worst time to discover it.

Two ways to resolve it:

1. If the old export path is truly retired, first update the runbook (and confirm the rollback window is closed with whoever owns the export rollout), then land this deletion.
2. If the old path still needs to be restorable, keep the flag until that window closes and track the deletion as a follow-up.

Either way, a pointer to the updated runbook or the owner's confirmation that the rollback window is closed would settle this.

#### 2. `flags.ts:1`

[P2 · Open question]

Does anything still read `OLD_EXPORT`, or implement the old export path it guarded?

The diff removes only the flag definition. If call sites or the old path's code remain, this either fails to build or strands dead code behind a deleted flag; if they were already removed in an earlier PR, that would also mean the runbook's rollback procedure is already broken today, which strengthens the case for fixing the runbook before this lands. A pointer to the PR that removed the old path, or a quick search result showing no remaining readers, would answer this.
~~~

The core issue is sequencing rather than the deletion itself: the flag is a rollback root as long as the runbook depends on it, so the safe order is retire the rollback dependency first, then delete the flag. If you'd like, I can adjust the review or you can ask me to submit it later.
```

---

## Output B — TREATMENT (skill v2.0.0)

```
The review is verified and edited. The adversarial verifier confirmed the P1 (revert-and-redeploy exists as a fallback, so it is not P0, but breaking a named runbook step is a legitimate blocker, not a bounded P2), and the editor pass made only light wording changes. Here is the proposed review as a preview — nothing has been posted or submitted.

## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This PR deletes the `OLD_EXPORT` flag definition now that the flag is enabled everywhere. The change itself is tiny, and cleaning up fully-rolled-out flags is the right instinct. The main thing to check here is rollback safety, and there's one P1 blocker: the production rollback runbook still requires `OLD_EXPORT` to restore the prior export path, so this deletion pulls out a recovery control the runbook still depends on before the runbook and rollback window have moved off it.

## QA Spec

### Setup

1. Open the production rollback runbook section that restores the prior export path.

### Rollback procedure

- When an operator follows the runbook against a build containing this PR:
  - [ ] Every control the runbook references still exists, or the runbook has been updated to a procedure that does not need `OLD_EXPORT`
  - [ ] Restoring the prior export path does not require a code revert and redeploy mid-incident

### Regression smoke

Spend a few minutes around:
- Remaining references to `OLD_EXPORT` or `old-export` in code, config, dashboards, or alerts that would break once the definition is gone

### Proposed inline comments

#### 1. `flags.ts` (removed line: `export const OLD_EXPORT = defineFlag('old-export')`)

[P1 · Change request]

Can we hold this deletion until the rollback runbook no longer depends on `OLD_EXPORT`?

The production rollback runbook still requires `OLD_EXPORT` to restore the prior export path. With the definition deleted, an operator following that runbook during an incident finds a control that no longer exists, and the only way back becomes a code revert and redeploy mid-incident. I'd treat this as P1 because it removes the documented recovery path with no safe fallback.

Two ways to resolve: update the runbook first (retiring the old path) and land this removal afterward, or keep the flag until the rollback window for the old export path has closed.
```
