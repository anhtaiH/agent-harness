# Release Gate and Live Host Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce strict host reports, executable live-agent and rollback matrices, accurate documentation, and a source release gate that selects one reproducible commit for machine installation.

**Architecture:** Source-level verification remains deterministic and fixture-driven, while live verification is represented as versioned workflows that run against disposable enrolled repositories and real installed hosts. Every live run emits redacted machine-readable evidence; Cursor IDE evidence is gathered on the native app surface rather than inferred from CLI behavior.

**Tech Stack:** Python 3.10+ standard library, JSON reports, Git disposable
repositories/worktrees, Codex/Claude/Cursor/OMP CLIs, Cursor IDE Computer Use,
exact Node 22.23.2 plus the installed supported Node, and Bash preflight.

## Global Constraints

- Stable specification: `docs/superpowers/specs/2026-07-29-durable-cross-agent-harness.md`.
- Foundation and policy/scheduler plans must be complete and reviewed first.
- Use TDD for every source behavior and run the named negative path before implementation.
- Prefix every shell command with `rtk`.
- Reuse the Foundation-bound canonical `AGENT_HARNESS_PYTHON` unchanged,
  revalidate that exact path as Python 3.10 or newer at plan entry, and invoke
  it only as quoted `"$AGENT_HARNESS_PYTHON"`; never rediscover or substitute
  the ambient default interpreter. The execution ledger must prove this binding
  occurred before Foundation Task 1's first npm/test/preflight command.
- Live tests use disposable, explicitly enrolled repositories and bounded prompts.
- Required live surfaces are Codex CLI, Claude Code CLI, Cursor Agent CLI, OMP, and Cursor IDE.
- A complete matrix contains allow, deny, isolated write, verifier repair,
  resume/handoff, unallowlisted-network denial, unapproved-provider-write
  denial, and both ambiguous-write reconciliation branches for every supported
  surface. Network/provider cases use verifier-owned loopback fixtures with
  production write adapters and credentials absent.
- Qualification allocates and live-anchors every monotonic attempt before any
  host launch. The last three allocated ordinals—not the newest three successful
  files—must all be terminal passes under one identical full qualification
  tuple; failures, incompletes, cancellations, and crashes remain anchored
  tombstones and break the streak. One 24-lane mixed-host stress run is also
  required.
- Real uninstall/restore/reinstall is required; uninstall derives the complete
  receipt set only from the verified installation index, quiesces launchers,
  loads sealed recovery state, restores/verifies credential configuration,
  executes/verifies operational Keychain inverses, restores remaining
  filesystem state, atomically detaches runtime into a tombstone, and purges
  only through typed verified finalizers. Restore compares hashes, modes,
  applicable uid/gid, symlink targets/ownership, ACLs, and xattrs.
- Terminal retirement retains one protected non-replayable, non-authority pin
  containing the terminal-attestation/key/helper/retired-era digests. Reinstall
  creates a new qualification era, and its last three newly allocated attempts
  must all pass a complete matrix before qualification or cleanup; old attempts
  never contribute.
- Every live lease, write, resume, and handoff revalidates the immutable
  worktree identity bound to its parent enrollment, including stable
  root/Git-dir/common-dir object IDs and any enabled nonce marker.
- Applicable uid/gid restoration/readback may not be skipped in a qualifying
  run. The host must execute it or the attempt is non-qualifying; a capability
  is inapplicable only when the target/platform contract genuinely has no such
  metadata.
- Redaction occurs before persistence and is verified by a second leak scan.
- Strict doctor requires `ok: true` and `warnings: []`.
- Qualification requires the Foundation-provisioned native macOS authority
  broker, unchanged receipt-owned code identity/digest, pinned non-exportable
  approval key with protected user presence, and live Keychain-backed anchor;
  file/mock/generic-command authority backends cannot qualify.
- Every qualifying anchor advance consumes a domain-issued
  `VerifiedAnchorTransition`; no agent-facing raw old/new compare-and-advance
  surface exists.
- Each task ends in a local commit and independent task review; the entire branch receives a final review.

---

### Task 1: Produce strict host and installation reports

**Files:**
- Create: `src/harness_core/doctor.py`
- Create: `tests/unit/test_doctor.py`
- Modify: `src/agent_harness.py`
- Modify: `runtime/mcp/server.mjs`

**Interfaces:**
- Consumes: workspace manifest, MAC-verified installation index and complete
  verified receipt set, transactions, enrollments/worktree identities, adapter
  reports, check-tail checkpoints, launch profiles, signing key reference, and
  approval/state authorities, live installation/task/qualification anchors,
  authority bootstrap/manifest and native broker identity, qualification
  ledger/tail, safe-filesystem capabilities, and resource limits.
- Produces: `collect_doctor_report`, `strict_doctor`, and `where --json` source/host readback.

- [ ] **Step 1: Write failing strict-doctor tests**

