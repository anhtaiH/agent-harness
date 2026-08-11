~~~markdown
## Review preview

### Proposed submission type

Request Changes

### Top-level review body

This PR adds one regression test in `styles.test.ts` that asserts on a generated `styleLess` value for exported styles. I reviewed the fixture against the real `styleLess` contract and checked whether the added assertion actually exercises the export path it's meant to guard.

[P1 · Change request] The fixture asserts on `':root { --sp: 8px; } .el { margin: var(--sp); }'`, but the real API only ever produces flat declarations in `styleLess` — never a `:root` block or a `.el` selector. I'd treat this as P1 because this test is the entire content of the PR, and a fixture shaped this way can't reflect real generated output, so the test doesn't actually guard against the export regression it's meant to catch. Can this be rebuilt around a valid `styleLess` value (declarations only, no selector wrapper), matching what the generator actually emits?

No other issues found in scope.

## QA Spec

### Setup

1. Run the styles export/generation path locally against a component with at least one custom property.

### Regression test validity

- When the generator emits a `styleLess` value:
  - [ ] Value contains flat declarations only, no selector or `:root` wrapper
  - [ ] Test fixture matches that shape exactly

### Regression smoke

Spend a few minutes around:
- other generated-style regression tests, to confirm none use the same invalid selector-wrapped shape
~~~
