# Treatment output preamble — narration-leak example 4

- stage: `stage2-official`
- case: `eval-golden-01-authz-bypass`
- repetition: `run-02`
- narration terms matched in preamble: **4**
- source: `workspace/stage2-official/run-02/eval-golden-01-authz-bypass/new_skill/outputs/response.md`

## Verbatim preamble (text before the review body)

```
All waves are complete and the final quality gate passes: the single blocker was found independently by three of the four first-wave reviewers, survived an adversarial disconfirmation pass from a different model family, and the structural counter-design (permission grant instead of hardcoded roles) survived its own falsification check. The editor's wording edits are adopted, except I restored the one-sentence deny-test proof request in the inline comment, since a P1 may carry a fix plus a proof request and a manual QA step is not a regression test. No entropy handoff was warranted, so there are no private follow-up artifacts.

**Outcome:** Request Changes, on one confirmed P1. The PR's stated goal (editors may export audit logs) is legitimate, but the implementation replaces the `audit.export` permission check with a hardcoded role list, which detaches the endpoint from the permission model: editors who were never granted `audit.export` gain direct-API access, grant revocations silently stop working, anyone holding the permission outside those roles would lose access, and the UI (still keyed on the permission) never shows the control to the very editors the PR is meant to help. The fix is to keep `requirePermission` and grant `audit.export` to the editor role.

---
```