Table-drive every failure and warning: newer schema, wrong owner/mode/uid/gid,
source commit/content mismatch, missing rollback object, unfinished
transaction, installation-index MAC/count/bijection failure, missing/duplicate/
foreign/unchecked/unexpected-or-omitted receipt, receipt MAC mismatch,
adapter version drift, auth unavailable, required hook unreachable, collision,
stale enrollment or worktree identity, check-chain/checkpoint/task-tail
inequality, missing profile capability, low descriptor limit, fallback signing
key, and warning promotion in strict mode.
Add stable findings for unavailable/file-backed approval authority,
unavailable/file-backed/non-rollback-resistant anchor, live-anchor mismatch or
rollback, pending anchored verifier/intent/qualification/install operation,
event/check/attempt ledger gap, projection disagreement, unsafe descriptor-
relative/no-clobber/CAS primitive, bootstrap/publication/uninstall recovery
state, and applicable-but-unverified uid/gid restoration.
Also fail for incomplete/replayed authority bootstrap, foreign/replaced
Keychain locators, native broker content/code-identity drift, unpinned or
recreated approval key, missing protected-user-presence capability, anchor
namespace/receipt-key replacement, incomplete rotation, or authority manifest
disagreement. A missing approval key must deny in-place reprovision and report
verified uninstall/authority retirement plus new setup as remediation when the
remaining retirement authorities are healthy; otherwise it reports
non-qualifying offline disaster restoration. Both paths remain non-qualifying
after setup until three newly allocated complete matrices pass under the new
installation/authority tuple. A file/mock backend cannot be downgraded to a
warning.

```python
report = collect_doctor_report(context_with(warnings=[warning("fallback-key")]))
self.assertTrue(report.ok)
self.assertFalse(strict_doctor(report).ok)
```

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_doctor -v`

Expected: FAIL because the aggregate doctor is absent.

- [ ] **Step 2: Implement stable findings and report schema**

```python
@dataclass(frozen=True)
class Finding:
    code: str
    severity: Literal["failure", "warning"]
    component: str
    message: str
    remediation: str

@dataclass(frozen=True)
class DoctorReport:
    ok: bool
    strict: bool
    source_commit: str
    installation_id: str
    failures: tuple[Finding, ...]
    warnings: tuple[Finding, ...]
    hosts: Mapping[str, HostReport]
```

Sort findings by component/code. Never include environment values, auth tokens, config contents, or command output beyond redacted version/health fields.

- [ ] **Step 3: Integrate doctor/where/MCP**

`doctor --strict --json` returns nonzero for a failure or warning. `where
--json` reports executable paths, canonical runtime, rollback root, source
  commit/content identity, installation-index digest, and the complete verified
  receipt IDs plus live installation/qualification anchor generations and
  redacted authority/backend key IDs and native broker code identity/digest. It
  queries the broker and live anchors; stored receipts alone are insufficient.
  MCP exposes read-only reports only.

Run: `rtk npm test`

Expected: stable JSON fixtures pass and strict warning promotion works.

- [ ] **Step 4: Commit**

```bash
rtk git add src/harness_core/doctor.py tests/unit/test_doctor.py src/agent_harness.py runtime/mcp/server.mjs
rtk git commit -m "feat: add strict installation and host reports"
```

### Task 2: Add versioned disposable live-host workflows

**Files:**
- Create: `src/harness_core/live_verify.py`
- Create: `runtime/schemas/live-run.v1.schema.json`
- Create: `runtime/schemas/qualification-attempt.v1.schema.json`
- Create: `runtime/schemas/qualification-tail.v1.schema.json`
- Create: `runtime/templates/live-scenarios.json`
- Create: `tests/unit/test_live_verify.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: verified installation/live anchor, enrolled disposable repo with
  immutable `VerifiedWorktreeIdentity`, exact qualification tuple, host launch
  manifests, scenario template, protected qualification anchor, and evidence
  root.
- Produces: `allocate_qualification_attempt`, `plan_live_matrix`,
  `run_live_scenario`, verifier-owned evidence records, authenticated terminal
  attempt events, qualification-domain `VerifiedAnchorTransition` issuance, and
  `summarize_live_matrix`.

- [ ] **Step 1: Write failing workflow-state tests**

Cover plan-only behavior, non-disposable repo refusal, unenrolled repo refusal,
scenario start/terminal transitions, timeout, unexpected write, expected deny,
verifier fail/repair, session capture/resume, cross-host handoff, redaction,
retry bounds, and incomplete surface evidence. Add red cases for swapping the
worktree path and substituting another worktree with the same common directory
before a lease, write, resume, or handoff. Add a complete check-chain suffix
deletion and stale MAC-valid checkpoint; neither run may complete.
Require a monotonic attempt ordinal plus its authenticated allocation event to
issue/consume a qualification-domain `VerifiedAnchorTransition` before any
worktree/host launch. Cover raw old/new anchor calls, forged/replayed/
cross-domain capabilities, correct-old/arbitrary-new qualification commitment,
pass, fail,
incomplete, cancelled, crash, started-without-terminal, reordered/deleted/
edited attempt events, concurrent allocation, stale-tail replay, and restoration
of an old complete local qualification ledger plus anchor receipt. The live
anchor must reject replay and every allocated ordinal must remain represented by
a terminal record or pending tombstone.

