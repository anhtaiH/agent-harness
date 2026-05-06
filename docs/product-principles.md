# Product Principles

Agent Harness is a developer product, not just a script bundle.

## Make The First Step Obvious

There should be one primary install command and one next prompt. Advanced backend commands are still available, but they should not be required for normal use.

## Preserve The User's Repo

Setup should avoid tracked repo edits. Runtime state, profiles, generated context, memory, metrics, and worktrees belong in the local runtime.

## Make Failure Actionable

Every setup failure should explain:

- what failed
- whether the runtime is partially usable
- how to retry
- what dependency or permission is missing

## Prefer Safe Defaults With Explicit Escape Hatches

Default mode is conservative. Yolo mode exists for high-autonomy local work. Connector writes are allowed when task-scoped. Secret and production hard stops stay in place.

## Optimize For Trust

Agents must distinguish what was checked, what was run, what was assumed, and what still needs human judgment. Evidence is a product feature, not an afterthought.
