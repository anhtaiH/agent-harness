# Proposed Change — UNVALIDATED. Reasons to reject it are included.

**Status: hypothesis, not a recommendation you should adopt on our word.**
We did not apply it and did not test it. Model quota ran out first. We are
handing you a specification, not a patch, precisely so you evaluate it rather
than merge it.

## What we would try

Extend the private-trace boundary so it explicitly covers the conversational
preamble, not only the posted review body.

In `SKILL.md`, the existing hard boundary reads:

> Do not expose raw reviewer output, private reasoning, model logs, search
> history, context packets, trust maps, or review ledgers.

Candidate addition (wording is illustrative, not prescriptive):

> This applies to everything you emit, including any summary you address to
> the human operator before or after the review payload. Do not narrate wave
> structure, mission counts, specialist dispatch, verification passes, editor
> passes, or quality-gate completion. State conclusions and their evidence;
> the process that produced them is not part of the output.

The same constraint would need to appear in `references/execution-modes.md`,
which governs terminal output.

## Why we think this is the right shape of fix

- It targets the measured mechanism (preamble narration) rather than the
  symptom (a readability score).
- 45% of treatment runs already comply, so the behavior is achievable within
  the current design — this is a tightening, not a redesign.
- It does not touch routing, wave structure, verification, or priority logic,
  which measured **non-inferior or better** (`disconfirmation_and_evidence`
  +0.12 to +0.29 across four measurements). Those should not be disturbed.

## Reasons to reject or modify it — take these seriously

1. **The premise may be wrong.** If you hold that the operator-facing preamble
   is legitimately exempt from the private-trace rule (see
   `REPRODUCE_FINDING_4.md` §"Where you can legitimately disagree"), this
   change is unnecessary and you should reject it.
2. **It may suppress useful caveats.** Some narration we flagged carries real
   information — e.g. "I reviewed from the provided bundle only, so the live
   head revision could not be checked". That is a genuine limitation
   disclosure, not process theater. A blunt prohibition could delete it. If you
   adopt anything, the rule must distinguish *evidence limitations* (keep) from
   *process description* (cut). **We did not solve that distinction.**
3. **It may trade against a dimension that is currently winning.** Both judges
   scored the treatment *higher* on `disconfirmation_and_evidence`. If some of
   that credit comes from the model signalling that it verified things,
   suppressing the signal could pull that dimension down. **This is the
   specific risk to measure.** Our acceptance condition would be: readability
   delta moves to ≥ 0 **without** `disconfirmation_and_evidence` dropping.
4. **More prose to fix a prose problem.** Adding instructions to a skill that
   already has 195 lines of coordinator policy may not change behavior at all —
   the 55% of runs that narrate did so *while* the existing boundary was in
   context. A behavioral fix (e.g. a final output-shaping step that strips
   process vocabulary) might work where more policy text does not. **We think
   this objection is strong and we do not know the answer.**
5. **Effect size is unmeasured.** We do not know how much of the −0.26 to −0.41
   readability gap is attributable to narration versus other differences. It
   could be most of it or a minority of it.

## How to validate it, if you try it

The iteration loop this evaluation was run under requires, in order:

1. the smallest failing case: `golden-docs-typo-clean` — a one-line docs typo
   where the treatment narrates the four-wave process before the review
2. the affected family: the writing/public-output fixtures
3. the full deterministic suite — `validate_package.py` (both skills),
   `pytest evaluation/tests`, `compare_baseline.py`, `agentskills validate`
4. the paired semantic subset — re-run Stage 1 + a Stage 2 slice with the
   harness in `harness/`, then re-judge blind

**Acceptance condition:** `public_readability` delta ≥ 0 **and**
`disconfirmation_and_evidence` does not regress **and** the four clean
counterexamples in `evidence/counterexamples/` are unchanged in character.

If readability improves but disconfirmation drops, the change is a wash and
should be reverted, not shipped.

## Separately: two harness defects we would fix first

These do not depend on any judgment of ours and are verifiable by reading the
files. We consider them higher priority than the A/B result itself, because
they corrupt every future measurement you make:

1. **Runner inputs leak ground truth.** `reviewing-pull-requests/evals/files/*.json`
   contain the `expected` block; `import_swe_prbench.py` writes
   `human_review_comments` into runner-visible fixtures. `run_live_ab.py` copies
   both to the runners. See `harness/run_ab_parallel.py` for the strip.
2. **`grade_live_ab.py` will score API error text as a review.** The runner
   writes the CLI `result` field to `response.md` even on error. Gate on
   `is_error` and exit code before writing.

And one assertion bug, which is **yours to decide** because fixing it changes
your historical numbers: `priority-confidence model is usable` fails any output
containing both `[p1` and "non-blocking", which `[P2 · Non-blocking]` trips by
construction. 0 of 17 Stage 1 failures were genuine. We deliberately left it
unmodified rather than edit a ground-truth check in a variant's favour.
