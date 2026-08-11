~~~markdown
## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This PR adds a regression test fixture for generated styles output (`styles.test.ts`). The visible diff is a single added line, so my review is scoped to that fixture and the stated contract for `styleLess`.

There's a P1 blocker: the new fixture assigns a `:root { ... } .el { margin: var(--sp); }` selector block to `styleLess`, but `styleLess` only accepts flat declarations, not selectors or `:root` blocks. That makes this an invalid input for the real export path, so the "regression test" doesn't exercise behavior the generator can actually encounter in production — it can't tell us whether real style export works or regresses.

I didn't find other issues in the visible diff, but the hunk has no surrounding assertions or file context, so I could only evaluate the fixture value itself.

## QA Spec

### Setup

1. Pull the branch and open `styles.test.ts`.

### Regression test fixture

- When the new test runs with a `styleLess` value containing a selector or `:root` block:
  - [ ] Confirm this is a shape the export API can actually produce for `styleLess`
  - [ ] Confirm the test's assertion reflects real generator behavior rather than just "does not throw"

### Regression smoke

Spend a few minutes around:
- Other style-export tests, to confirm they only feed `styleLess` flat declarations
~~~
