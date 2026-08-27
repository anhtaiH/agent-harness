# Policy, Verification, and Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make harness launches fail closed, bind external writes exactly, replace model verdicts with authenticated verifier evidence, and schedule 24 mixed-host lanes without duplicate writers or file-descriptor exhaustion.

**Architecture:** Normalize every host event into core policy types, keep launch manifests explicit and immutable, and make the task ledger an authenticated state machine. A resource-aware scheduler owns process creation and writer leases; host wrappers are thin translators.

**Tech Stack:** Python 3.10+ standard library, host hook JSON/RPC bridges, macOS
Keychain/protected local brokers, live compare-and-advance anchor, JSONL hash
chains, POSIX locks, Node-based MCP facade. File-backed authorities exist only
as non-qualifying test/development fixtures.

## Global Constraints

- Stable specification: `docs/superpowers/specs/2026-07-29-durable-cross-agent-harness.md`.
- Foundation plan must be complete and reviewed before this plan starts.
- Use TDD and observe each named negative path fail before implementation.
- Prefix every shell command with `rtk`.
- Reuse the Foundation-bound canonical `AGENT_HARNESS_PYTHON` unchanged,
  revalidate that exact path as Python 3.10 or newer at plan entry, and invoke
  it only as quoted `"$AGENT_HARNESS_PYTHON"`; never rediscover or substitute
  the ambient default interpreter.
- Required harness gates fail closed on crash, timeout, invalid output, or missing capability.
- Normal non-harness host defaults remain untouched.
- Preserve three non-substitutable authorities: Foundation's installation
  integrity key, a distinct non-exportable protected user-presence approval key,
  and a live compare-and-advance anti-rollback anchor. Agent-facing APIs expose
  no raw anchor CAS, raw key bytes, or generic signing oracle.
- Reuse the Foundation-provisioned native authority manifest and pinned broker/
  key identities. Policy tasks may add domain-specific verification but may not
  provision, replace, rebaseline, or silently recover an authority.
- Threat scope is harness-launched same-UID agents that may alter/replay
  ordinary harness files and invoke agent CLI/MCP but cannot access/inject the
  protected brokers or roll back the anchor. Do not claim protection from
  root/kernel, full-account, authority-process/trusted-UI, provider-account, or
  anchor-security-domain compromise. A MAC proves integrity, not approval or
  freshness.
- Mutable JSON, status snapshots, indexes, and intent files are projections
  only. Authenticated event chains plus live anchor equality are authority.
- No CLI/MCP/native agent surface accepts raw anchor old/new state. Every
  advance consumes one domain-issued `VerifiedAnchorTransition` bound to the
  exact authenticated WAL/event/check/record transition; correct-old/
  arbitrary-new, forged, replayed, or cross-domain requests deny.
- File-backed/replayable approval or anchor backends disable production
  external writes and release qualification; owner-only mode bits are not an
  isolation boundary.
- External intents are exact, current-task, digest-bound, single-use, and TTL-bound.
- External intent dispatch requires an atomic reservation with a persisted
  stable provider idempotency key; ambiguous outcomes are `uncertain` and block
  reissue until provider status/readback reconciliation.
- Every lease, mutable dispatch, resume, and handoff requires a freshly
  revalidated immutable `VerifiedWorktreeIdentity` bound to the parent
  enrollment and stable root/Git-dir/common-dir object IDs; matching paths,
  provenance, or shared Git common directory alone is insufficient.
- Task completion is recomputed from verifier specs and authenticated records; stored verdict text is not proof.
- Verifier starts, check/task/intent transitions, leases, handoffs, and
  qualification allocations are authenticated events committed against the
  live anchor before their external effect. Replaying every ordinary local file
  and stored anchor receipt must still fail against newer live state.
- Scheduler ceilings are total 24, Codex 8, Claude 8, Cursor 4, OMP 4; one writer per task.
- Retention defaults are indefinite active/blocked state, 365-day compact evidence/manifests, 30-day raw logs, and 90-day unpromoted repo memory.
- Each task ends in a local commit and independent task review; no push or PR.

---

### Task 1: Add explicit launch manifests and profiles

**Files:**
- Create: `src/harness_core/launch.py`
- Create: `runtime/schemas/launch-manifest.v1.schema.json`
- Create: `tests/unit/test_launch_profiles.py`
- Modify: `src/harness_core/credentials.py`
- Modify: `runtime/bin/ah-codex`
- Modify: `runtime/bin/ah-claude`
- Modify: `runtime/bin/ah-cursor`
- Modify: `runtime/bin/ah-omp`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: enrolled repository, freshly `VerifiedWorktreeIdentity`, task
  identity/current authenticated head and authorization epoch, adapter
  capabilities, and profile name.
- Produces: `build_launch_manifest` and `run_launch_manifest` for `read`, `worktree-write`, and `yolo`.

- [ ] **Step 1: Write failing profile tests**

Cover complete argv/env/cwd serialization, read-only mutation denial, worktree
containment, network default denial, yolo authorization requirement,
timeout/turn bounds, and resume replay of non-persisted fields. Add path-swap
and same-common-dir/different-worktree red cases at build, spawn, resume, and
mutable tool dispatch boundaries.