For each required surface, test verifier-owned loopback network and provider
fixtures for unallowlisted network denial, unapproved provider-write denial,
ambiguous committed reconciliation, and authoritative-not-committed same-key
retry. Prove production credentials/adapters are absent and conflicting/
changed-precondition not-committed results remain uncertain.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_live_verify -v`

Expected: FAIL because versioned live workflows do not exist.

- [ ] **Step 2: Define exact default scenarios**

`runtime/templates/live-scenarios.json` contains for each host:

1. `allow`: read a committed sentinel and emit its SHA-256;
2. `deny`: attempt a write outside the enrolled worktree and require policy denial;
3. `isolated-write`: create one named file with exact content inside the task worktree, run verifier, and leave Git state exactly expected;
4. `verifier-repair`: begin with a deterministic failing test, apply one repair, and require the registered verifier to pass;
5. `resume-handoff`: persist task/session reference, stop cleanly, resume on the same host, then hand off a read-only summary to a second host;
6. `network-deny`: attempt an unallowlisted connection to a verifier-owned
   loopback endpoint and require host/harness denial before the fixture receives
   a request;
7. `provider-write-deny`: invoke an unapproved write against a verifier-owned
   loopback provider with production write adapters/credentials absent and
   require zero dispatches;
8. `ambiguous-committed`: lose the loopback response after one committed
   same-key write, reconcile by authoritative key lookup/readback, and prove
   consumed with exactly one logical dispatch;
9. `ambiguous-not-committed`: lose the response before commit, reconcile
   authoritative non-commit plus unchanged precondition/readback, retry once
   with the same key, and prove one commit; the sibling changed/conflicting
   precondition case must remain uncertain with no retry.

Prompts include bounded turn/time limits and prohibit every network/external
write except the explicitly instrumented loopback fixture step.

- [ ] **Step 3: Implement disposable repository safety**

Create repositories only beneath an owner-only verifier root. Write a random
run marker into the root as defense in depth, but never treat it as a substitute
for stable object identity. Enroll explicitly and create the Foundation
worktree-identity record bound to canonical root/Git-dir/common-dir paths and
stable object IDs, root/remote provenance, and independent nonce. Revalidate
and retain the verified root capability before every scenario
lease/write/resume/handoff. Record initial/final Git hashes/status. Cleanup
reopens exact objects descriptor-relative and consumes a typed
`VerifiedFinalizationPlan`; any unexpected state/identity drift is quarantined
rather than deleted, and caller paths/raw cleanup plans are never applied.

- [ ] **Step 4: Implement CLI matrix commands**

Support:

```text
agent-harness verify-hosts plan --hosts codex,claude,cursor,omp --json
agent-harness verify-hosts run --plan PATH --expect-digest SHA256 --json
agent-harness verify-hosts status --run-id UUID --json
agent-harness verify-hosts cursor-broker-status --run-id UUID --json
```

`run` reparses and fully verifies the raw plan against current installation,
source, config, hosts, launch contracts/manifests, worktrees, authorities,
scenario/verifier set, and live anchors, then allocates/anchors the qualification
attempt before any launch. Only the resulting verified run capability may
spawn. Caller-supplied evidence paths are not accepted.

A run is complete only when every declared scenario has a valid authenticated
event/check chain, actual/checkpoint/task tails equal the live task anchor, the
worktree identities and full qualification tuple remain exact, final Git state
is expected, and one authenticated terminal qualification event advances the
live qualification anchor. Any crash or missing terminal event is incomplete.

- [ ] **Step 5: Add redaction and leak tests**

Seed fixtures with synthetic token patterns in process environment and host output. Persisted reports must contain only redaction markers; the test scans the complete evidence tree and fails if any sentinel survives.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_live_verify -v`

Expected: workflow, safety, and leak tests pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/harness_core/live_verify.py \
  runtime/schemas/live-run.v1.schema.json \
  runtime/schemas/qualification-attempt.v1.schema.json \
  runtime/schemas/qualification-tail.v1.schema.json \
  runtime/templates/live-scenarios.json tests/unit/test_live_verify.py \
  src/agent_harness.py
rtk git commit -m "feat: add disposable live-host verification"
```

### Task 3: Add native Cursor IDE evidence and consecutive matrix rules

**Files:**
- Create: `src/harness_core/cursor_evidence.py`
- Create: `runtime/templates/cursor-ide-workflow.md`
- Create: `runtime/schemas/surface-evidence.v1.schema.json`
- Create: `tests/unit/test_surface_evidence.py`
- Modify: `src/harness_core/live_verify.py`
- Modify: `runtime/schemas/live-run.v1.schema.json`

**Interfaces:**
- Consumes: verifier-owned run/scenario/nonce, native Cursor process/window
  provenance, quit/restart state, disposable trusted repository, broker-captured
  hook/screenshot/readback evidence, final Git state, and live qualification
  anchor.
- Produces: authenticated broker-owned Cursor IDE surface record and anchored
  consecutive-attempt qualification.

- [ ] **Step 1: Write failing surface evidence tests**

Reject wrong app/version, missing quit/restart proof, untrusted or
non-disposable repo, swapped worktree identity, another worktree with the same
common directory, absent allow/deny hook output, absent screenshot/readback,
unexpected Git diff, stale evidence, and CLI evidence mislabeled as IDE
evidence.
Reject caller-uploaded file paths, caller-selected run/scenario/nonce,
screenshots outside broker custody, PID/process-start or native executable
identity mismatch, window reassignment, capture outside the broker-authorized
time window, replay across attempts/scenarios, and missing broker transcript.
After restart, require the IDE itself to emit an authenticated cross-surface
handoff request and the target surface to acknowledge the same anchored task
head; CLI/orchestrator-synthesized handoff proof fails.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_surface_evidence -v`

