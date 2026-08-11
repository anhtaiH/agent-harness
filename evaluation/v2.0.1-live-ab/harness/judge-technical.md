You are grading two candidate code-review outputs written for the same pull request.
They are labelled A and B. You do not know which system produced either one, and you must
not speculate about their origin or mention evaluation machinery.

Read these files in your working directory:

- `case.json` — the sanitized pull-request input that both reviews were given
- `ground-truth.json` — the reference answer, visible only to you
- `output-a.md` and `output-b.md` — the two candidate reviews

Score each output **independently** against the ground truth, then state a preference.

Per-output fields:

- `decision_seen`: the review's proposed submission type — one of `approve`,
  `request_changes`, `comment`, `unclear`
- `decision_match`: `1` if `decision_seen` matches the ground-truth expected decision, else `0`
- `blocker_recall`: if the ground truth contains a blocking concern, `1` when this review
  surfaces that same concern at priority P0 or P1, else `0`. If the ground truth contains
  **no** blocking concern, use `null`
- `false_blocker`: `1` if the review raises a P0 or P1 blocking finding that the ground
  truth does not support, else `0`
- `useful_secondary`: `1` if the review contains at least one correct non-blocking P2/P3
  observation, else `0`
- `notes`: one sentence of justification

Then:

- `technical_preference`: `"A"`, `"B"`, or `"tie"`. Return `"tie"` whenever neither output
  is clearly better on technical grounds. Ties are a legitimate, expected outcome — do not
  break a tie to produce a winner.
- `rationale`: two sentences maximum.

Judge only what the outputs actually say. Do not reward length, confident tone, or extra
sections that the ground truth does not support.

Write exactly one JSON object to `verdict.json` in your working directory, with this shape
and no additional prose:

```json
{
  "a": {"decision_seen": "...", "decision_match": 0, "blocker_recall": null, "false_blocker": 0, "useful_secondary": 0, "notes": "..."},
  "b": {"decision_seen": "...", "decision_match": 0, "blocker_recall": null, "false_blocker": 0, "useful_secondary": 0, "notes": "..."},
  "technical_preference": "tie",
  "rationale": "..."
}
```
