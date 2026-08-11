# Treatment output preamble — narration-leak example 8

- stage: `stage1-golden`
- case: `eval-golden-wrong-test-harness`
- repetition: `run-01`
- narration terms matched in preamble: **1**
- source: `workspace/stage1-golden/run-01/eval-golden-wrong-test-harness/new_skill/outputs/response.md`

## Verbatim preamble (text before the review body)

```
Review complete. Here's the outcome: the PR's one-line loop, meant to mark every CSSOM declaration `!important`, has a confirmed P1 defect — in a real browser it deletes any shorthand declaration written with `var()` instead of strengthening it. The repository's unit harness doesn't model CSSOM pending-substitution values, so green unit tests are not valid evidence here; the claim was instead confirmed by an independent adversarial verification pass against the CSSOM and CSS Variables specs (iteration yields longhands, `getPropertyValue` on a pending-substitution longhand returns the empty string, and `setProperty` with an empty value is specified to act as `removeProperty`, with live-collection mutation mid-iteration as a secondary hazard). No upstream guard or safer explanation was found. The proposed action is Request Changes. Nothing has been posted — this is a preview only.
```
