# Reproduce Finding 4 — the orchestration-narration leak

This is the one finding that does not require trusting a model judge. Verify it
yourself in a few minutes, then decide whether it is real.

## The claim

The treatment narrates its internal wave orchestration in the conversational
preamble that precedes the review body, at a much higher rate than the control:

| Stage | Control | Treatment |
|---|---:|---:|
| 1 — golden fixtures | 6/72 (8%) | **38/69 (55%)** |
| 2 — official evals | 3/166 (2%) | 14/164 (9%) |
| 3 — real PRs | 0/29 (0%) | 1/27 (4%) |

Median output length is comparable (Stage 1: 3,690 chars treatment vs 3,820
control), so this is **not** a verbosity difference.

## Why it matters (this is the part to challenge)

`SKILL.md` states as a hard boundary:

> Do not expose raw reviewer output, private reasoning, model logs, search
> history, context packets, trust maps, or review ledgers.

Our reading: preamble text like "four independent first-wave missions ran" and
"survived adversarial verification" exposes the private orchestration trace and
so violates this rule. It also correlates with the `public_readability`
regression both blind judges measured independently.

**Where you can legitimately disagree:** you may hold that the boundary governs
the *posted review body* only, and that the conversational preamble to the
human operator is exempt — it is not posted anywhere. That is a coherent
position. If you take it, the leak is a style question, not a rule violation,
and the readability regression needs a different explanation.

We think the exemption is wrong because the preamble is what the operator
actually reads, and because two independent judges docked readability without
being told to look for narration. But this is the strongest counter-argument
available and we would rather you make it than nod along.

## The detection method (exact)

```python
import re
NARRATION = re.compile(
    r"(first-wave|four independent|wave \d|adversarial (verifier|verification|disconfirmation)|"
    r"survived (adversarial|disconfirmation)|specialist(s)? (ran|dispatched)|coordinator|"
    r"counter-design|falsifier|editor pass|public-editor|quality gate (passes|passed)|"
    r"review effort (tier|classified)|compact tier|trust map|context packet|review ledger)", re.I)

def preamble(text: str) -> str:
    """Everything before the review body starts."""
    m = re.search(r'^#{1,3}\s*(review preview|proposed|top-level)', text, re.I | re.M)
    return text[:m.start()] if m else text[:1500]

leaked = bool(NARRATION.search(preamble(response_text)))
```

Applied to `outputs/response.md` for every run in each workspace.

## Known weaknesses of this method — check these

1. **`coordinator` is in the pattern.** A review could use that word innocently.
   Re-run with `coordinator` removed and see how much the 55% drops. We did not.
2. **The preamble split is heuristic.** If a treatment output does not use a
   `## Review preview` heading, the first 1500 chars are scanned, which may
   include review body text. Check whether that inflates the count.
3. **Binary per-output.** One match counts the same as six. Mean matches per
   Stage 1 treatment preamble was 1.23 vs 0.10 for control, so the gap holds
   under a count-based measure too, but the headline is the binary rate.
4. **The control had no opportunity to leak this vocabulary** — v19 does not
   have named waves or specialists. So part of the gap is that the treatment
   *has* internal machinery to describe and the control does not. **This is a
   fair objection.** The counter is that having machinery does not require
   narrating it, and 45% of treatment runs did not narrate it (see
   `evidence/counterexamples/`).
5. **Our regex under-counts — we found this ourselves while packaging.**
   `evidence/counterexamples/02` is classified CLEAN by the regex, but its text
   says *"run in preview mode per the skill"* and *"the skill's convergence rule
   says this approves"*. That is self-reference to the governing policy, which
   arguably belongs in the same category. The pattern has no term for "the
   skill" / "per the skill" / "the rule says". **So 55% is a floor, not a
   ceiling** — a broader pattern would likely score the treatment worse, not
   better. We are reporting the narrower number because that is what we
   actually ran. If you re-run with a broader pattern, report both.

## What to look at

- `evidence/narration-leak/01..08` — eight verbatim preambles, highest match
  counts first. Read them as if you were the PR author. Do they read as review,
  or as the reviewer describing its own process?
- `evidence/counterexamples/01..04` — four treatment preambles with no
  narration at all, same skill, same conditions. **Any fix must leave these
  unchanged.** They are the regression test.

## The honest bar

If, reading the eight examples, you judge that **≥3 are acceptable reviewer
prose**, then our 55% is inflated and Finding 4 should be downgraded. Say so.

If you judge that most of them genuinely expose internals, the finding stands
and the question becomes what to do about it — see
`PROPOSED_CHANGE_UNVALIDATED.md`, including the reasons to reject our proposal.
