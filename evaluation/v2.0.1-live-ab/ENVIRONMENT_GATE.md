# Environment Gate

Recorded before experimental inference, per `START_HERE.md` § Environment gate.

## Required inventory

| Item | Finding |
|---|---|
| Callable model or agent command | `claude` CLI at `/opt/node22/bin/claude`, headless `-p` mode, verified working |
| Agent CLI version | 2.1.227 (Claude Code) |
| Runner model | `claude-sonnet-5`, provider `firstParty` (Anthropic), pinned with `--model` |
| Runner effort | `high`, pinned with `--effort` (host default `max` is scrubbed from runner env) |
| Judge model | `claude-opus-5` (technical), `claude-opus-5` (author-experience) — different model from runners |
| Fresh-process isolation | Yes. One fresh `claude` process per run; `--no-session-persistence`; per-run `CLAUDE_CONFIG_DIR`; host session identity scrubbed from env |
| Host-customization isolation | Yes. `--safe-mode` disables host CLAUDE.md, skills, plugins, hooks, MCP, custom agents; `--strict-mcp-config` |
| OS/filesystem isolation per run | Yes. Per-run mount namespace, all capabilities dropped, `--no-new-privs`. Verified by negative control (below) |
| Token / latency / cache telemetry | Yes. `--output-format json` yields input/output/cache-read/cache-creation tokens, `duration_ms`, `duration_api_ms`, `ttft_ms`, per-model usage, `total_cost_usd`, `permission_denials` |
| Tool-call telemetry | Partial. Permission denials and per-model usage are recorded; a per-tool call count is not exposed by the CLI JSON result envelope |
| Available subagents | `Agent` tool available inside the sandbox; enabled identically for both variants |
| Concurrency | 4 CPUs; 5 shards run in parallel; each shard is sequential internally |
| Repository access | Local git repo `anhtaih/agent-harness` on branch `claude/v19-code-review-ab-test-u23sga` |
| PR-platform access | GitHub MCP tools available, scoped to `anhtaih/agent-harness` only |
| Real-PR corpus | SWE-PRBench reachable via HuggingFace datasets-server; 100-PR split imported successfully |

## Filesystem isolation: design

Each run executes inside its own mount namespace created with `unshare --mount
--propagation private`. Inside the namespace:

1. The run directory is bind-mounted at its **original absolute path**, so absolute paths
   embedded in the generated prompt resolve identically inside and outside the sandbox.
   No prompt rewriting is performed.
2. `tmpfs` is mounted over `/srv/ab` (every other run and the sibling variant of the same
   case), `/tmp/claude-0` (the eval source package, judge-private ground truth, blind
   mappings), `/home/user` (the host repository), and `/root/.claude` (host skills, hooks,
   projects, session transcripts).
3. All capabilities are dropped with `setpriv --no-new-privs --bounding-set=-all`, so the
   process cannot remount and — as uid 0 without `CAP_DAC_OVERRIDE` — cannot bypass normal
   file permissions.

This satisfies `LIVE_AB_PROTOCOL.md`'s requirement that each run "receive a sandbox or
container that can read only its own run directory plus explicitly mounted tools and
repository inputs". The judge-private tree is not merely permission-denied to runners; it
is absent from their filesystem view.

## Negative control (measured, not asserted)

A canary layout was built with distinctive secrets in the judge-private directory, in the
sibling variant's output, and in an answer-bearing eval-set file. A probe was then executed
inside the sandbox:

| Target | Result |
|---|---|
| Sibling variant output (`old_prompt/response.md`) | blocked — absent from namespace |
| Judge-private ground truth | blocked — absent from namespace |
| Answer-bearing eval-set file | blocked — absent from namespace |
| Host repository | blocked — absent from namespace |
| Host skills directory | blocked — absent from namespace |
| Listing of the case directory | shows only the runner's own variant |
| `mount --bind` attempt | `permission denied` |
| Effective capabilities | `CapEff: 0000000000000000` |

## Input sanitization (measured)

The shipped `sanitize_eval_input.py` was verified on a real case: the fixture's `expected`
block, and the case's `expected_output`, `assertions`, `expected_priority` and
`expected_specialists` fields, are all absent from every runner-visible file. Runner-visible
grep hits for terms like `request_changes` are the skill's own policy vocabulary and the PR
diff itself, not ground truth.

## Environment fixes applied (harness, not package)

Two deterministic checks failed for environment reasons and were repaired without touching
the package:

- `pandoc` was absent; installed. `test_markdown_parses_with_pandoc` then passed.
- The `pytest` on `PATH` was a `uv`-isolated tool environment missing `jsonschema` and
  `PyYAML`, so `run_release_validation.py`'s `pytest` step failed while `python3 -m pytest`
  passed. Reinstalled with `uv tool install pytest --with jsonschema --with pyyaml`.

Neither is a package defect. Both are recorded so the validation result is reproducible.

## Limitations — declared, not substituted

1. **No cross-family judge is available.** Only Anthropic models are callable. The technical
   judge is cross-*model* (`claude-opus-5` judging `claude-sonnet-5` runners), which controls
   for runner self-preference but not for shared model-family bias. `LIVE_AB_PROTOCOL.md`
   asks for "one technical blind judge from a different model family"; that requirement is
   **not met**, and no substitute is presented as equivalent.
2. **No human adjudication is available.** `LIVE_AB_PROTOCOL.md` requires human adjudication
   of judge disagreements. No human is in the loop. Disagreements are recorded and reported
   as an unadjudicated rate; all disagreeing pairs are preserved for later adjudication.
3. **Per-tool call counts are not exposed** by the CLI result envelope, so tool-call
   telemetry is limited to permission denials and per-model token usage.
4. **The SWE-PRBench runner-visible input retains `pr_url`, `repo`, `task_id`, and commit
   SHAs.** With any network egress these are a path to the real PR and its human review
   comments. This is a concealment hole in the shipped importer. Stage 4 inputs are
   additionally stripped of these keys before running; see the Stage 4 section of the report.

## Gate decision

The isolation requirement in `LIVE_AB_PROTOCOL.md` — the one condition that would force a
stop — **is met and measured**. Runner agents cannot reach judge-only ground truth, blind
mappings, sibling outputs, the source eval set, or human review comments.

Release-grade semantic A/B execution proceeds, with limitations 1 and 2 above carried into
every conclusion: they cap what this evaluation can certify, and they are restated in the
final report rather than absorbed.
