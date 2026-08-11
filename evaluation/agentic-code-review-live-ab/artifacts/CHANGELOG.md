# Evaluation-session changelog

All changes below are evaluation-harness changes made by the coordinator in
this Work session. **The canonical skill package, frozen v19 baseline, golden
fixtures, and eval definitions are unmodified** (SHA-256 manifests verified at
extraction; baseline hashes re-verified in every run manifest).

## Harness additions (new files, package untouched)

1. `run_ab_parallel.py` — parallel paired runner derived from the bundled
   `evaluation/scripts/run_live_ab.py` (which is strictly serial and would need
   ~40+ hours for the mandated 750 runs). Preserves its directory layout,
   manifest fields, prompt templates, and per-case seeded variant-order
   randomization. Differences, applied identically to both variants:
   - bounded parallelism (6 concurrent child runs)
   - `claude -p` headless invocation with pinned model/effort/tools/timeout
   - children produce their review as the final message; the coordinator
     extracts it to `outputs/response.md` from the CLI JSON envelope. This
     replaces the bundled prompt's "save into the output directory"
     instruction because child agents are run with **no Write tool** (stricter
     read-only isolation than the bundled design).
   - the treatment reads a private per-run copy of the skill (`./skill/`)
     instead of a shared absolute path (isolation; no cross-run state)
   - full token/cost/turn metrics recorded per run
   - resumable: completed run directories are skipped on re-invocation
2. `build_golden_evals.py` — converts the 25 golden fixtures into runner cases.
   Runner-visible bundles contain title/description/diff/context (+ existing
   review state where present) and **never** the `expected` block.
3. `judge_ab.py` — blind-judge driver implementing the bundled rubric flow with
   per-(case, repetition, judge) independent A/B randomization, sealed mapping,
   and leakage redaction (variant-identifying strings replaced by `[policy]`
   in judge copies only; counts logged).
4. `select_escalations.py` — second-judge escalation selection per the
   handoff spec (P0/P1 differences, approve-vs-block divergence, structural
   non-ties, adjudication flags, 20% random sample).
5. `stats_ab.py` — paired statistics: sign tests, case-clustered bootstrap CIs,
   Wilson intervals, decision accuracy, efficiency percentiles, inter-judge
   agreement.

## Harness integrity fixes (documented deviations from bundled scripts)

1. **Ground-truth leak fix (both variants equally).** The bundled eval inputs
   `reviewing-pull-requests/evals/files/*.json` embed the `expected` block
   (decision/priority/finding), and the bundled SWE-PRBench importer writes
   `human_review_comments` into runner-visible fixtures. The bundled
   `run_live_ab.py` would hand these answers to both runners verbatim.
   `run_ab_parallel.py` strips `expected` and `human_review_comments` from the
   runner-visible copies only. Judges still receive full ground truth via the
   case definition. Package files themselves are unmodified.
2. **Anti-cheat ordering.** The bundled runner writes `task.json` (containing
   graded assertions) into the run directory before the child starts;
   `run_ab_parallel.py` writes it only after the child exits.
3. **Timeout.** 1800 s per run for both variants (the EVALUATION_REPORT's own
   recommended `--timeout 1800`), after a smoke pair showed the treatment's
   full multi-wave pass needs ~7 minutes on P1 fixtures.

## Environment installs

- `jsonschema` 4.26.0, `pytest` (present), `pandoc` 3.1.3 (for the one pandoc
  test), `skills-ref` 0.1.1 (official Agent Skills validator; both skills pass).

## Additional integrity fixes made during execution

4. **Error text was being graded as a review.** The runner wrote the CLI
   envelope's `result` field to `response.md` whenever it was non-empty —
   including API error text (usage-limit and safety-refusal messages). Blind
   judges caught this ("the output is a session-limit error message"). Fixed:
   `response.md` is written only for genuinely completed runs; error text goes
   to `error_message.txt`. 77 contaminated outputs were purged and 41 verdicts
   computed against them were invalidated; sealed A/B mappings were rebuilt
   deterministically from their seeds. All reported numbers are post-purge.
5. **Stale `failed` records from overlapping runner relaunches.** Concurrent
   relaunches could append a `failed` record after a successful retry of the
   same unit, hiding valid pairs. Readers now prefer completed records, and
   pair collection trusts on-disk artifacts rather than the manifest status.
6. **Judge dimension-key normalization.** Judges return rubric dimension names
   with varying punctuation/case; deltas are now matched on normalized keys so
   no dimension is silently dropped from the statistics.

## Skill changes

- **None.** The canonical skill, the frozen v19 control, the golden fixtures,
  and the eval definitions are byte-for-byte unmodified (hashes in
  `RUN_MANIFEST.json`).
- One measured failure **does** justify a change: the orchestration-trace
  leak documented in `LIVE_AB_REPORT.md` §6.1 (55% of Stage 1 treatment
  outputs narrate the wave process in the preamble, violating the skill's own
  private-trace boundary and matching a readability regression replicated
  across both blind judges and both stages). The patch was **not applied**
  because the iteration contract requires re-running the RED case, the writing
  family, the full deterministic suite, and the paired semantic subset before
  a change can be versioned — and model quota was exhausted before that
  re-validation could run. Applying an unvalidated fix would be worse than
  handing over a precisely-specified one.