```python
manifest = build_launch_manifest(context, host="claude", profile="worktree-write")
self.assertEqual(manifest.cwd, str(context.task_worktree))
self.assertNotIn("ANTHROPIC_API_KEY", manifest.env)
self.assertTrue(manifest.sandbox.fail_closed)
```

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_launch_profiles -v`

Expected: FAIL because `harness_core.launch` does not exist.

- [ ] **Step 2: Define immutable launch contracts**

```python
@dataclass(frozen=True)
class LaunchManifest:
    schema_version: int
    task_id: str
    task_version: int
    authorization_epoch: int
    worktree_identity_digest: str
    host: Literal["codex", "claude", "cursor", "omp"]
    profile: Literal["read", "worktree-write", "yolo"]
    argv: tuple[str, ...]
    cwd: str
    env: Mapping[str, str]
    timeout_seconds: int
    max_turns: int
    resume_fields: Mapping[str, str]
```

Canonicalize and digest the manifest before launch. Environment construction is
allowlist-based and stores auth references rather than values in the serialized
manifest. Resolve only the credential-reference types produced by Foundation
Task 10; secret bytes are materialized into child environment or stdin at spawn
time and never enter the manifest, argv, or durable output.

- [ ] **Step 3: Encode host-specific profile mappings**

Codex selects the receipt-owned harness profile file and uses `--config` only
for task-specific overrides; Claude uses strict settings/MCP and fail-closed
sandbox; Cursor uses CLI mode, permission file, sandbox, and NDJSON; OMP uses an
explicit config overlay and RPC mode. Reject any required field unsupported by
the discovered host version.

- [ ] **Step 4: Make wrappers consume manifests**

Wrappers accept `--manifest PATH --expect-digest SHA256` and pass no unmodeled
user arguments. The facade builds manifests and records launch/start/exit
evidence. Re-run `verify_worktree_identity` immediately before spawn/resume and
before every mutable tool dispatch; require all root/Git-dir/common-dir
paths/object IDs and the nonce-bound marker when enabled. Retain the verified
root capability through spawn/dispatch and reject same-path replacement or a
different worktree even when repository provenance and common directory match.
Launch/start/exit records are authenticated task events and each
security-relevant manifest/profile change bumps the authorization epoch.

Run: `rtk npm test`

Expected: all four wrapper/profile tests pass and ordinary host configs remain unchanged.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/launch.py src/harness_core/credentials.py runtime/schemas/launch-manifest.v1.schema.json tests/unit/test_launch_profiles.py runtime/bin src/agent_harness.py
rtk git commit -m "feat: add explicit harness launch profiles"
```

### Task 2: Compose host hooks with fail-closed harness semantics

**Files:**
- Create: `src/harness_core/hooks.py`
- Create: `tests/unit/test_hook_composition.py`
- Modify: `runtime/hooks/pre-tool-policy.py`
- Modify: `runtime/hooks/cursor-bridge.py`
- Modify: `runtime/mcp/omp-extension.ts`
- Modify: `src/harness_core/adapters/claude.py`
- Modify: `src/harness_core/adapters/cursor.py`
- Modify: `src/harness_core/adapters/omp.py`

**Interfaces:**
- Consumes: adapter hook inventory plus ordered Harness, RTK, and Headroom hook declarations.
- Produces: `compose_hooks`, stable health probes, and normalized fail-closed results.

- [ ] **Step 1: Write failing hook failure tests**

Cover existing user hooks, ordering, deduplication, concurrent-hook semantics, timeout, missing executable, invalid JSON, exit 0, exit 2, unexpected nonzero, and each host bridge. Required harness launches must deny every infrastructure failure.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_hook_composition -v`

Expected: current bridges fail open and tests fail.

- [ ] **Step 2: Define hook identities and ordering**

```python
@dataclass(frozen=True)
class HookSpec:
    owner: Literal["agent-harness", "rtk", "headroom", "user"]
    event: str
    command: tuple[str, ...]
    matcher: str | None
    timeout_seconds: int
    required: bool
    order: int
```

Order required policy before observability, and observability before user notification. Deduplicate only exact owner/event/command identities; preserve unrelated user entries.

- [ ] **Step 3: Implement normalized failure behavior**

```python
def required_hook_result(result: HookProcessResult) -> PolicyResult:
    if result.timed_out:
        return PolicyResult.deny("hook-timeout")
    if result.exit_code not in (0, 2):
        return PolicyResult.deny("hook-infrastructure-error")
    if not result.valid_json:
        return PolicyResult.deny("hook-invalid-response")
    return result.policy_result
```

Host bridge serialization must preserve each host's native block protocol while mapping all internal failures to denial for harness launches.

- [ ] **Step 4: Add hook health to host reports**

Verification probes each installed command without mutation, checks versioned receipt paths and timeouts, and reports duplicate/unreachable hooks as strict doctor failures.

Run: `rtk npm test`

Expected: negative infrastructure cases deny and all adapter lifecycle tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/hooks.py tests/unit/test_hook_composition.py runtime/hooks runtime/mcp/omp-extension.ts src/harness_core/adapters
rtk git commit -m "feat: fail closed across composed host hooks"
```