Expected: FAIL because native Cursor surface evidence does not exist.

- [ ] **Step 2: Define the exact IDE workflow**

The template requires:

1. the broker allocates and anchors run/scenario/nonce and starts its capture
   window before surface interaction;
2. quit Cursor completely, then the broker launches/binds the installed native
   signed executable, PID/process-start identity, and repository window;
3. verify trust and installed harness hook health;
4. run allow and outside-write deny and let the broker capture visible
   readback, denial, and hook output;
5. run isolated write/verifier repair and capture final expected Git status;
6. run the loopback network/provider denial and both ambiguous reconciliation
   scenarios with production adapters/credentials absent;
7. quit/restart, have the broker bind the new native process/window, and resume
   the same anchored task;
8. from the resumed IDE, originate a real authenticated handoff to a different
   required agent surface; capture its acknowledgement/shared task head before
   the IDE continues;
9. keep all broker-owned screenshots/readbacks/transcripts inside the evidence
   root and close the capture window.

- [ ] **Step 3: Validate evidence without inferring UI state**

The verifier-owned `CursorEvidenceBroker` is the only surface-record
constructor. It owns run/scenario/nonce allocation, native executable code-
identity verification, PID/process-start/window binding, capture timing, and
artifact creation. It hashes broker-created screenshots/readbacks/hook and
handoff transcripts, app version, complete parent-enrollment/worktree identity
including root/Git-dir/common-dir object IDs, scenario/attempt IDs, and final
Git state into an authenticated terminal event. Revalidate identity and process/
window provenance before and after restart/resume. No API accepts a caller
evidence path or mutable record. Missing native evidence, process/window/
identity drift, or absent IDE-originated handoff leaves the attempt incomplete;
it cannot fall back to Cursor CLI or source inspection.

- [ ] **Step 4: Qualify the last three anchored allocated attempts**

Derive the window from the authenticated qualification event ledger and live
qualification tail/anchor. Take the last three allocated ordinals without
filtering. All must have exactly one terminal `pass`; a fail, incomplete,
cancelled, crash, missing terminal event, ledger gap, or pending attempt breaks
the streak. Never delete or reorder non-passing attempts; retention may keep an
anchored status/digest tombstone.

Every attempt binds one full invariant tuple containing:

- source commit, `SourceContentIdentityV1`, and frozen-source manifest root;
- installation ID plus live installation-anchor generation/commitment;
- exact installation-index generation/document digest and ordered verified
  receipt inventory/root;
- redacted effective config, hooks, adapter profiles, and policy digest;
- scenario/template and verifier-set digests;
- every host executable path/version/binary/capability digest;
- stable launch-contract digest and per-run exact ordered full
  launch-manifest digests;
- every worktree identity and evidence-root digest;
- integrity/approval key IDs, anchor backend identity/generation, and
  applicable OS capability digest.

Each run's full manifests naturally contain run-local IDs. Define one versioned
invariant launch-contract projection that excludes only an enumerated set of
run-local fields for streak equality while preserving each exact full-manifest
digest for individual-run validation. Any other tuple change resets the streak.
Replay of an older qualification ledger/tail/receipt fails against the live
anchor.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_surface_evidence -v`

Expected: invalid surface evidence and broken streaks fail; three identical complete runs qualify.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/cursor_evidence.py \
  runtime/templates/cursor-ide-workflow.md \
  runtime/schemas/surface-evidence.v1.schema.json \
  tests/unit/test_surface_evidence.py src/harness_core/live_verify.py \
  runtime/schemas/live-run.v1.schema.json
rtk git commit -m "feat: require native Cursor IDE evidence"
```

### Task 4: Add stress and rollback rehearsal workflows

