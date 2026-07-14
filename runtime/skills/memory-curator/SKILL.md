---
name: memory-curator
description: Curate local harness memory from task evidence and inbox notes. Use when finishing tasks that produced reusable lessons, when the memory inbox has accumulated candidates, or when the user asks to promote knowledge. Only durable, source-backed, non-sensitive claims survive curation.
---

# Memory Curator

- Treat `memory/inbox/` as candidate material only; canonical claims live in `memory/claims.jsonl` and project-owned docs.
- Promote a candidate only if it is durable (still true next month), source-backed (cites a file, commit, command, or doc), and non-sensitive.
- Keep claims compact: one sentence, one source, one confidence level.
- Record failures worth remembering in `memory/failures.jsonl` with the trigger and the fix.
- Team-useful lessons are upstream candidates: propose them for project-owned docs (AGENTS.md, docs/) and let a human land them.
- Never store secrets, tokens, personal data, or raw logs containing them; the redaction gate rejects them anyway.