### Task 3: Enforce exact external-write intents and readback

**Files:**
- Modify: `src/harness_core/authorities.py`
- Create: `src/harness_core/events.py`
- Create: `src/harness_core/intents.py`
- Create: `runtime/schemas/task-event.v1.schema.json`
- Create: `runtime/schemas/write-intent-approval.v1.schema.json`
- Create: `tests/unit/test_write_intents.py`
- Modify: `tests/unit/test_authorities.py`
- Modify: `runtime/hooks/pre-tool-policy.py`
- Modify: `src/agent_harness.py`
- Modify: `runtime/mcp/server.mjs`

**Interfaces:**
- Consumes: current authenticated/anchored task head, authorization epoch,
  verified worktree/launch identities, normalized provider operation,
  canonical target/precondition, proposed content bytes, clock, protected
  Foundation-provisioned pinned approval authority and live anchor broker.
- Produces: `create_intent_proposal`, protected `approve_intent`,
  `reserve_for_dispatch`, `record_provider_operation`, `mark_uncertain`, and
  `reconcile_intent_after_status_and_readback`.

- [ ] **Step 1: Write the full failing negative matrix**

Use a fixed clock. Cover expired, future-issued, wrong task, provider,
operation, target, canonicalization, content digest, status, already consumed,
missing active task, and multiple ambiguous matches. Add one positive match
followed by reservation, dispatch, and successful readback/consumption. Before
production changes, add red cases for concurrent double reservation,
dispatch without reservation/idempotency persistence, timeout after the
provider has committed, lost response after commit, conflicting readback,
duplicate reissue while `reserved` or `uncertain`, changed idempotency key on
retry, and reconciliation attempted without both provider status and canonical
readback.
Add authority/replay reds: editing a projection from proposed to approved;
approval replay across installation, key ID, task/version/authorization epoch,
predecessor event, worktree/launch digest, provider, operation, target,
precondition, content, key, or expiry; stale-predecessor append CAS; using the
installation MAC as approval; replacing the pinned approval key; MCP or
non-interactive `--confirm`; file-backed approval/anchor; unavailable/mismatched
anchor; stale permit; and restoring an old internally valid event/projection/
anchor-receipt set after the live task generation advances. Every case must
deny.
Add raw anchor CAS, forged/replayed/cross-domain transition capability, and
correct-current-generation/arbitrary-new task commitment; none may append an
event or advance the native anchor.
Also cover absent/incomplete authority bootstrap, native broker code-identity
drift, approval-key persistent-reference/public-key mismatch, silent key
recreation, rotation without old-and-new protected user presence, stale
approval after a valid rotation, and live-anchor namespace/receipt-key
replacement. All production cases fail before proposal approval or reservation;
the explicit file/fake backend remains unit-test-only and non-qualifying.

Crash after anchored reservation before the provider call and require
`uncertain`; crash after provider commit before response/operation-ID storage
and reconcile by the same key. Cover provider-not-committed with unchanged
precondition/readback (`retryable`) and with changed or conflicting
precondition/readback (`uncertain`). Duplicate callbacks/permit replay never
dispatch twice; TTL expiry blocks new reservation but still permits
reconciliation to consumed.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_write_intents -v`

Expected: current provider/substring matching fails the matrix.

- [ ] **Step 2: Define exact canonical matching**

```python
@dataclass(frozen=True)
class ProposedExternalWrite:
    installation_id: str
    intent_id: str
    task_id: str
    task_version: int
    authorization_epoch: int
    predecessor_event_hash: str
    worktree_identity_digest: str
    launch_manifest_digest: str
    provider: str
    operation: str
    target: str
    provider_precondition: str | None
    content_sha256: str
    created_at: datetime
    expires_at: datetime
    idempotency_key: str


@dataclass(frozen=True)
class VerifiedApprovalEvent:
    event_hash: str
    proposal: ProposedExternalWrite
    approval_key_id: str
    user_presence_signature: bytes
