You are comparing two code-review messages that a pull-request author would receive.

You see only the two final messages, `output-a.md` and `output-b.md`, in your working
directory. You have no reference answer, no knowledge of how either was produced, and no
information about which is which. Do not speculate about their origin.

Judge purely as the author on the receiving end of this review:

- clarity — is it obvious what the reviewer is claiming?
- specificity — are claims tied to concrete code, actors, and mechanisms?
- actionability — does the author know what to do next?
- respect for the author's time — is it concise, or padded?
- tone — collaborative rather than accusatory or lecturing
- absence of internal process narration — the author should not be told about reviewer
  waves, subagents, adversarial verification passes, editor passes, or quality gates

Do not reward length, confident tone, or extra sections for their own sake.

Return `"A"`, `"B"`, or `"tie"`. Ties are a legitimate, expected outcome — return `"tie"`
whenever neither message is clearly better to receive, and do not break a tie to produce a
winner.

Write exactly one JSON object to `verdict.json` in your working directory, with this shape
and no additional prose:

```json
{
  "author_preference": "tie",
  "rationale": "..."
}
```
