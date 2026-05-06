# Research Notes

Agent Harness is informed by several public patterns and local lessons.

## Harness Engineering

OpenAI’s harness engineering framing treats the agent as a worker inside a purpose-built loop: task setup, tool access, verification, feedback, and iteration. This project applies that locally with task packets, worktrees, MCP tools, review lanes, and evidence gates.

Sources:

- [OpenAI: Harness Engineering](https://openai.com/index/harness-engineering/)
- [OpenAI: Unlocking the Codex Harness](https://openai.com/index/unlocking-the-codex-harness/)

## Surface-Agnostic Agents

The same runtime should work from desktop apps, TUIs, CLIs, and headless agent calls. The package exposes a local MCP server, CLI shims, and natural-language router instructions so Codex, Claude, Cursor, or future tools can share one control plane.

## Small Measurable Loops

Karpathy’s `autoresearch` style emphasizes bounded runs, explicit outputs, and repeatable scoring. Agent Harness mirrors this with golden evals, evidence documents, metrics JSONL, and local reports.

Source:

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch)

## Markdown Knowledge Bases

Markdown knowledge works when claims are source-backed, easy to diff, and promoted deliberately. The harness keeps mutable local memory as candidates, then expects humans to promote stable lessons into project-owned docs.

Reference pattern:

- [karpathy/llm.c wiki](https://github.com/karpathy/llm.c/wiki)

## MCP Security

MCP expands agent capability, so the harness treats tools as scoped surfaces. It avoids raw token passthrough, keeps write intents task-scoped, and leaves hard stops for secrets and production-affecting actions.

Source:

- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)

## Local Product Principle

The product interface is not the backend command. Humans should be able to install once, then ask natural-language tasks. Backend commands exist for diagnosis, automation, and fallback.