```

Provider canonicalizers must reject fragments, wildcard targets, embedded credentials, ambiguous repository aliases, and normalization that changes ownership scope.
The approval signature covers every proposal field plus the pinned approval-key
ID. `verify_approval` queries the protected broker and current live task anchor,
requires the approval event at the current authenticated predecessor/epoch, and
returns the non-serializable verified type. The projected intent additionally
shows reservation generation, attempt history, optional provider operation ID,
and status, but none of those mutable fields authorizes dispatch. Authoritative
events follow `proposed -> approved -> reserved -> consumed` or
`reserved -> uncertain -> consumed | retryable -> reserved`. The stable key is
derived once from the approved immutable identity and never regenerated.

- [ ] **Step 3: Make protected approval human-owned and predecessor-bound**

Load and verify the Foundation authority manifest, native broker code identity,
opaque persistent reference, and pinned approval public-key digest before every
approval. Never provision or replace a key from an intent path. CLI/MCP may
create only a proposal for the current authenticated task head, with exact
fields, TTL between 1 and 60 minutes, content from a file/supplied digest,
provider precondition, and stable key. Approval calls the distinct
non-exportable approval broker, displays the canonical provider/operation/
target/content/expiry summary, requires protected local user presence, signs
only the complete versioned envelope, and appends an authenticated approval
event by CAS only if the predecessor task head/version/authorization epoch
remains current. A plain flag, redirected stdin, ordinary file,
installation-integrity MAC, generic signing method, agent-facing MCP method, or
noninteractive session cannot approve.

Expose a separate protected local `authority rotate-approval` lifecycle. It
requires verified user-presence signatures from both the currently pinned and
candidate keys, readback of the candidate public-key digest/code identity, an
authenticated authority event, and an authorization-epoch advance for every
affected task before the new key becomes current. Lost/unavailable keys block
external writes and normal rotation. There is no in-place reprovision command.
If the live anchor, integrity/control key, broker receipt key, and helper remain
healthy, strict doctor returns the exact protected local remediation:
receipt-complete uninstall through `UNINSTALLED_PUBLISHED`, typed authority
retirement, then a new setup/authority/qualification era. The retirement path
uses OS local user presence plus the surviving domain authorities; it does not
pretend the missing approval key signed. If those retirement authorities are
also unavailable, report offline disaster restoration as non-qualifying rather
than minting a replacement. Test lost-key rotate/approve/recover denial, the
complete uninstall/new-era path, epoch invalidation, and rejection of every old
approval after reinstall. Both the healthy-retirement and offline-disaster
paths remain non-qualifying until the new era allocates and passes three
consecutive complete matrices; no old attempt or approval may contribute.

- [ ] **Step 4: Reserve before dispatch and reconcile ambiguous outcomes**

Under the task/intent lock, `reserve_for_dispatch` verifies the protected
approval event is in the current anchored task chain, rechecks task/version/
epoch/worktree/launch/predecessor/expiry and every canonical provider field,
allocates the exact attempt, appends a reservation event, and
issues/consumes the intent-domain `VerifiedAnchorTransition` bound to that
event/WAL and exact old/new task commitment before returning a one-use dispatch
permit. The stable idempotency key is already part of approval and is never
rederived. Projection write follows the authoritative event/anchor transition.
Connectors cannot dispatch without that generation-bound permit and pass the
same key to the provider. Duplicate reservation races yield one permit. A crash
after the anchored reservation but before provable provider dispatch recovers
to `uncertain`, never silently retryable. Persist a returned provider operation
ID in an anchored event before reporting success.

The connector/action adapter supplies provider operation status plus canonical
readback target and digest. Matching committed status/readback atomically
changes `reserved` to `consumed`. A timeout, lost response, status/readback
conflict, or inability to prove non-commit changes it to `uncertain`.
`reserved` and `uncertain` deny reissue. Reconciliation queries provider status
by the exact key and canonical readback before appending/anchoring `consumed` or
`retryable`; a retry must reuse the same approval/key and reserve again.
Authoritative "not committed" plus unchanged precondition/readback may become
retryable. Missing authoritative key lookup, changed/conflicting
precondition/readback, or an unsupported provider remains uncertain for human
resolution. Expiry prevents a new reservation but not reconciliation of an
existing attempt. Never infer retryability merely from a timeout or exception
and never claim distributed exactly-once behavior.

- [ ] **Step 5: Route policy hooks to the core matcher**

Remove substring/provider-only authorization from `pre-tool-policy.py`. Only
the verified, unconsumed, current-anchor dispatch permit authorizes the
connector call; projected `intent.json` status never does. Missing runtime,
approval/anchor backend, file-backed authority, stale/mismatched anchor,
authorization-epoch/head drift, state parse error, matcher exception, duplicate
dispatch, expired approval, or uncertain state returns a stable denial.

Run: `rtk npm test`

Expected: all intent negatives deny; timeout-after-provider-commit becomes
`uncertain`; duplicate reissue is blocked; reconciled status/readback consumes
or permits same-key retry; and gate verification remains green.

- [ ] **Step 6: Commit**

```bash
rtk git add src/harness_core/authorities.py src/harness_core/events.py \
  src/harness_core/intents.py runtime/schemas/task-event.v1.schema.json \
  runtime/schemas/write-intent-approval.v1.schema.json \
  tests/unit/test_authorities.py tests/unit/test_write_intents.py \
  runtime/hooks/pre-tool-policy.py src/agent_harness.py runtime/mcp/server.mjs
