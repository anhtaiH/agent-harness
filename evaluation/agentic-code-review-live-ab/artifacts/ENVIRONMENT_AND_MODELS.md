# Environment and Models

Capability inventory for the live semantic A/B evaluation of
`agentic-code-review-skills-v2.0.0` (treatment) versus the frozen v19 prompt
pair (control). Recorded before any evaluation run, per
`START_HERE_WORK_ULTRA.md`. Nothing below is assumed; every line was probed.

## Session

- Surface: Claude Code remote execution environment (managed container, Linux 6.18.5, 4 vCPU, 15 GB RAM)
- Coordinator model: started as `claude-fable-5`; **switched to `claude-opus-5` mid-session** by the operator at ~13:30 UTC. Runner and judge models are pinned explicitly on every child invocation, so this did not alter any A/B run.
- Coordinator thinking budget: `MAX_THINKING_TOKENS=31999` (inherited identically by all child CLI runs)
- Date of evaluation: 2026-08-10

## Capability probe results

| Capability | Status | Evidence |
|---|---|---|
| Native parallel subagents | YES | In-session `Agent`/`Workflow` tools (workflow concurrency cap: min(16, nproc−2) = 2 per workflow); plus headless `claude -p` child processes (Claude Code CLI 2.1.226), which is what the bundled provider-neutral harness expects |
| Concurrent child runs used | 6 | `claude -p` processes are network-bound; 6 concurrent on 4 vCPU verified stable |
| Fresh isolated child contexts | YES | each `claude -p` invocation starts a fresh context (verified: full system-prompt cache creation on each new run); run cwd is an isolated per-run directory |
| Terminal / Python runtime | YES | Python 3.11.15, pytest 9.0.2, pandoc 3.1.3 (installed during session), jsonschema 4.26.0 (installed during session) |
| Zip extraction, local file R/W | YES | handoff archive extracted; SHA-256 manifest verified OK |
| Git | YES | git 2.43.0; working clone of `anhtaiH/agent-harness` on branch `claude/agent-skills-code-review-eval-ehm3n2` |
| GitHub / PR platform | PARTIAL | GitHub MCP tools available but **scoped to `anhtaih/agent-harness` only**; no `gh` CLI. Arbitrary public-repo PR reading is out of policy scope for this session |
| Token / latency / tool-call metrics | YES | `claude -p --output-format json` returns input/output/cache tokens, cost USD, wall + API duration, turn count, per-model usage, and permission denials for every run |
| External model providers | **NO** | No OpenAI/Google/other credentials present. Only Anthropic first-party models (fable-5, opus, sonnet, haiku tiers reachable through the CLI) |
| Official Agent Skills validator | YES | `skills-ref` 0.1.1 from PyPI installs the `agentskills` CLI; both skills validate clean (this was unavailable in the original sandbox) |
| Outbound network | PARTIAL | HTTPS via managed agent proxy; pypi.org, huggingface.co reachable. Usable for the SWE-PRBench dataset probe in Stage 3 |

## Provider-diversity limitation (explicit)

The skill's Wave-3 instruction prefers verifiers and public editors "from
another model family." **Only the Anthropic Claude family is available in this
environment.** All runner, judge, and verifier roles are Claude models.
Cross-provider diversity is therefore NOT exercised; what is exercised is
model-independent orchestration plus intra-family diversity (primary blind
judge `claude-fable-5`, secondary blind judge `claude-opus-5`). Multiple
subagents running in parallel are all the same provider; no result below
should be read as evidence of provider-diverse behavior.

## A/B execution vehicle

Both variants run through identical headless commands; only the policy payload differs:

```
claude -p --model claude-fable-5 --effort high --output-format json \
  --strict-mcp-config \
  --allowedTools "Read,Grep,Glob,Task" \
  --disallowedTools "Bash,Write,Edit,NotebookEdit,WebFetch,WebSearch,Skill,SlashCommand,KillShell,BashOutput"
```

- Control: frozen v19 preview prompt embedded verbatim in the run prompt (`<baseline_prompt>` block), exactly as the bundled `run_live_ab.py` template does.
- Treatment: private copy of `reviewing-pull-requests/` placed inside the run directory; prompt points at `./skill/SKILL.md`.
- Identical between variants: model, effort, thinking budget, tool allowlist, timeout, fixture inputs, working-directory isolation, retry policy.
- Read-only enforcement: children have no Bash/Write/Edit/network tools; GH/NPM/GCloud tokens are stripped from the child environment; `--strict-mcp-config` removes all MCP servers (no GitHub access at all in children); permission auto-deny blocks reads outside each run directory.
- Anti-cheat: `task.json` (which carries graded assertions / fixture ground truth) is written into the run directory only after the child process exits.
- Randomization: variant execution order shuffled per (case, repetition) with a deterministic seed.
- Metrics: the CLI JSON envelope per run is preserved (`stdout.txt`) with tokens, cost, duration, and turns extracted into `timing.json` and `runs.jsonl`.

## Judging vehicle

- Primary blind judge: `claude-fable-5`, fresh context per pair, zero tools, receives rubric + case ground truth + anonymized Output A/B only.
- Secondary blind judge (escalations + 20% sample): `claude-opus-5`, independently re-randomized A/B assignment.
- A/B assignment: independent seeded coin per (case, repetition, judge); the sealed mapping is stored separately from judge inputs/outputs.
- Leakage control: variant-identifying strings in judge copies are replaced with `[policy]` and counted; raw outputs are preserved unmodified.

## What this environment cannot do (no silent substitution)

1. No cross-provider A/B or cross-provider verification (Anthropic-only credentials).
2. No arbitrary-repository GitHub PR reads (session repo scope is `anhtaih/agent-harness` only); Stage 3 therefore depends on the public SWE-PRBench dataset export rather than live GitHub PR APIs.
3. No `gh`/`hub` CLIs (GitHub MCP only, scoped as above).
4. In-session `Workflow` concurrency is capped at 2 on this 4-vCPU container; heavy fan-out is done with `claude -p` child processes instead (6 concurrent).


## Post-hoc addenda (recorded during execution)

### Model quota exhaustion
- `claude-fable-5` (Stage 1–2 runner and primary judge) hit account limits
  twice: a session limit resetting 11:50 UTC, then a model-specific
  "You've reached your Fable 5 limit" that was still in force at 15:50 UTC.
- `claude-opus-5` / `claude-sonnet-5` remained available and were used for
  Stage 3 (both arms) and for the secondary blind judge.
- A further session limit (reset 18:30 UTC) stopped Stage 3 judging.

### Judge assignment as executed
- Primary blind judge: `claude-fable-5` — 69 Stage 1 pairs, 77 Stage 2 pairs
  (partial coverage; quota-capped).
- Secondary blind judge: `claude-opus-5` — 69 Stage 1 pairs, 162 Stage 2 pairs
  (full coverage of usable pairs). Independent seeded A/B re-randomization.
- Adversarial verdict audit: 14 in-session read-only subagents over all
  non-tie Stage 1 verdicts.
- Stage 3: no judge pass (quota).

### Process-execution constraint
Detached (`nohup`) background processes are terminated at turn boundaries in
this environment. Batches were therefore executed as bounded foreground
windows (~580 s each), with the runner's resume logic preserving completed
units across windows.