**Files:**
- Create: `src/harness_core/rehearsal.py`
- Create: `tests/unit/test_rehearsal.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: scheduler, live verifier, verified installation/index and complete
  receipt set, install/uninstall transactions, pre-install snapshot manifest,
  exact pre-uninstall qualification tuple/live anchors, terminal retirement
  pin, and exact source commit/content identity.
- Produces: `run_stress_rehearsal`, `run_rollback_rehearsal`, and signed rehearsal reports.

- [ ] **Step 1: Write failing stress-report tests**

Require exactly 24 terminal lanes with host distribution 8/8/4/4, no `EMFILE` escape, no lost/duplicate ledger sequence, no duplicate writer interval, and all injected child failures either recovered or reported terminally.
Allocate/anchor the stress attempt before launch and bind its report to the
same full qualification tuple and exact ordered launch manifests as the live
matrix. A tuple/anchor/config/host drift or projection-only terminal status
invalidates it.

- [ ] **Step 2: Write failing rollback-report tests**

Cover pre-install manifest completeness, credential-bearing paths represented
only by sealed snapshot references, a complete rollback-object canary scan, real
uninstall call, indexed receipt-set completeness, missing/duplicate/foreign/
unchecked/unexpected-or-omitted receipt refusal before restore, Keychain
recovery snapshot availability, credential-config restore/readback before
operational existing-item restore or new-item delete, remaining filesystem
restore after those inverses, recovery-item deletion last,
path/mode/uid/gid/symlink-target/symlink-ownership/ACL/xattr comparison, extra
touched path, ownership restore/readback failure, restore failure, runtime
incorrectly removed on failure, source-commit/content mismatch on reinstall,
typed terminal removal/readback of newly created installation-scoped approval/
anchor/control items and the external bootstrap broker after
`UNINSTALLED_PUBLISHED`, exact retained protected terminal-pin readback,
protected user-presence reprovisioning on reinstall, and final strict doctor.
If uid/gid metadata is applicable to any target, the
qualifying host must perform and readback-verify a real uid/gid round trip; lack
of permission/capability makes the attempt non-qualifying rather than skipped.
Only a target/platform contract with no uid/gid metadata may record
`not-applicable`, and injected ownership failure/readback cases remain
mandatory.
Inject crashes before/after every authority-retirement WAL fsync, authority
deletion/readback, terminal-attestation signature/fsync, add-only protected
terminal-pin creation/readback, control-key deletion, receipt-key deletion, and
helper unlink/readback. Require exact forward recovery
through `RETIREMENT_VERIFIED`, `APPROVAL_RETIRED`, `ANCHORS_RETIRED`,
`RECOVERY_ITEMS_RETIRED`, `TERMINAL_ATTESTED`, `CONTROL_KEY_RETIRED`,
`RECEIPT_KEY_RETIRED`, `BROKER_RETIRED`, and `RETIREMENT_COMPLETE`. The
signer/helper dependency order and protected-terminal-pin plus public-
attestation recovery after key removal are qualifying assertions. Inject
replacement/replay of the attestation, public key, manifest, WAL, and all other
ordinary retirement files after both keys are absent; no helper finalizer may
run unless the live protected pin still matches the exact attestation digest,
receipt-public-key digest, retired era, and helper object identity.
After reinstall, allocate and anchor three new attempts. Reject one or two new
passes, any old-era attempt mixed into the streak, an intervening new-era
failure/incomplete/cancel/crash, changed post-reinstall tuple, or a report that
collapses the pre- and post-uninstall tuple digests into one field.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_rehearsal -v`

Expected: FAIL because stress and rollback rehearsal reports do not exist.

- [ ] **Step 3: Implement bounded rehearsal commands**

```text
agent-harness rehearse stress --plan PATH --expect-digest SHA256 --json
agent-harness rehearse rollback --snapshot PATH --expect-installation UUID --json
```

Stress has explicit `fixture` and `live-host` modes. Fixture mode uses harmless
local children for deterministic tests. Release-qualified `live-host` mode
launches the installed Codex/Claude/Cursor/OMP clients in the 8/8/4/4
distribution and records each client's capability identity, auth probe, and
launch-manifest digest; relabelled generic children cannot qualify. Rollback
requires an external snapshot path and never creates a weaker snapshot during
uninstall. It calls only the verified-installation-state uninstall API; it
cannot supply receipt paths or a subset.
Both commands parse caller files only to fully verify current installation,
qualification tuple, live anchor, source, and object identities and then consume
phase-specific verified rehearsal/uninstall/finalization capabilities. Raw
plans/snapshots/paths never authorize a launch, restore, detach, or purge.
Rollback drives and crash-resumes every published uninstall phase through
atomic runtime detach and typed tombstone purge, then independently verifies and
crash-resumes the complete authority-retirement phase machine. Raw retirement
plans, persistent references, helper paths, or mutable terminal-attestation
projections never authorize deletion. After reinstall it allocates and runs
three complete live matrices in the new qualification era. The signed rehearsal
report records distinct authenticated `pre_uninstall_tuple_digest` and
`post_reinstall_tuple_digest`, the terminal retirement-pin digest, and the
three new allocated attempt ordinals/evidence roots.

- [ ] **Step 4: Implement exact restoration comparison**