rtk git commit -m "feat: bind external write intents exactly"
```

### Task 4: Add deterministic verifier specifications

**Files:**
- Create: `src/harness_core/verifiers.py`
- Modify: `src/harness_core/events.py`
- Modify: `src/harness_core/authorities.py`
- Create: `tests/unit/test_verifiers.py`
- Create: `runtime/schemas/real-surface-verifier.v1.schema.json`
- Modify: `src/agent_harness.py`
- Modify: `runtime/mcp/server.mjs`

**Interfaces:**
- Consumes: current anchored task/version, a versioned command/artifact/
  real-surface verifier spec, and `VerifiedVerifierAttempt`.
- Produces: anchored `allocate_verifier_attempt`, `run_verifier` and immutable
  `VerifierResult` with output/artifact digests.

- [ ] **Step 1: Write failing verifier tests**

Cover argv execution without shell, timeout/process-group termination, expected exit codes, stdout/stderr digest and bounded tail, artifact exists/hash/JSON predicate, real-surface pending evidence, spec digest changes, and refusal of shell strings.
Prove no verifier process starts before an authenticated
`verifier-attempt-started` event and its verifier-domain
`VerifiedAnchorTransition` advance the live task anchor. Kill after that
advance and require the pending attempt to block completion; fabricated,
replayed, wrong-task/version/spec, or already-terminal attempt capabilities must
not launch.
At the verifier-domain issuer itself, cover raw namespace/old/new input,
forged, replayed, expired, or cross-domain capabilities, a correct current old
commitment paired with an arbitrary new commitment, missing or changed
attempt-event/WAL/spec digests, wrong task/version/code identity, and reuse
after advance. Every case must fail before appending an attempt event, advancing
the anchor, or starting a process; generic broker tests do not substitute for
this issuer matrix.

```python
with self.assertRaisesRegex(VerifierError, "argv must be an array"):
    run_verifier({"kind": "command", "command": "npm test"}, context)
```

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_verifiers -v`

Expected: FAIL because verifier specs are absent.

- [ ] **Step 2: Implement typed verifier specs**

```python
@dataclass(frozen=True)
class CommandVerifier:
    argv: tuple[str, ...]
    cwd: str
    timeout_seconds: int
    expected_exit_codes: tuple[int, ...] = (0,)

@dataclass(frozen=True)
class ArtifactVerifier:
    path: str
    expected_sha256: str | None
    json_pointer: str | None
    expected_value: object | None
```

Real-surface specs include host, build/version, starting state, steps, pass criteria, negative path, evidence paths, and clean-restart requirement. They cannot auto-pass without the declared surface evidence.
`allocate_verifier_attempt` derives the exact new anchor commitment only from
the authenticated canonical attempt event/WAL/spec tuple and is the sole
verifier-domain issuer. It never accepts a caller commitment or a prebuilt
transition.
`run_verifier` accepts only the non-serializable attempt capability returned by
the anchored allocation. Its terminal result appends an authenticated event
closing that exact attempt; missing terminal state remains pending.

- [ ] **Step 3: Replace synthetic QA checks**

Remove the code path that converts parsed `QA: PASS` into return code zero. Orchestration requires a verifier spec for yellow/red tasks. Model markers remain annotations only.

- [ ] **Step 4: Add CLI/MCP commands**

Support `verifier register`, `verifier list`, `verifier run`, and `verifier status`. Registration increments task version and invalidates older check freshness.
Registration also advances authorization epoch and the anchored verifier-set
digest so earlier approvals, attempt capabilities, and completion projections
become stale.

Run: `rtk npm test`

Expected: a deliberate agent `QA: PASS` with failing verifier cannot satisfy strict evidence.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/verifiers.py src/harness_core/events.py \
  src/harness_core/authorities.py tests/unit/test_verifiers.py \
  runtime/schemas/real-surface-verifier.v1.schema.json \
  src/agent_harness.py runtime/mcp/server.mjs tests/run.sh
rtk git commit -m "feat: verify tasks with declared executable specs"
```

### Task 5: Extend foundation authentication and hash-chain check records

**Files:**
- Modify: `src/harness_core/auth.py`
- Modify: `src/harness_core/authorities.py`
- Modify: `src/harness_core/events.py`
- Create: `src/harness_core/checks.py`
- Create: `tests/unit/test_check_chain.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: `VerifierResult`, exact verifier attempt, current authenticated task
  head/version/authorization epoch, integrity-authority reference, previous
  check/event hashes, Foundation check-tail contract, and live task anchor.
- Produces: append-only `checks.jsonl`, crash-safe `check-append.wal`,
  authenticated task-event append, separately MAC-authenticated
  `check-tail.json`, live anchor receipts, `append_check_record`, and
  `verify_check_chain`, plus check/task-domain `VerifiedAnchorTransition`
  issuance for exact prepared WAL transitions.

- [ ] **Step 1: Write failing tamper tests**

