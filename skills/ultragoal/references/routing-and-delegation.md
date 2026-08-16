# Routing and Delegation

Load this reference only for Medium or Heavy routes, child-model selection, or
routing-policy evaluation. Keep routine Light goals on the core workflow.

- [Optimization contract](#optimization-contract)
- [Model and effort roles](#model-and-effort-roles)
- [Route admission](#route-admission)
- [Worker capsule](#worker-capsule)
- [Deltas instead of re-reports](#deltas-instead-of-re-reports)
- [Verify, escalate, or stop](#verify-escalate-or-stop)

## Optimization Contract

1. Treat the goal's quality, safety, and approval requirements as a hard floor.
2. After that floor, minimize cost by default.
3. Measure total tokens, context occupancy, and wall time separately. A cheaper
   route may use more of each.
4. Honor a different optimization target when the user states one.
5. Never set a token budget unless the user explicitly asks for one.

Use the cheapest route and model likely to pass a hard verifier. More cheap-model
work is acceptable when it lowers cost; gratuitous fan-out is not.

## Model and Effort Roles

Subagent model and effort are set per `Agent` call (`model`, `effort`) or in a
`.claude/agents/*.md` definition. Confirm the live roster with `/model` when the
choice matters, and preserve the capability roles below if names change.

| Work shape | Start with | Escalate when |
| --- | --- | --- |
| Extraction, inventory, formatting, deterministic classification | `haiku`, low–medium | inputs are ambiguous or synthesis matters |
| Bounded implementation with a hard verifier | `sonnet`, medium–high | the verifier exposes non-local reasoning gaps |
| Contained exploration or single-surface review | `sonnet`, medium | requirements conflict or failures cross boundaries |
| Ambiguous debugging, consequential independent review | `sonnet` high, then `opus` | two evidence-backed attempts make no measurable progress |
| Goal architecture, cross-cutting synthesis, integration decisions | `opus`, medium | risk or ambiguity remains high |
| Security, destructive boundaries, repeated failure | `opus`, high–xhigh | human approval or external state is required |

Omitting `model` inherits the session model, which is usually right — set it
only when a different tier clearly fits. Do not default to `max` effort; reserve
it for one indivisible hard decision.

The parent session's own model is the user's choice via `/model`; this skill
does not change it. If the parent lacks capability for one consequential
decision, spawn a single `opus` advisor with a compact packet and bring the
decision back, rather than transferring goal ownership.

## Route Admission

Select the lowest route whose conditions hold.

- **Light** — one coherent dependency path, one mutable owner, a credible
  verifier. Do not delegate execution. An independently selected assurance tier
  may still add bounded read-only review.
- **Medium** — a complete bounded execution packet can be handed to one `Agent`
  and doing so is cheaper than keeping the work in the parent. Stay Light when
  building the packet or reacquiring the result costs about as much as doing
  the work. One active child; hand off writing rather than sharing it.
- **Heavy** — at least two genuinely independent read-only lanes, each with its
  own evidence contract, and expected value above coordination cost. At most
  three active children.

For Heavy, fan out once and fan in before mutation. If Full assurance also
applies, run its review lanes after execution fan-in and deterministic checks;
never overlap two fan-outs. Keep one mutation owner.

**Parallel writers.** The one-writer rule exists to prevent conflicting edits to
shared state. Claude Code can lift it honestly: an `Agent` with
`isolation: worktree` gets its own git worktree branched from the default
branch, so several implementation lanes can write at once without touching the
main checkout. Use it for competing approaches or genuinely independent
subsystems, then integrate the winner in the parent. It costs setup time and
disk per agent, so do not reach for it when one writer suffices, and remember
the worktree branches from the default branch, not from the session's `HEAD`.

Send independent `Agent` calls in a single message so they run concurrently.
Prefer `Explore` for read-only discovery, `Plan` for design research, and
`general-purpose` when a lane must also modify files. Do not create nested agent
trees. Do not use the `Workflow` tool unless the user explicitly opted into
multi-agent orchestration.

## Worker Capsule

Give each worker only what it needs:

```text
Objective: one bounded result
Inputs: exact paths, sources, commands, and established facts
Non-goals: scope the worker must not expand
Ownership: read-only, or the exact mutable surface
Verifier: observable success check
Stop: failure, approval, and dependency boundaries
Return: outcome, strongest evidence, uncertainty, artifacts, next action
```

Subagents start with a fresh context, so state the grounded facts rather than
assuming shared history. Pass artifact paths, commands, and log locations
instead of pasted output. Default worker returns to roughly 250 words.

For bounded implementation, extend the capsule only as needed:

```text
Touchpoints: exact path, symbol, interface, or runtime surface when grounded
Order: dependency-sensitive steps; omit when order does not matter
Preserve: contracts, invariants, protected areas, compatibility constraints
Validation ladder: fastest diagnostic, focused checks, then the primary verifier
```

Do not invent precision. If locating touchpoints is the delegated objective, say
so and keep that lane read-only. The packet is execution-complete when the
writer can start safely without reconstructing your investigation.

Reuse an existing bounded worker for a closely related follow-up with
`SendMessage` — its context is intact, so a delta costs far less than a fresh
agent re-reading everything. Do not keep chatty peers alive.

## Deltas Instead of Re-Reports

For a related exploration follow-up, request a **discovery delta**:

```text
New evidence: facts and artifact pointers not already in the parent packet
Invalidated: assumptions or prior findings the evidence changes
Impact: decision, route, plan, or verifier consequence
Unknowns: only uncertainty that still affects the next action
```

When a delegated change fails verification, the read-only checker returns a
**repair delta**:

```text
Failure: exact check or reproduction and decisive output
Expected/observed: the smallest useful contrast
Boundary: evidence-backed location or hypothesis, labeled accurately
Preserve: passing behavior and invariants the repair must not disturb
Pass condition: exact focused check and primary verifier
```

Send that delta to the *same* mutation owner for one evidence-driven repair; the
checker never becomes a writer. Do not recruit a fresh executor merely because
verification failed. If the problem boundary changed or the repair moves the
verifier not at all, return to Research and Plan.

## Verify, Escalate, or Stop

1. Run deterministic checks through `UG verify` before qualitative model judgment.
2. On a local mechanical failure, improve the packet and retry the same cheap
   model once. On a failed delegated change, reuse the current mutation owner
   with a repair delta before considering a new executor.
3. Escalate one model or effort rung after two verifier failures without
   measurable progress, conflicting evidence, a changed dependency or public
   contract, missing required proof, or a security, destructive, external-write,
   or approval boundary.
4. Escalate the decision, not the whole workflow. Do not answer failure by
   spawning more peers.
5. Mark complete only from the parent's integrated evidence, through
   `UG complete`. Apply the blocker standard before marking blocked.

When evaluating a routing change, forward-test Light, Medium, and Heavy
scenarios with fresh minimal contexts and record outcome quality, route, model
and effort, agent count, verifier result, tokens, observed cost, and wall time.
Do not infer cost from token counts across models or cache states, and do not
adopt or reject a route from a single run.