Compare the union of pre-install targets and every target from the complete
verified installation-index receipt set. Every path must match kind,
content/symlink target, mode, uid, gid, ACL, and xattrs using symlink-aware
readback; expected-absent paths must be absent. Compare Keychain item
presence/value/metadata inside the protected broker and persist only an opaque
comparison attestation plus redacted identity—never secret bytes or
secret-derived fingerprints. Prove the credential config was restored first,
operational inverses next, remaining filesystem restoration next, recovery
items last, and runtime detach/purge only after restoration. The rollback
rehearsal report uses exact field-by-field equality, not a best-effort metadata
summary. After the redacted terminal broker attestation, verify every exact new
installation-scoped authority/control locator and external bootstrap object is
absent except the declared protected terminal retirement pin; verify that
pin's exact immutable public digest payload and do not claim another transition
under the removed anchor. Reinstall must explicitly provision fresh authority
state through protected user presence, use the same source commit and recomputed
`SourceContentIdentityV1`, produce a new fully bound internally invariant
qualification tuple under the new installation/authority era, query current
live anchors, pass strict doctor, then allocate and pass three consecutive
complete matrices as the last three allocated attempts. It must not claim
equality with the retired pre-uninstall authority/key/anchor identities or use
any retired attempt in the new streak.

Run: `rtk npm test`

Expected: injected restore mismatch blocks success and complete stress/rollback fixtures pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/rehearsal.py tests/unit/test_rehearsal.py src/agent_harness.py tests/run.sh
rtk git commit -m "feat: add stress and rollback rehearsals"
```


### Task 5: Catalog capabilities and gate obsolete-item cleanup

**Files:**
- Create: `src/harness_core/capabilities.py`
- Create: `tests/unit/test_capabilities.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: host reports, executable/package inventories,
  `VerifiedAdapterReceipt` values or complete `VerifiedInstallationState`
  bound to the expected installation, skill/MCP/plugin identities, qualified
  live matrices, and a rollback rehearsal report containing distinct
  authenticated pre-uninstall and post-reinstall qualification tuple digests.
- Produces: `build_capability_catalog`, `plan_quarantine`, and `plan_verified_cleanup`.
  Verification returns phase-specific `VerifiedQuarantinePlan` or
  `VerifiedFinalizationPlan`; only their matching apply APIs mutate.

- [ ] **Step 1: Write failing catalog and cleanup tests**

Cover canonical and duplicate executable paths, semantically duplicate MCP
registrations, same-name/different-content skills, broken symlinks, stale
registrations, current and last-known-good versions, unmanaged capabilities,
quarantine readback, missing matrix qualification, missing rollback rehearsal,
changed quarantine digest, and attempted cleanup through a broad directory
target. Add raw/unchecked, forged, and wrong-installation receipt red cases for
ownership, quarantine, restore, and removal; each must fail before mutation.
Also reject raw cleanup/quarantine plans, caller paths, stale/full
qualification-tuple mismatch, live installation/qualification anchor drift,
changed object identity, a rollback report missing either tuple or the terminal
retirement-pin digest, any old-era attempt in the current streak, and
still-referenced last-known-good/recovery data.
Crash during each exact finalizer and require forward resume without broad
recursive deletion.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_capabilities -v`

Expected: FAIL because capability identity and proof-gated cleanup do not exist.

- [ ] **Step 2: Define exact capability identity**

```python
@dataclass(frozen=True)
class Capability:
    kind: Literal["executable", "skill", "mcp", "plugin", "hook", "agent"]
    logical_id: str
    host: str
    version: str | None
    canonical_path: str
    content_sha256: str | None
    owner_receipt: str | None
    health: Literal["healthy", "broken", "stale", "duplicate"]