Cover edited result, removed middle line, reordered lines, duplicated sequence,
wrong prior hash, wrong task/version, changed verifier digest, wrong MAC,
truncated final line, and concurrent appends. Before production changes, add
complete-tail deletion, a valid but stale tail checkpoint, checkpoint ahead of
the log, checkpoint/task-state disagreement, crash after prepared WAL fsync,
crash after JSONL fsync, crash after checkpoint replacement, replay of a WAL
for a different old/new tail, and corrupted prepared record cases. Each
mutation must be detected or recovered only to the exact prepared state.
Also crash after task-event append, after live anchor compare-and-advance, and
before WAL commit. Save a complete valid old check log, task-event chain,
check/task projections, WALs, and stored anchor receipt; advance the live task
anchor; restore every saved file. Completion must still fail. Missing,
unavailable, file-backed/replayable, mismatched, rolled-back, or conflicting
anchor state and a pending anchored verifier/dispatch attempt all fail closed.
Add forged/replayed/cross-domain anchor transitions and a correct-old/
arbitrary-new check/task commitment; the broker must remain unchanged.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_check_chain -v`

Expected: current editable JSONL/stored Boolean logic fails.

- [ ] **Step 2: Reuse the installation signing key reference**

Load the installation signing-key reference created before the first Foundation
receipt. Do not rotate or replace it implicitly. A missing or
wrong-installation key is a strict failure. Store only its opaque key ID/
service/account reference in the manifest and call the narrow
`IntegrityAuthority`; check/task code cannot obtain bytes or request arbitrary
MACs. The approval key remains separate and cannot authenticate check records.
An owner-only file integrity fallback is a strict-doctor/release-qualification
failure in production, not a warning or same-UID isolation claim.

Never pass the key on argv or include it in logs/errors.

- [ ] **Step 3: Define chained records**

```python
def build_check_record(sequence: int, prior_hash: str,
                       payload: Mapping[str, object],
                       authority: IntegrityAuthority) -> dict[str, object]:
    unsigned = {"sequence": sequence, "prior_hash": prior_hash, **payload}
    record_hash = sha256(canonical_json_bytes(unsigned)).hexdigest()
    mac = authority.mac_check_record(unsigned)
    return {**unsigned, "record_hash": record_hash, "mac": mac}
```

The separately MAC-authenticated `check-tail` document contains task ID/version,
expected sequence/hash, and checkpoint generation. The live task commitment
covers installation ID, task ID/version/authorization epoch, task-event
sequence/hash, check sequence/hash, current verifier-set digest, and all pending
verifier/dispatch attempt IDs. Under one interprocess lock:

1. query and verify the live anchor, full check/event chains, checkpoints, and
   old local commitment agree;
2. write/fsync `check-append.wal` and its directory with exact old/new live
   commitments, tails, attempt ID, and complete record/event digests;
3. append, flush, fsync, reopen, and verify the exact JSONL check record;
4. atomically replace/fsync `check-tail.json` and its directory;
5. append/fsync the authenticated terminal verifier/task event and derived
   snapshot/checkpoint;
6. issue and consume the check/task-domain `VerifiedAnchorTransition` bound to
   the exact WAL, records, events, and old/new commitment, persist the broker
   receipt, then mark the WAL committed.

Recovery completes only this exact state transition and fails closed on a
conflict. Before an anchor advance it may finish only the prepared local
transition and CAS; after an advance it may finish only the matching local
projection/WAL commit. It never truncates a valid record, rolls back the live
anchor, or trusts the longest surviving file.

- [ ] **Step 4: Recompute strict evidence**

`strict_evidence_failures` validates the full chain and current verifier/task
digests and queries the live task anchor. Completion additionally requires exact
equality among live generation/commitment, actual task/check chain tails,
separately MAC-authenticated checkpoints, derived task snapshot, current
verifier set, and absence of pending attempts. Complete suffix deletion, stale
checkpoint, or replay of every local valid file therefore blocks completion.
Ignore stored `passed` unless authenticated records, live equality, current
artifact readback, and exact terminal attempt closure all validate. Return
stable findings for unavailable/file-backed authority or anchor, anchor
mismatch/rollback, pending anchored operation, chain/checkpoint gaps, stale
authorization epoch, and projection disagreement.

Run: `rtk npm test`

Expected: every tamper fixture blocks evidence doctor and normal verifier records pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/auth.py src/harness_core/authorities.py \
  src/harness_core/events.py src/harness_core/checks.py \
  tests/unit/test_check_chain.py src/agent_harness.py tests/run.sh
rtk git commit -m "feat: authenticate verifier check chains"
```

### Task 6: Make task state transitions atomic and resumable

**Files:**
- Create: `src/harness_core/tasks.py`
- Modify: `src/harness_core/events.py`
- Create: `tests/unit/test_task_state.py`
- Modify: `src/agent_harness.py`
- Modify: `runtime/hooks/stop-requires-evidence.py`

**Interfaces:**
- Consumes: enrollment, immutable `VerifiedWorktreeIdentity`, task packet,
  authenticated event/check state, live task anchor, writer lease, and
  host-session references.
- Produces: anchored compare-and-swap `transition_task`, derived task/index
  projections, task-domain `VerifiedAnchorTransition` issuance, and cross-host
  `handoff_task`.

- [ ] **Step 1: Write failing state-machine tests**

