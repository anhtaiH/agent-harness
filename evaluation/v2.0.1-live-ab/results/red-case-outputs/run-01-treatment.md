~~~markdown
## Review unavailable

This fixture gives only an id, title, description, and a short context note — not real repository or PR/branch access. The `diff` field is not a usable patch: it has no `---`/`+++` file headers, no hunk line numbers, and no surrounding file content, so no head revision, file path, or line location can be confirmed. The context note asserts what the actual API accepts, but that claim can't be checked against real source.

Without a resolvable target, I can't inspect callers, existing tests, or prior review state, and I won't guess at findings from an unverifiable fragment.

To review this for real, please provide one of:

- A PR or branch link with repository access, so the actual diff, head revision, and current review state can be read.
- A complete unified diff (proper file headers and hunk context) applied against a real base commit, plus repository access to check callers and tests.
- The actual source file(s) involved (for example the styleLess parser/validator and its tests), so the asserted behavior can be verified rather than assumed.
~~~
