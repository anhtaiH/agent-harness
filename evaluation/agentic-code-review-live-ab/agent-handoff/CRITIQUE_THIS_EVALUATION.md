# The Case Against Our Own Evaluation

Written by the evaluating agent, unprompted, to give the receiving agent
material to push back with. Every item here is a real reason to discount
something we reported. If you find more, add them.

## 1. The judges are barely better than noisy

Inter-judge Cohen's κ: **0.40** (Stage 1), **0.17** (Stage 2). By the usual
reading that is "fair" and "slight". Two judges scoring the same 77 pairs
disagreed on the winner in 25 of them.

Implication: **any single-judge result in this report is weak evidence.** The
Stage 2 conclusion survives only because two judges independently reached
significance in the same direction — which is a much weaker claim than
"the judges agreed".

If you want to reject Finding 2 on the grounds that a κ=0.17 instrument
should not be used to make release decisions, that is defensible. We would not
argue hard against it.

## 2. The primary judge shares a model family with the runners

`claude-fable-5` generated both arms' outputs in Stages 1–2 **and** served as
the primary judge. Self-family stylistic preference cannot be excluded. The
secondary judge (`claude-opus-5`) is a different model and reproduced the
direction, which mitigates this — but both are Anthropic models, so a shared
family-wide preference (e.g. for a particular review register) would not be
detected by either.

**No cross-provider judge was available. This is the single biggest
methodological gap in the evaluation.**

## 3. The sign test throws away most of the data

Stage 2 secondary: 33 new wins, 13 old wins, **116 ties**. The p=0.0045 is
computed on 46 decided pairs and ignores the 116 ties. That is standard for a
sign test, but it means the headline is driven by 28% of the sample.

An alternative reading of the same data: **in 72% of official-eval pairs, a
blind judge could not tell the two apart.** That framing is equally true and
much less flattering to the treatment. We chose the sign test because it is
the paired test the handoff spec asked for; you are entitled to prefer the
tie-inclusive framing.

## 4. The official eval set may reward the skill's own format

Stage 2's mechanical gain comes substantially from two assertions: "review
includes decision or clear merge action" and "QA Spec is present". The
treatment's `SKILL.md` explicitly prescribes both. The control (v19) also
prescribes them, so this is not pure circularity — but the eval set was
authored alongside the skill, and we cannot rule out that it encodes the
skill's output conventions rather than review quality as such.

**We consider this the most likely way Finding 2 is inflated.** If you conclude
the eval set is format-biased, the honest fix is to re-score Stage 2 on
outcome-based criteria, not to trust the +0.046.

## 5. Under-powered nearly everywhere

- 69 Stage 1 pairs cannot detect a small recall difference. Our "tie" and our
  "non-inferior" could both be masking a real 5-point gap in either direction.
- Stage 2 reached 54% of planned pairs; case-level majority aggregation is
  meaningless with 1–3 uneven repetitions per case.
- Stage 3 is 27 pairs, one repetition, **unjudged**, and used a different
  runner model. It supports no semantic conclusion at all.
- No multiple-comparison correction across 12 rubric dimensions. Individual
  dimension results should be treated as exploratory — *except*
  `public_readability`, which replicates four times and is independently
  reproducible without a judge.

## 6. The decision-accuracy number depends on a regex

Stage 1's 88.4% vs 90.3% comes from a regex that parses "approve" /
"request changes" out of prose. We spot-checked it; we did not exhaustively
validate it. A parser bug would move that number. `raw/stage1-golden/final-decisions.csv`
contains every parse — check the ones you care about.

## 7. Our contamination fix happened mid-run

77 outputs containing API error text reached the grader before we caught it.
We purged them and invalidated 41 verdicts. But:

- verdicts produced *before* the fix against *clean* pairs were retained rather
  than re-run. We believe they are unaffected, since the contamination was
  per-artifact, not systemic. We did not re-run them to prove it.
- the purge used a regex over error strings. If an error phrasing existed that
  the regex missed, contaminated outputs may remain in the graded set. We
  found none in manual sampling. That is not the same as none existing.

## 8. Losses were symmetric — but "symmetric" was not formally tested

Stage 2 failures: 105 treatment, 103 control. That looks balanced, and it is
the basis for our claim that pairing integrity holds. We did not test whether
the *specific cases* lost were the same on both sides in every instance. If
harder cases systematically failed on one arm, the surviving sample would be
biased. **This is worth checking and we did not check it.**

## 9. We may have anchored on the one finding we could measure without a judge

Finding 4 (narration leak) is the one we state most confidently, and it is the
one measurable by regex. There is a real risk we over-weighted it *because* it
was measurable, and under-weighted harder-to-measure dimensions like whether
the treatment's findings are actually more useful to a human author. Nobody in
this evaluation was a human author. **Every "author experience" claim here is a
model's guess about what a human would prefer.**

## 10. What would change our conclusion

We would withdraw the "acceptance gate not passed" verdict if:

- the narration-leak examples turn out to read as acceptable reviewer prose to
  a human reviewer (we think they do not, but we are not the audience), **or**
- the readability dimension is judged to be measuring register/verbosity rather
  than genuine cognitive load, **or**
- a human author sample prefers the treatment's outputs despite the narration.

We would strengthen it if a cross-provider judge reproduced the readability
regression.

## 11. What we would not withdraw

The two harness defects (ground-truth leakage into runner inputs; API error
text being graded as reviews) are verifiable by reading the files. They do not
depend on any judgment of ours, and no amount of disagreement about the A/B
result affects them.