Cover allowed transitions, stale expected version, concurrent starts, duplicate
IDs, crash between state and active index, repair from journal, host handoff,
session reference redaction, stop gate with multiple tasks, and finish refusal
when checks are stale. Add red cases for path swap and substitution by another
worktree sharing the common directory immediately before resume and handoff,
plus actual/checkpoint/task-state check-tail inequality at completion.
Edit/replay task snapshots and `active-tasks.json`, restore a complete old
authenticated task/check/event/projection set after live anchor advance, kill
after an anchored transition but before projection replacement, and replay an
old handoff/launch approval after authorization-epoch bump. Derived projections
must repair forward from authoritative events/anchor and never authorize or
roll the task back.
At the task-domain issuer, add the full raw namespace/old/new, forged, replayed,
expired, cross-domain, correct-old/arbitrary-new, changed event/WAL/check-tail,
wrong task/version/epoch/code-identity, and reuse-after-advance matrix. Each
case must leave both the event chain and live anchor unchanged; a validly
authenticated transition whose new commitment was not derived from the exact
canonical task event is denied.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_task_state -v`

Expected: FAIL because atomic task state does not exist.

- [ ] **Step 2: Define the state machine**

Allowed states are `planned -> active -> verifying -> complete` with
`active/verifying -> blocked`, `blocked -> active`, and any non-complete state
to `abandoned`. Each transition requires expected task version, authorization
epoch, predecessor event/check heads, and live anchor generation. It writes an
authenticated WAL, appends/fsyncs the event, issues/consumes the task-domain
`VerifiedAnchorTransition` bound to that exact event/WAL and old/new state, and
only then repairs the task snapshot and active index as derived
caches. A conflict fails; no path selects a longest chain or trusts snapshot
state. Security-relevant identity, verifier-set, launch/profile, handoff,
approval-key, or permission changes increment authorization epoch and invalidate
older approvals, permits, leases, attempts, and manifests.
The task-domain issuer computes the new commitment from the canonical event and
WAL under the task lock; it accepts neither a caller-selected commitment nor a
prebuilt transition.

- [ ] **Step 3: Implement handoff without ownership drift**

A handoff stores source host/session reference, target host, task/version,
authorization epoch, complete worktree identity digest and
root/Git-dir/common-dir object IDs, source and target launch-manifest digests,
and latest event/check sequence/hashes. Revalidate every identity field through
retained descriptor capability immediately before handoff and target
acknowledgement. Append/anchor request and acknowledgement events; the handoff
itself advances authorization epoch so stale surface approvals cannot resume.
Matching only path/provenance/common directory is insufficient. Release no
writer lease until the target acknowledges the same anchored version/identity,
and require a new lease before either surface writes.

- [ ] **Step 4: Route start/resume/finish and stop hooks through core state**

Remove unlocked read-modify-write of `active-tasks.json`. Resume revalidates the
complete worktree object identity before session use. Finish queries the live
anchor and requires actual event/check tails, MAC-authenticated checkpoints,
derived task state, verifier set, authorization epoch, and pending-attempt set
to agree. Stop hooks verify canonical authenticated events plus live state;
snapshots/indexes are consistency-checked projections only and disagreement,
anchor unavailability, or pending intent/verifier/lease events fails closed.

Run: `rtk npm test`

Expected: concurrent starts serialize, crash repair restores the index, and stale checks cannot finish.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/tasks.py src/harness_core/events.py \
  tests/unit/test_task_state.py src/agent_harness.py \
  runtime/hooks/stop-requires-evidence.py tests/run.sh
rtk git commit -m "feat: make task transitions durable and resumable"
```

### Task 7: Enforce repository-scoped memory retention

**Files:**
- Create: `src/harness_core/retention.py`
- Modify: `src/harness_core/finalization.py`
- Modify: `src/harness_core/events.py`
- Create: `tests/unit/test_retention.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: enrolled repository identity, memory candidate metadata, retention policy, and current clock.
- Produces: `plan_retention`, `verify_retention_plan(...) ->
  VerifiedFinalizationPlan`, `apply_retention(VerifiedFinalizationPlan)`, and
  explicit `promote_memory`.

- [ ] **Step 1: Write failing retention tests**

Use a fixed clock to cover indefinite active/blocked state, 365-day compact evidence/manifests, 30-day raw logs, 90-day unpromoted candidates, promoted claims, dry-run, path escape, symlink escape, and cross-repository promotion refusal.
Add raw-plan apply, changed-object identity, changed retention clock/policy,
stale lifecycle/anchor, still-referenced recovery/qualification data, crash
during each finalizer, and caller-selected path cases. Preserve authenticated
anchored tombstones for all verifier/qualification failures, incompletes,
crashes, and cancellations; compaction cannot improve a streak.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_retention -v`

Expected: FAIL because retention planning does not exist.

- [ ] **Step 2: Implement safe retention planning**

Each candidate carries repository enrollment ID, created/last-used timestamps,
source event/check hashes, status, content digest, receipt ownership, trusted
root, and stable object identity. Planning is read-only and returns raw
inventory. Verification reopens candidates descriptor-relative, checks
containment/object identity/reference liveness, retention cutoff, lifecycle
generation and live anchor, and returns Foundation's phase-specific
`VerifiedFinalizationPlan`. Finalizers WAL each exact forward-only removal or
compaction and readback/fsync progress; they never accept caller paths.

- [ ] **Step 3: Require human-only promotion**

