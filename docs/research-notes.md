# Research Notes

Agent Harness tracks public harness-engineering practice. Last refreshed: July 2026.

## Instruction files: AGENTS.md convergence

AGENTS.md is the cross-tool instruction standard (stewarded by the Agentic AI Foundation under the Linux Foundation; adopted by Codex, Cursor, Gemini CLI, opencode, Zed, Copilot, and ~20 more). Claude Code still reads CLAUDE.md rather than AGENTS.md, so the harness renders one shared instruction body into each tool's native location (`~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md`, `~/.config/opencode/AGENTS.md`, `~/.pi/agent/APPEND_SYSTEM.md`, `.cursor/rules/*.mdc`) as marker-delimited managed blocks.

Evidence on content: short root files win. HumanLayer recommends <300 lines with progressive disclosure; Augment's evals found 100-150-line instruction files plus on-demand reference docs outperform long files, and architecture over-description reduces completeness. The harness keeps its managed block ~10 lines and points to the long-form runtime instructions.

- https://agents.md/
- https://www.humanlayer.dev/blog/writing-a-good-claude-md
- https://www.augmentcode.com/blog/how-to-write-good-agents-dot-md-files

## Gates as hooks, not prose

The deployed pattern for guardrails is native hook wiring, not instruction text: Claude Code hooks (`PreToolUse` with `permissionDecision: allow|ask|deny`, `UserPromptSubmit`, `Stop` with `stop_hook_active` loop guards, `SessionStart` context injection), Cursor `hooks.json` (`beforeShellExecution`/`beforeMCPExecution` returning `{"permission": ...}`), opencode plugins (`tool.execute.before`), and pi extensions (blockable `tool_call`). Reference deployments: Anthropic's bash-command validator example, tdd-guard, sensitive-canary (UserPromptSubmit secret blocking), git-guard. The harness ships one Python policy engine and bridges it into each surface, then proves behavior with `verify-gates`.

- https://code.claude.com/docs/en/hooks
- https://cursor.com/docs/agent/hooks
- https://opencode.ai/docs/plugins/
- https://github.com/nizos/tdd-guard

## Sandboxing and deny-by-default

Anthropic ships OS-level sandboxing (Seatbelt/bubblewrap, open-source `sandbox-runtime`) and documents bypass-permissions as container-only; Codex runs Landlock/seccomp with `sandbox_mode` + `approval_policy`; both vendors added auto-classifiers that block destructive commands. The harness complements (not replaces) these with permission deny seeds (`Read(**/.env)`, `Read(~/.ssh/**)`) and env scrubbing in wrappers and the MCP server.

- https://code.claude.com/docs/en/sandbox-environments
- https://github.com/anthropic-experimental/sandbox-runtime
- https://developers.openai.com/codex/config-reference

## Prompt injection and MCP security

Operating assumptions: Simon Willison's lethal trifecta (private data + untrusted content + external communication must never combine), Invariant Labs' tool-poisoning/rug-pull findings, and MCPTox. Consequences in this harness: connector writes require task-scoped intents, PR review is draft-only, tool output is treated as untrusted, secrets are blocked at the prompt boundary, and MCP servers should be allowlisted in tool config.

- https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks
- https://arxiv.org/pdf/2508.14925

## MCP vs CLI

Anthropic's "Code execution with MCP" (98.7% context reduction by moving from schema-loading to code APIs) and Ronacher's CLI-first essays set the 2026 rule of thumb: prefer CLIs the agent can compose; use MCP for auth-gated SaaS and control planes; defer schemas. The harness follows it: one small MCP control plane (task/evidence/review state machine), a full CLI equivalent for CLI-first tools like pi, and no generic-shell MCP tools.

- https://www.anthropic.com/engineering/code-execution-with-mcp
- https://lucumr.pocoo.org/2025/7/3/tools/

## Context engineering and state

Anthropic's context-engineering guidance (attention budget, compaction, structured note-taking, subagent isolation) and Chroma's context-rot research motivate the harness's file-based state: task packets, progress checkpoints, evidence documents, and the session-start capsule survive compaction and session restarts; heavy review work runs in isolated lanes.

- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://research.trychroma.com/context-rot

## Orchestration patterns

Patterns the harness aligns with: orchestrator-worker fan-out with independent verifier/critic lanes (Anthropic multi-agent research), plan-then-execute/spec-driven development (github/spec-kit, Agent OS), git worktrees for parallel isolation (now native in major tools), ralph-style bounded loops with file/git state and test backpressure, and graph task queues (Yegge's beads). The harness's task packets, review lanes, and worktree policy are local implementations of these.

- https://www.anthropic.com/engineering/built-multi-agent-research-system
- https://github.com/github/spec-kit
- https://ghuntley.com/ralph/
- https://github.com/gastownhall/beads

The 2026 wave made this concrete, and `harness orchestrate` is the local translation of three systems:

- OpenAI's Symphony spec (April 2026): an issue tracker as the agent control plane — poll ready work, isolated workspace per task, dispatch to completion, restart stalls, watch CI, human review at the end. Locally: `plan.json` + `ledger.jsonl` are the tracker, the conductor is the poller/watchdog.
- Steve Yegge's Gas Town (January 2026): Overseer → Mayor → Polecats/Witness/Refinery/Deacon role fleet over beads. Locally: deterministic conductor as Mayor, role contracts in `roles/*.md`, one-writer serialization as the Refinery, stale-step requeue as the Deacon.
- GPT-5.6 Sol Ultra (July 2026): model-native dynamic decomposition — the planner decides the role fan-out per task. Locally: the planner role emits the step graph (validated, capped, cycle-checked), with a deterministic fallback plan.

- https://openai.com/index/open-source-codex-orchestration-symphony/
- https://www.infoq.com/news/2026/05/openai-symphony-agents/
- https://steve-yegge.medium.com/welcome-to-gas-town-4f25ee16dd04
- https://yegge.ai/gastown
- https://openai.com/index/gpt-5-6/
- https://www.marktechpost.com/2026/07/09/openai-releases-gpt-5-6-a-three-tier-model-family-with-programmatic-tool-calling/

## Ecosystem: personal/meta harnesses

Comparable projects: obra/superpowers (skills + methodology, multi-harness plugin), affaan-m/ECC, wshobson/agents, SuperClaude, ruvnet/ruflo, buildermethods/agent-os, steipete/agent-scripts (canonical rules + per-tool symlink mirrors), the dotagents family (`.agents/` as source of truth), and danielmiessler's LifeOS ("paste this URL into your agent" install). Shared traits the harness adopts: agent-prompt install with deterministic scripts underneath, idempotent managed edits with backups and full uninstall, skills as the packaging unit (Agent Skills standard), doctor/self-check commands, and cross-tool adapters from one canonical source.

- https://github.com/obra/superpowers
- https://github.com/humanlayer/12-factor-agents
- https://github.com/getsentry/dotagents
- https://agentskills.io
