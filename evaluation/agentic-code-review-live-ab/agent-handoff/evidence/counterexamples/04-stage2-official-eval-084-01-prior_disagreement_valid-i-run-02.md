# Treatment output preamble — CLEAN counterexample 4

The same skill, same conditions, no orchestration narration. Any fix must keep
outputs like this unchanged.

- stage: `stage2-official`
- case: `eval-084-01-prior_disagreement_valid-initial_preview`
- repetition: `run-02`
- source: `workspace/stage2-official/run-02/eval-084-01-prior_disagreement_valid-initial_preview/new_skill/outputs/response.md`

## Verbatim preamble

```
I've finished checking the environment, and I have to stop short of producing the review preview: **there is no pull request here to review.** Rather than invent one, here's exactly what I found and what I need from you.

## What I checked

- The working directory contains only the review skill itself (`./skill`) and the task prompt — no source files, no TypeScript, no diff or patch file.
- It is not a git repository, and no `.git` metadata, branches, or commits exist anywhere reachable from this workspace, including the parent directory.
- No pull-request platform tooling (GitHub CLI, API connector, or configured project-adapter actions) is available in this session, so I can't fetch a PR by reference either.
- The task's own input manifest lists no input files.

The review skill I'm following requires me to anchor every finding to the PR's actual head revision, diff, and existing review threads, and it explicitly forbids inventing sources. A "prior disagreement" re-review depends even more heavily on real state — the earlier review comments, the author's rebuttal, and the commits since — none of which exist here. Fabricating a plausible-looking TypeScript review preview would produce findings with no evidence behind them, so I won't do that.

## What I need to proceed

Any one of these will unblock the review:

1. **A repository path** (with the PR branch and its base branch available locally), plus which branch or commit range to review.
2. **A diff or patch file** togethe
```
