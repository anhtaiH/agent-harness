You are grading two candidate code-review outputs written for the same real pull request.
They are labelled A and B. You do not know which system produced either one, and you must
not speculate about their origin or mention evaluation machinery.

Read these files in your working directory:

- `case.json` — the sanitized pull-request input that both reviews were given
- `ground-truth.json` — the review comments real human maintainers left on this pull
  request, visible only to you
- `output-a.md` and `output-b.md` — the two candidate reviews

The human comments are the reference, but they are **not exhaustive**: a real reviewer
raises some issues and misses others. A candidate finding that the humans did not mention
is not automatically wrong. Classify each candidate's findings with the standard rubric:

- **CONFIRMED** — substantively matches a concern a human reviewer actually raised
- **PLAUSIBLE** — not raised by a human, but supported by the diff and a reasonable thing
  for a reviewer to say
- **FABRICATED** — contradicted by the diff, or asserts behaviour, code, or context that
  is not present in the input

Per-output fields:

- `decision_seen`: the review's proposed submission type — one of `approve`,
  `request_changes`, `comment`, `unclear`
- `confirmed_count`: integer, how many distinct human concerns this review independently
  surfaced
- `plausible_count`: integer
- `fabricated_count`: integer
- `human_recall`: `1` if `confirmed_count` >= 1, else `0`. If the human comments contain no
  substantive technical concern (for example only "LGTM", a nit, or process chatter), use
  `null`
- `any_fabricated`: `1` if `fabricated_count` >= 1, else `0`
- `notes`: one sentence of justification

Then:

- `technical_preference`: `"A"`, `"B"`, or `"tie"`. Return `"tie"` whenever neither output
  is clearly better on technical grounds. Ties are a legitimate, expected outcome — do not
  break a tie to produce a winner.
- `rationale`: two sentences maximum.

Judge only what the outputs actually say. Do not reward length, confident tone, or extra
sections. A review that correctly says there is nothing blocking is not worse than one that
manufactures a concern.

Write exactly one JSON object to `verdict.json` in your working directory, with this shape
and no additional prose:

```json
{
  "a": {"decision_seen": "...", "confirmed_count": 0, "plausible_count": 0, "fabricated_count": 0, "human_recall": null, "any_fabricated": 0, "notes": "..."},
  "b": {"decision_seen": "...", "confirmed_count": 0, "plausible_count": 0, "fabricated_count": 0, "human_recall": null, "any_fabricated": 0, "notes": "..."},
  "technical_preference": "tie",
  "rationale": "..."
}
```
