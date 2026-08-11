~~~markdown
## Review unavailable

I can't run a real review against this PR. The supplied diff for `styles.test.ts` is a fragment, not a usable patch: it has no `---`/`+++` file headers and no line numbers on the `@@` hunk, so it can't be located in or applied to a repository. There is also no repository, branch checkout, or PR platform connection available, so I can't read the current head revision, the rest of the test file, or the `styleLess` validation code needed to confirm the claim that only declarations are accepted there.

To review this, please provide one of:
- a complete unified diff (real file headers and hunk line numbers) plus the repository or relevant source files
- a link or checkout to the actual branch or PR so I can read current head state
- the `styleLess` parsing/validation source so the new test's fixture can be checked against it
~~~
