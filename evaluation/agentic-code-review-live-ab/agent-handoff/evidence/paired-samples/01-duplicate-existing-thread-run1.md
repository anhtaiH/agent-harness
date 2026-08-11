# Paired sample — a case where the CONTROL won (primary judge)

These are the cases most useful for challenging our conclusions. Read both
outputs and form your own view before reading the judge's reason.

- case: `golden-duplicate-existing-thread` · repetition 1 · judge `primary`
- fixture ground truth: `{"decision": "approve", "priority": null, "finding": "Do not duplicate the existing thread unless adding a materially better proof or fix.", "specialists": ["public_contract"], "proof": "duplicate_suppression"}`

## Judge's stated reason (read LAST, after forming your own view)

> Both outputs correctly execute the fixture's core behavior: they recognize the frontend/backend .mdc mismatch is already owned by an unresolved thread and suppress duplicating it, and both honor preview-only mode. Both deviate identically from the ground-truth 'approve' decision by proposing Comment, with arguable rationale, so that dimension is a wash. A edges ahead on non-blocking value and repairability: its single P2 inline suggestion (shared classification map or contract test to prevent future drift) is a genuinely distinct, non-duplicative ask permitted by the ground truth's 'unless adding materially better proof or fix' clause, whereas B over-filters to zero comments. B also opens with internal process narration ('four first-wave missions', 'coordinator pass') that leaks orchestration jargon into user-facing text. Differences are modest, so confidence is low.

---

## Output A — CONTROL (frozen v19)

```
The workspace contains only the PR bundle, so the review is based on the diff and review state it describes.

**What I found:** The PR adds one backend classifier case mapping `.mdc` to `skill-companion`. The material concern — that the frontend instruction tree classifier also needs the `.mdc` case, or the two classifiers disagree — is already raised by an unresolved human review thread on this PR. Posting it again as a new inline comment would duplicate that thread, so the preview instead acknowledges it in the review body and defers to the existing thread for resolution. The only new comment I'm proposing is a non-blocking suggestion aimed at preventing the same frontend/backend drift on the next extension, which is a distinct ask the existing thread doesn't cover. Since the outstanding blocker-shaped work is already owned by an open thread rather than a new finding of mine, the honest submission type is Comment rather than a fresh Request Changes.

Here is the proposed review preview. Nothing has been posted or submitted.

~~~markdown
## Review preview

### Proposed submission type

Comment

### Top-level review body

This PR adds a backend classification case so `.mdc` files are classified as `skill-companion`. I reviewed the classifier change itself and its frontend/backend parity implications. I'm not raising any new blockers, but the existing unresolved review thread asking to update the frontend instruction tree classifier for `.mdc` still covers the main outstanding work: with only the backend side changed, the two classifiers disagree on `.mdc` files until the frontend follows. Rather than duplicating that thread, I'd close it out either by updating the frontend classifier in this PR or by linking where that change lands, and I've left one non-blocking suggestion about keeping the two classifiers from drifting again.

## QA Spec

### Setup

1. A project or workspace containing at least one `.mdc` file, plus a few neighboring file types the classifier already handles.

### File classification

- When the backend classifier processes a `.mdc` file:
  - [ ] it is classified as `skill-companion`
  - [ ] files with other extensions keep their previous classification
- When the same `.mdc` file is viewed through the frontend instruction tree:
  - [ ] its presentation is consistent with the backend `skill-companion` classification once the frontend change from the existing review thread lands
  - [ ] the file does not silently fall into a generic or unknown bucket on one side only

### Regression smoke

Spend a few minutes around:
- classification of adjacent extensions (for example `.md`) to confirm the new case didn't change any existing fallthrough behavior

### Proposed inline comments

#### 1. `backend/classify.ts` (added `.mdc` case)

[P2 · Suggestion]

Can we add a guardrail so the frontend and backend classifiers can't drift on file types again?

The open review thread already covers adding the `.mdc` case to the frontend instruction tree classifier, so this isn't about that. It's about the next extension: right now the same classification rule has to be updated in two places by hand, and this PR shows how easy it is for one side to move without the other. A shared classification map that both sides consume, or a small contract test asserting the two classifiers agree on the supported extension set, would turn this from a review-thread reminder into a mechanical check.

This doesn't need to hold the PR. It could go here if it's cheap, or in a small follow-up.
~~~

To recap: no new blockers from this pass; the frontend `.mdc` update remains tracked in the existing unresolved thread, and the one proposed inline comment is a non-blocking drift-prevention suggestion. If you'd like, I can adjust the submission type or wording before any eventual submission.
```

---

## Output B — TREATMENT (skill v2.0.0)

```
I've completed the review analysis. The change is a one-line backend addition, so this ran as a compact-effort pass: the four first-wave missions (intent/behavior, contracts/safety, proof/operations, structure/history) were done as isolated sequential passes over the bundle, and the coordinator pass compared candidates against the existing review state before drafting.

**TLDR:** The PR only does half of what its title claims. It adds the `.mdc` → `skill-companion` case to the backend classifier, but the frontend instruction tree classifier is untouched — and an unresolved human review thread already asks for exactly that frontend update. Since that gap is already raised in an open thread, the proposed review does **not** duplicate it as a new inline comment; instead the review body points back to the existing thread, and the proposed decision is **Comment** (the backend line itself has no confirmed blocker, but approving would falsely signal the alignment is complete). Nothing has been posted — this is a preview only.

---

## Review preview

### Proposed submission type

Comment

### Top-level review body

This adds a backend classification case mapping `.mdc` files to `skill-companion` in `backend/classify.ts`. The backend change itself looks fine and I found no new blockers in it.

However, the PR title says it aligns the frontend and backend classifiers, and the diff only changes the backend. The existing unresolved review thread ("Update frontend instruction tree classifier for .mdc") still applies, so I won't repeat it as a new comment here. Until that thread is settled, backend and frontend will classify `.mdc` files differently, which is the inconsistency this PR set out to remove. Could you either add the frontend `.mdc` case in this PR and resolve that thread, or note in the thread where the frontend half is tracked? I'm leaving this as a comment rather than an approval only because that open thread covers work the PR description claims is done.

## QA Spec

### Setup

1. Have a workspace containing at least one `.mdc` file alongside a few files of other already-supported types.

### Classification alignment

- When the backend classifies a `.mdc` file:
  - [ ] it is classified as `skill-companion`
  - [ ] files of other types keep their previous classification
- When the same `.mdc` file is shown in the frontend instruction tree (after the frontend classifier is updated):
  - [ ] it carries the same `skill-companion` classification as the backend
  - [ ] it does not fall through to a default or unknown category while the backend reports `skill-companion`

### Regression smoke

Spend a minute confirming other extensions handled by the same classifier switch still classify as before, since the new case sits in that shared decision point.

---

No inline comments are proposed: the only material finding (the missing frontend classifier update) is already raised in the existing unresolved thread, and filing it again would duplicate that thread. No private follow-up artifacts were created, and per preview mode, nothing was posted or submitted.
```