```

Duplicate classification requires the same normalized logical identity and behavior/content digest; a shared name alone is not enough. Unmanaged healthy capabilities are retained.

- [ ] **Step 3: Implement transactional quarantine**

Move only exact catalog paths owned by a receipt from the already verified
installation state into an owner-only quarantine root through transaction
operations and record original metadata/digest. This API cannot parse raw
receipt documents. Re-run host reports after quarantine. Any health regression
rolls the quarantine transaction back through the verified receipt-owned
inverse. Planning observations bind trusted roots plus parent/target object
witnesses; apply consumes only `VerifiedQuarantinePlan` and uses
descriptor-relative no-clobber/CAS operations.

- [ ] **Step 4: Gate final deletion on full proof**

`plan_verified_cleanup` requires the last three anchored allocated attempts to
be terminal passes under one identical full qualification tuple, one passing
24-lane report, and a real rollback/reinstall report that separately binds the
retired pre-uninstall tuple, protected terminal pin, and current post-reinstall
tuple. The current three attempts and live installation/qualification anchors
must equal the post-reinstall tuple; no retired attempt may count. It also
requires unchanged quarantine object identities/digests and no live reference.
It retains the canonical current version and one last-known-good version per
agent host. Verification returns Foundation's typed
`VerifiedFinalizationPlan`; raw inventory is read-only.

- [ ] **Step 5: Add no-glob cleanup CLI**

Support `capabilities catalog`, `capabilities quarantine --plan ...`, and `capabilities cleanup --plan ... --expect-digest ... --confirm`. Cleanup targets exact quarantine object IDs; reject glob characters, parent paths, workspace roots, and unresolved symlinks.
Each mutating command reparses and fully verifies current state, then consumes
only the matching verified type. A plan digest and `--confirm` alone are not
authority; confirmation must use the protected local interactive path and MCP
cannot finalize.

Run:

```bash
rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_capabilities -v
rtk npm test
```

Expected: incomplete proof blocks deletion, exact qualified cleanup preserves canonical and last-known-good versions, and unmanaged capabilities survive.

- [ ] **Step 6: Commit**

```bash
rtk git add src/harness_core/capabilities.py tests/unit/test_capabilities.py src/agent_harness.py tests/run.sh
rtk git commit -m "feat: gate capability quarantine cleanup"
```

### Task 6: Correct documentation, glossary, and architecture decisions

**Files:**
- Create: `docs/glossary.md`
- Create: `docs/adr/0001-canonical-ledger.md`
- Create: `docs/adr/0002-transactional-adapters.md`
- Create: `docs/adr/0003-independent-verifiers.md`
- Create: `docs/adr/0004-omp-is-not-pi.md`
- Modify: `README.md`
- Modify: `INSTALL.md`
- Modify: `docs/architecture.md`
- Modify: `docs/app-integrations.md`
- Modify: `docs/orchestration.md`
- Modify: `docs/security.md`
- Modify: `docs/troubleshooting.md`
- Create: `tests/test_docs.sh`
- Modify: `tests/run.sh`

**Interfaces:**
- Consumes: shipped CLI help, schemas, adapter registry, and stable specification.
- Produces: accurate user documentation and automated docs/CLI consistency checks.

- [ ] **Step 1: Write failing docs consistency checks**

Generate CLI command names, MCP tool names, adapter names, schema IDs, and strict success rules from executable source and compare them with machine-readable fenced inventories in docs. The test must catch the known stale 29-vs-31 tool count, task-index wording, first-vs-last verdict claim, broad `verify-gates` claim, and Pi/OMP claim.

Run: `rtk ./tests/test_docs.sh`

Expected: FAIL on current documentation drift.

- [ ] **Step 2: Add glossary and focused ADRs**

Define every specification term once in `docs/glossary.md`. Each ADR contains Context, Decision, Consequences, Rejected alternatives, and Verification. Do not include machine paths or local inventory.

- [ ] **Step 3: Rewrite lifecycle and integration docs**

Document plan/digest apply, enrollment, profiles, exact intents, authenticated checks, strict doctor, collision behavior, OMP separately from Pi, live matrices, stress, fail-safe uninstall, and rollback retry. State limits precisely; never claim all hooks/surfaces are tested by a narrower command.
Document phase-specific verified mutation capabilities, descriptor-relative
filesystem limits, publication/bootstrap/uninstall recovery, three-authority
separation and explicit threat boundary, live anti-rollback anchors,
typed authority bootstrap, macOS native broker/code-identity and
Secure-Enclave/user-presence approval lifecycle, explicit rotation/recovery,
acyclic setup-body/bootstrap/final-plan digests, domain-authorized
`VerifiedAnchorTransition` boundaries, no in-place lost-key reprovisioning,
crash-resumable terminal authority retirement/attestation and protected
non-authority retirement pin,
projection-versus-authority rules, `SourceContentIdentityV1`, all-attempt
qualification semantics/full tuple and post-reinstall three-pass new-era gate,
loopback-only provider/network scenarios,
Cursor evidence broker/provenance and IDE-originated handoff, typed finalizers,
and non-qualifying uid/gid or file-backed-authority capabilities.

- [ ] **Step 4: Verify docs and full suite**

Run:

```bash
rtk ./tests/test_docs.sh
rtk npm test
rtk git diff --check
```

Expected: docs consistency, full suite, and diff checks pass.

- [ ] **Step 5: Commit**

```bash
rtk git add README.md INSTALL.md docs tests/test_docs.sh tests/run.sh
rtk git commit -m "docs: define the durable harness contract"
```

### Task 7: Harden the source release gate and compatibility matrix

**Files:**
- Create: `tests/test_package.sh`
- Create: `tests/test_leaks.sh`
- Create: `tests/test_source_identity.sh`
- Create: `tests/test_compat.sh`
- Modify: `tests/preflight.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `package.json`

**Interfaces:**
- Consumes: a clean committed frozen source snapshot, its recomputed
  `SourceContentIdentityV1`, lock artifacts, schemas, generated inventories,
  leak patterns, and the private execution-ledger proof of the canonical
  Python binding established before Foundation Task 1.
- Produces: authoritative local release report bound to the exact source
  commit and `SourceContentIdentityV1`, exact `node@22.23.2`, the installed
  supported Node version, Python 3.10+, and the unchanged canonical interpreter
  selected for installed shims.

- [ ] **Step 0: Verify the inherited Python binding evidence**

Before any Task 7 command, read the private execution ledger and prove its
recorded canonical real path and Python 3.10+ version were established before
Foundation Task 1 Step 1 or any earlier npm test, preflight, script, or
Python-capable command. Revalidate the same exported
`"$AGENT_HARNESS_PYTHON"` by argv-only probe. A missing, late, changed,
relative, symlink-aliased, incompatible, or unprovable binding makes release
qualification fail; never rediscover or substitute an interpreter.

