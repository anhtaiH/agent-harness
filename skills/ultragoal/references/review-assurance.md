# Review Assurance

Load this reference only for Focused or Full assurance, assurance-policy
evaluation, or multi-reviewer synthesis. Compact goals stay on deterministic
checks plus your own outcome audit.

## Invariants

- Assurance is independent of Light, Medium, or Heavy execution.
- Run the strongest applicable deterministic verifier through `UG verify`
  *before* result-assurance model review. Any earlier model review is advisory
  and is never completion evidence.
- Keep one mutation owner; all assurance lanes are read-only.
- You stay goal owner, evidence integrator, and completion authority.
- Review does not add human-controlled phase transitions. Repair findings
  autonomously inside the goal contract.

## Select the Lowest Sufficient Tier

| Tier | Use when | Independent model review |
| --- | --- | --- |
| Compact | Reversible, low blast radius, strong deterministic proof, no meaningful contract or operational risk. | None. You audit outcome and scope. |
| Focused | One meaningful risk surface, cross-boundary uncertainty, or a verifier blind spot. | One targeted reviewer at the highest-leverage checkpoint. |
| Full | Multiple distinct risks, or a high-consequence security, privacy, migration, public-contract, destructive, rollout, or incident-prone boundary. | Up to three non-overlapping lanes across the whole goal. |

File count and task duration do not determine assurance. Reclassify only when
new evidence changes consequence, reversibility, verifier coverage, or
uncertainty.

`UG complete` enforces the tier: Focused needs one recorded lane, Full needs
two. Record each with

```bash
UG assurance --lane "security: authz on the new endpoint" --finding "no bypass found; 2 low-severity notes fixed"
```

## Lanes Available in Claude Code

Two bundled skills already are review lanes, and they run against the real diff:

- **`/code-review`** — correctness bugs plus reuse, simplification, and
  efficiency findings, at a chosen effort level. It can target a PR number,
  branch, or path, and `--comment` posts inline PR comments.
- **`/security-review`** — a security pass over the branch's pending changes.

Use them as the default Focused lane when the risk surface matches. For a risk
they do not cover, spawn a read-only `Agent` (`Explore`, or a
`.claude/agents/*.md` reviewer) with an isolated artifact packet. A custom
reviewer agent can preload a checklist skill via its `skills:` field, which
gives a consistent lane across goals.

Prefer a different model for a lane only when it is likely to reduce correlated
failure beyond what context isolation and role specificity already buy.

## Spend Review Where It Changes the Outcome

- **Advisory research review** — challenge source quality, stale assumptions,
  missing consumers, and unknowns before activation, when preventing a wrong
  plan justifies the cost.
- **Advisory goal or plan review** — challenge acceptance, invariants,
  recovery, scope, and verifier blind spots before mutation.
- **Result assurance** — after the strongest deterministic verifier, challenge
  the integrated artifact, deviations, regressions, and completion proof.

Only result assurance satisfies the selected tier. Focused reserves its one lane
for the result by default; when an early advisory pass has higher expected
value, reuse that same reviewer via `SendMessage` for one tightly related result
follow-up rather than adding a lane.

Full uses at most three distinct lanes across the goal, not a fresh fleet at
every phase. Pick lanes by risk and expected information gain, and run at least
one on the integrated result after deterministic proof.

If an independent lane is unavailable, an inline audit may support progress but
does not satisfy Focused or Full. Continue unblocked work and retry after a
capability or state change. Do not claim the tier, and do not lower it because
tools are unavailable — missing required independent assurance is missing
completion evidence.

## Isolate the Review Artifact

Give an adversarial reviewer only:

```text
Claim: outcome or decision being reviewed
Artifact: exact goal, spec, diff, result, or evidence paths
Risk question: one bounded failure mode to investigate
Constraints: verified requirements, approvals, and non-goals
Verifier: command or evidence and its current result
Return: findings with severity, confidence, evidence, impact, smallest remediation
```

Do not pass your private reasoning or the full conversation. A subagent starts
fresh by default, which is the isolation you want — do not undo it by pasting
context the reviewer should derive independently.

## Choose Distinct Lanes

- **Evidence auditor** — unsupported premises, contradictions, stale sources,
  unexamined dependencies.
- **Change-completeness reviewer** — what likely needed to change but did not:
  consumers, tests, docs, migrations, flags, monitoring, rollback, cleanup.
- **Risk specialist or skeptic** — attacks the highest-consequence domain
  invariant, or tries to falsify the claimed outcome.

Do not assign generic overlapping reviewers. One strong lane beats several
fuzzy ones.

## Synthesize for Precision

A finding must carry concrete evidence and distinguish severity from
confidence. A blocker demonstrates that acceptance, safety, permission, or
required proof fails; speculation alone never blocks.

As the parent:

1. Deduplicate findings and cluster them by risk surface.
2. Reproduce or check evidence when practical — re-run it through `UG verify`
   so the check is recorded, not just believed.
3. Resolve conflicts from evidence rather than vote count.
4. Drop unsupported or immaterial findings.
5. Separate required repairs from optional follow-up.

Fix evidence-backed issues inside the contract without asking. Return to Plan
when a fix changes scope, risk, verifier, or approval boundaries; ask only for a
consequential human decision.

## Completion Standard

Complete only when deterministic proof passes, the actual outcome matches the
goal, the required lanes have run on the result, and no evidence-backed blocker
remains. Reviewer agreement is neither necessary nor sufficient. Record the
tier, lanes used, strongest finding or clean result, repairs, and final evidence
compactly — `UG report` renders most of it for you.
