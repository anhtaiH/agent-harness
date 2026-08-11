~~~markdown
## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This PR's only change is a regression test for generated styles, asserting behavior for a `styleLess` fixture value. I focused on whether that fixture actually represents a valid `styleLess` input, since the test is the entire content of the change. There's one blocker: the fixture doesn't match the documented `styleLess` contract, which means the regression protection this PR is meant to add doesn't actually exist yet.

## QA Spec

### Setup

1. Check out this branch and run `styles.test.ts` locally.

### Generated styles export

- When the export runs against a `styleLess` value containing only declarations (the shape the real API accepts):
  - [ ] The generated output matches the expected exported styles
  - [ ] No selector or at-rule content (e.g. `:root { ... }`, `.el { ... }`) is present in what's asserted

### Regression smoke

Spend a few minutes around:
- Any other tests or call sites that pass `styleLess` end-to-end, to confirm they use declarations-only values consistent with the real contract

### Proposed inline comments

#### 1. `styles.test.ts:1`

[P1 · Change request]

Can we change this fixture to use only CSS declarations, since `styleLess` accepts declarations only and not selectors or `:root` blocks?

The added case sets `styleLess` to `':root { --sp: 8px; } .el { margin: var(--sp); }'`, which is a full ruleset with a `:root` selector and a nested `.el` selector rather than plain declarations. Since the real API never receives that shape in `styleLess`, this test exercises a code path that doesn't correspond to actual usage, so it can't verify the export behavior it's meant to guard.

I'd treat this as P1 because the PR's sole purpose is adding this regression test, and an invalid fixture means the regression coverage it's meant to add isn't real, with no other test in this change providing a fallback.

Suggested fix: use a declarations-only value, e.g. `styleLess: '--sp: 8px; margin: var(--sp);'`, and assert against the generated output the real API would produce for that input.
~~~