- [ ] **Step 1: Write failing package, leak, source-identity, and compatibility checks**

Package into a temporary directory, install from the archive with scripts
disabled, and prove runtime self-containment, including the native macOS
authority-broker source/wrapper and its reproducible build inputs. Scan tracked
source, archive, fixtures, Git diff, and generated example reports with
synthetic leak canaries. Verify no `__pycache__`, local goal data, machine
manifest, evidence, or rollback snapshot enters the archive.

Run:

```bash
rtk ./tests/test_package.sh
rtk ./tests/test_leaks.sh
rtk ./tests/test_source_identity.sh
rtk ./tests/test_compat.sh
```

Expected: FAIL because the package, leak, source-identity, and compatibility
gates are absent or incomplete.

- [ ] **Step 2: Bind preflight to the frozen source identity**

Before the fresh-clone stage, fail when tracked changes exist unless `--allow-dirty-source-checks` is explicitly supplied for local focused work. Always print and record the exact commit cloned. Keep release mode committed-only.
Recompute `SourceContentIdentityV1` from the exact clean commit-derived frozen
snapshot, compare it with the declared identity, and bind the report, package,
and all install/build consumers to that snapshot. Prove excluded
untracked/ignored paths are never opened by those consumers. The dirty-source
override may run focused checks but cannot emit a release-qualified identity or
installable report.

`tests/test_source_identity.sh` must prove executable-bit, symlink-target,
tracked-content, recursive-submodule, algorithm-version, and inclusion-policy
changes alter the identity while timestamps and checkout location do not. It
must reject staged dirt, unstaged worktree dirt, dirty or uninitialized
submodules, case-fold and Unicode-normalization collisions, unsupported
paths/types, untracked non-ignored executable/config inputs, and any
install/build access to excluded paths.

- [ ] **Step 3: Add compatibility entry points**

Add package scripts:

```json
"scripts": {
  "test": "./tests/run.sh",
  "preflight": "./tests/preflight.sh",
  "test:package": "./tests/test_package.sh",
  "test:leaks": "./tests/test_leaks.sh",
  "test:source-identity": "./tests/test_source_identity.sh",
  "test:compat": "./tests/test_compat.sh"
}
```

`test_compat.sh` runs the suite once with the installed supported Node and once
with exact `node@22.23.2` from an isolated cache/runner. Before execution it
requires the package artifact to match npm integrity
`sha512-OGbbJ0gJCDJ+wEw+VkMxVgdfqYI81k3xaXof3dF2zX078bOttW7ZyMdxJYzJn3hvTwMyYEw/SvnqKqOCiA1C4w==`
and shasum `81841b82e8fc61c925bf052e7a7c9b72a51a2259`; a metadata, digest,
version, executable-path, or cache mismatch fails closed. It records both Node
executable paths and versions, revalidates and runs entrypoints with the
unchanged canonical `"$AGENT_HARNESS_PYTHON"` selected before Foundation Task
1, and separately proves an incompatible Python 3.9 ambient default fails
clearly. The negative default-interpreter gate must not replace or mutate the
bound interpreter. CI pins `22.23.2` and current stable on macOS and Linux and
runs the source-identity gate, but docs continue to call the local committed
preflight authoritative.
The macOS leg also compiles the authority broker from the frozen snapshot, runs
its no-Keychain self-test, records executable/code-identity/content digests, and
proves an altered or unsigned helper is rejected. Linux proves the explicit
unsupported/non-qualifying production-authority capability rather than
substituting the file fixture. Automated source gates never provision a real
approval key or request user presence.

- [ ] **Step 4: Run focused and dirty-tree source checks**

Before committing, run:

```bash
rtk npm ci --ignore-scripts
rtk npm audit --omit=dev --audit-level=low
rtk npm test
rtk npm run test:package
rtk npm run test:leaks
rtk npm run test:source-identity
rtk npm run test:compat
rtk npm run preflight -- --allow-dirty-source-checks
```

Expected: zero advisories, all focused tests pass, the package is
self-contained, the leak scan is clean, the frozen-source identity matrix
passes, both exact Node environments pass, and the explicitly allowed
dirty-tree preflight passes its non-release checks including macOS simulation
without emitting a release-qualified report.

- [ ] **Step 5: Commit**

```bash
rtk git add tests/test_package.sh tests/test_leaks.sh \
  tests/test_source_identity.sh tests/test_compat.sh tests/preflight.sh \
  .github/workflows/ci.yml package.json
rtk git commit -m "test: enforce the complete source release gate"
```

- [ ] **Step 6: Run the authoritative committed preflight**

Run from the now-clean committed HEAD:

```bash
rtk npm run preflight
```

Expected: release-mode preflight verifies the exact committed clone, recomputes
and records the matching `SourceContentIdentityV1`, proves the package and
install/build path used only the frozen included snapshot, verifies the pinned
Node artifact digests and both Node environments, revalidates the inherited
Python binding evidence, and passes without `--allow-dirty-source-checks`.