CLI promotion requires `--confirm` and current repository enrollment. MCP can list/query/candidate but cannot promote. Promotion never copies a claim to a different repository.
Promotion is an authenticated task/repository event approved through the
protected local interactive path; a flag alone or projection edit is not
authority.

- [ ] **Step 4: Route clean/memory commands through retention plans**

`clean` defaults to dry-run and prints retention class plus redacted exact
target identity. Apply reparses, fully verifies current state, and consumes only
`VerifiedFinalizationPlan`; a digest-bound raw plan is insufficient.

Run: `rtk npm test`

Expected: clock boundaries and path escapes pass; existing memory queries remain compatible.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/retention.py src/harness_core/finalization.py \
  src/harness_core/events.py tests/unit/test_retention.py \
  src/agent_harness.py tests/run.sh
rtk git commit -m "feat: enforce repository memory retention"
```

### Task 8: Add the 24-lane resource-aware scheduler and writer leases

**Files:**
- Create: `src/harness_core/scheduler.py`
- Create: `src/harness_core/leases.py`
- Modify: `src/harness_core/events.py`
- Create: `tests/unit/test_scheduler.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: launch manifests, host ceilings, process limits, task
  writer/read mode, current authenticated/anchored task head, immutable
  `VerifiedWorktreeIdentity`, and retry policy.
- Produces: `Scheduler.run`, `WriterLease`, lease-domain
  `VerifiedAnchorTransition` issuance, scheduler report, and recoverable crash
  events.

- [ ] **Step 1: Write failing deterministic scheduler tests**

Use fake processes and a fake clock to prove total and per-host ceilings, fair
queues, one writer/task, concurrent readers, transient `EMFILE` backoff,
permanent spawn failure, process crash, cancellation, stale lease recovery,
ledger completeness, and no duplicate result delivery. Add path-swap and
same-common-dir/different-worktree red cases immediately before lease acquire,
renew, stale recovery, and writer dispatch.
For acquire, renew, close, and stale-owner replacement issuers, add raw
namespace/old/new, forged, replayed, expired, cross-domain,
correct-old/arbitrary-new, changed lease-event/WAL/process/worktree identity,
wrong task/version/epoch/code identity, and reuse-after-advance cases. Each
must fail before appending a lease event, advancing the anchor, or dispatching a
writer.

```python
report = scheduler.run(make_jobs(codex=8, claude=8, cursor=4, omp=4))
self.assertEqual(report.max_total, 24)
self.assertEqual(report.duplicate_writers, [])
self.assertEqual(report.lost_jobs, [])
```

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_scheduler -v`

Expected: FAIL because scheduler/leases do not exist.

- [ ] **Step 2: Implement lease identity and recovery**

A writer lease stores task ID, random owner token, PID, process start identity,
task version/authorization epoch/event head/anchor generation, the complete
worktree identity digest and root/Git-dir/common-dir object IDs, acquired time,
heartbeat, and expiry. Acquire under `fcntl.flock` with a create-exclusive
projection only after freshly revalidating the descriptor-bound worktree and
current live task anchor, then append/anchor the authoritative lease-acquired
event through a lease-domain `VerifiedAnchorTransition` before writer dispatch.
Renewal repeats identity/anchor validation and consumes a transition bound to
the renewal event. Recovery requires stale heartbeat, proof the recorded process
identity is gone, another complete identity validation, and a verified
transition that closes the old owner and allocates the new one.
Editing/replaying the lease projection cannot create ownership.
Every lease-domain transition is issued only inside the corresponding locked
event transaction; its new commitment is derived from the exact canonical
event/WAL/owner identity, never accepted from a caller.

- [ ] **Step 3: Implement resource admission**

Reserve at least 16 descriptors for the controller and a measured descriptor budget per child. Refuse admission when `RLIMIT_NOFILE - open_fd_count` cannot cover the reservation. On `EMFILE`, close partial pipes, record the attempt, and retry with bounded exponential backoff and jitter; never drop or silently mark a job complete.

- [ ] **Step 4: Integrate orchestration**

Replace ad-hoc thread spawning with scheduler submission. Read-only roles may
run to ceilings; writers require a lease. Immediately revalidate the worktree
identity again before each writer job or mutable operation is dispatched.
Query the live task anchor and require the current authenticated lease event
before each dispatch. Persist and anchor queued/running/retry/succeeded/failed
events before reporting status; stale epoch/head/anchor or projection-only lease
always denies.

- [ ] **Step 5: Add real 24-process stress fixture**

The integration test starts 24 harmless local child processes across the four host labels, forces at least one retry through an injected low admission budget, and asserts 24 terminal results, one writer at a time, no `EMFILE` escape, no lost ledger lines, and clean shutdown.

Run:

```bash
rtk npm test
rtk npm run preflight
```

Expected: unit concurrency matrix, real stress fixture, and full preflight pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/harness_core/scheduler.py src/harness_core/leases.py \
  src/harness_core/events.py tests/unit/test_scheduler.py \
  src/agent_harness.py tests/run.sh
rtk git commit -m "feat: schedule 24 agent lanes safely"
```
