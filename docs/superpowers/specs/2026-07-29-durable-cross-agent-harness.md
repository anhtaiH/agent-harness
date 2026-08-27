# Durable Cross-Agent Harness Specification

Status: approved for local implementation

Implementation order:

1. [Transactional Foundation and Host Adapters](../plans/2026-07-29-foundation-and-host-adapters.md)
2. [Policy, Verification, and Scheduler](../plans/2026-07-29-policy-verification-and-scheduler.md)
3. [Release Gate and Live Host Verification](../plans/2026-07-29-release-and-live-verification.md)

## Purpose

Agent Harness is a local control plane for coding agents. It owns task state,
policy decisions, verification evidence, host-adapter receipts, and recovery.
Vendor sessions may resume execution, but the harness ledger is the only
canonical source of task status.

This specification is machine-agnostic. Real host manifests, installation
identifiers, credentials, snapshots, transcripts, and rollback bundles are
local-only data and must never be committed.

## Product invariants

1. A repository is inert until a user explicitly enrolls its canonical path and
   Git identity. Discovery alone never grants trust. A harness-created worktree
   also has a versioned immutable identity bound to that enrollment, including
   stable filesystem object identities for its root, worktree-specific Git
   directory, and common Git directory, and is revalidated before every lease,
   write, resume, and handoff.
2. Every task has one canonical task identifier, one ledger, and at most one
   writer lease. Multiple read-only workers may run concurrently.
3. A model statement such as `QA: PASS` is never verification. Completion requires a
   declared verifier to execute on its declared surface and produce a valid
   check record.
4. Harness-launched required gates fail closed. A hook crash, timeout, invalid
   response, missing adapter, stale receipt, or unavailable sandbox blocks the
   gated action.
5. Ordinary non-harness host sessions keep their user-owned defaults. The
   harness selects explicit launch profiles instead of rewriting global
   permission preferences.
6. External writes require a protected, user-presence approval signature over
   the exact installation, current authenticated task head and authorization
   epoch, worktree/launch identities, provider, operation, canonical target,
   content digest, precondition, expiry, and stable provider idempotency key.
   Approval and reservation are authenticated task events; a mutable intent
   file is only a projection. Reservation advances the live anti-rollback
   anchor before dispatch. An ambiguous outcome becomes `uncertain` and cannot
   be reissued until authoritative provider status and canonical readback
   reconcile it.
7. Installation and uninstallation are transactions. Uninstall restores every
   touched pre-existing target before removing managed runtime data. Prepared
   receipts become authoritative only when one generation-CAS publication
   transaction durably publishes and reads back the complete MAC-verified
   installation index. Uninstall derives its receipt set only from that index,
   rejects any missing, duplicate, foreign, unchecked, unexpected, or omitted
   receipt, restores credential configuration and Keychain state in dependency
   order, and detaches the runtime into an exact external tombstone before
   resumable purge. Any restore failure preserves the runtime, journal, and
   rollback bundle.
8. Unmanaged files are never overwritten. A path is mutable only when absent or
   owned by a MAC-verified receipt for the same installation identifier. The
   installation signing key is created by the first typed bootstrap Keychain
   operation with an authenticated WAL and exact conditional inverse before the
   first receipt. Mutation callers receive phase-specific verified types bound
   to the expected installation rather than unchecked parsed documents. Raw
   parsing and verification always finish before mutation.
9. Secret values never enter manifests, receipts, evidence, logs, prompts, Git,
   or rollback reports. Persistent configuration contains native-auth or
   Keychain references.
10. Source, installed runtime, host adapters, and evidence expose explicit
     schema versions and support forward-safe migration.
11. Mutable JSON documents, snapshots, indexes, and stored anchor receipts are
    caches or projections, never authorization or freshness authorities.
    Completion, mutation, cleanup, and qualification query a live
    compare-and-advance anchor outside the replayable file set and fail closed
    on unavailability, mismatch, rollback, or a pending anchored attempt.
12. Qualification is derived from the last three allocated attempt ordinals,
    including failed, incomplete, cancelled, and crashed attempts. All three
    must be terminal passes under one identical, fully bound qualification
    tuple; deleted or intervening attempts break the streak.

## Terminology

- installation: one generated UUID and its external rollback root.
- installation index: the separately MAC-authenticated inventory of every
  committed receipt belonging to an installation.
- workspace: a named installed runtime associated with an installation.
- enrollment: explicit trust for a canonical repository path plus Git identity.
- worktree identity: an immutable harness-created worktree record bound to its
  parent enrollment, canonical path, stable filesystem object identities for
  the worktree root/worktree-specific Git directory/common Git directory,
  root/remote identity, and random enrollment nonce.
- source content identity: `SourceContentIdentityV1`, a deterministic SHA-256
  manifest of the frozen clean commit-derived tracked source snapshot.
- task: the durable unit of work represented in the harness ledger.
- writer lease: an exclusive task-scoped right to mutate a worktree.
- launch profile: an explicit host command, sandbox, approval, network, and
  resource policy selected for one harness run.
- adapter plan: a no-write description of intended host changes.
- adapter receipt: the authenticated record of changes actually applied.
- verifier spec: a deterministic command, artifact, or real-surface workflow
  with pass/fail criteria independent of model prose.
- check record: an append-only, authenticated verifier result linked into the
  task's hash chain.
- check tail: a versioned, separately MAC-authenticated expected final sequence
  and hash for a task's check chain.
- write intent: a single-use authorization envelope for an external mutation.
- approval envelope: a protected user-presence signature over one exact write
  intent and the current authenticated task predecessor.
- state anchor: a live compare-and-advance authority, outside ordinary harness
  files, that commits the current installation/task/qualification generation
  and digest.
- verified anchor transition: a one-use, non-serializable domain authorization
  binding one exact old/new anchor transition to verified WAL/event/record
  evidence; raw old/new values never authorize compare-and-advance.
- qualification attempt: one allocated, anchored run ordinal with exactly one
  terminal pass, fail, incomplete, cancelled, or crash event.
- finalizer: an exact-target, forward-only, WAL-driven purge operation accepted
  only through a verified finalization plan.
- authority retirement: the protected, typed, forward-only terminal state
  machine that removes installation-scoped authorities after uninstall while
  retaining the last recovery signer/helper until a terminal attestation exists.
- host report: machine-readable adapter capability, version, health, and
  source-commit readback.

## Architecture

The implementation has four layers:

1. `harness_core`: schemas, canonicalization, transactions, receipts,
   enrollment, policy, evidence, scheduling, and retention. This layer is
   deterministic and host-neutral.
2. Host adapters: Codex, Claude Code, Cursor, and Oh My Pi (OMP). Each adapter
   performs capability discovery and emits core plans; it does not mutate
   paths directly.
3. CLI/MCP facade: the existing CLI and MCP server translate inputs to core
   operations and preserve backwards-compatible command names where safe.
4. Runtime assets: thin host instructions, hooks, wrappers, schemas, roles, and
   skills projected from one canonical runtime copy.

The existing monolithic CLI remains the compatibility facade while focused
modules are added under `src/harness_core/`. New correctness-critical logic must
live in the focused modules and be invoked by the facade; it must not be copied
back into the monolith.

## Local storage layout

```text
~/.agent-harness/
  installations/<installation-uuid>.json
  installations/<installation-uuid>.publication.wal
  rollback/<installation-uuid>/<transaction-uuid>/
    receipts/<generation>/<receipt-id>.json
    bootstrap/
      authority.wal
      signing-key.wal
    authority-retirement/<retirement-id>/
      retirement.wal
      terminal-attestation.json
    tombstones/<uninstall-transaction-id>/
  <workspace>/
    manifest.json
    config.json
    source/agent-harness/
    state/
      enrollments.json
      worktrees/<worktree-id>.json
      tasks/<task-id>/
        events.jsonl
        checks.jsonl
        check-tail.json
        check-append.wal
        anchor-receipts.jsonl
      adapters/<host>/receipt.json
      transactions/<transaction-id>.jsonl
      qualification/
        attempts.jsonl
        qualification-tail.json
      scheduler/
    evidence/
    hooks/
    skills/
```

The rollback root is a sibling of the workspace so an uninstall cannot delete
its own recovery material. Owner-only directories use mode `0700`; manifests,
receipts, ledgers, and logs use `0600`.

## Versioned contracts

Every JSON document has these top-level fields:

```json
{
  "schema": "agent-harness/<kind>",
  "schema_version": 1,
  "created_at": "RFC3339 UTC",
  "installation_id": "UUID"
}
```

Required version-one documents:

| Kind | Required identity and payload |
| --- | --- |
| source-content-identity | algorithm/policy version, exact ordered entry manifest digest, source commit, frozen-snapshot digest |
| workspace-manifest | workspace, source commit and content identity, canonical runtime root, canonical rollback root, generation |
| install-plan | installation ID, canonical runtime/rollback roots, exact source commit/content identity, bootstrap-independent setup-body digest, authority-bootstrap descriptor and digest, ordered adapter-plan digests, ordered operations, complete unsigned-plan digest |
| installation-index | generation, lifecycle state, publication transaction, predecessor digest, canonical runtime/rollback roots, exact ordered receipt IDs/paths/digests, receipt count, index MAC |
| installation-publication-wal | prior/new index generations and digests, transaction/plan digests, exact prepared receipt inventory, phase, MAC |
| authority-bootstrap-wal | fixed broker/Keychain locators, broker code identity, installation/creator IDs, immutable item attributes, exact conditional inverses, phase, protected broker signature |
| authority-manifest | broker code identity/digest, approval public-key digest, anchor backend/namespace/receipt-key IDs, protected terminal-pin fixed locator/immutable access attributes, capability state, bootstrap digest |
| authority-retirement-wal | retirement ID, exact authority/control/helper object identities and dependencies, ordered forward phases, readbacks, terminal-attestation digest, protected terminal-pin locator/readback, signatures |
| terminal-authority-attestation | retired installation/authority era, completed removals/readbacks, exact remaining helper finalizer, protected terminal-pin locator, public verification key, terminal signature |
| signing-key-bootstrap-wal | fixed Keychain locator, add-only operation/creator identity, expected immutable attributes, exact conditional inverse, phase, MAC |
| enrollment | canonical repo path, stable root/Git-dir/common-dir object IDs and canonical Git dirs, root commit, remote fingerprint, trust timestamp |
| worktree-identity | parent enrollment ID, canonical path, stable root/Git-dir/common-dir object IDs, canonical Git dirs, immutable root commit, remote fingerprint, random enrollment nonce |
| adapter-plan | host, plan ID, source commit, ordered operations, collision decisions, plan digest |
| adapter-receipt | host, applied transaction, exact targets, before/after metadata digests, plan digest, receipt MAC |
| host-report | host, executable, version, auth state, capabilities, adapter receipt, health failures/warnings |
| verifier-spec | verifier ID, task ID, risk tier, surface, argv/artifacts, timeout, pass criteria |
| check-record | sequence, verifier digest, result, output digest, prior hash, record hash, MAC |
| check-tail | task ID/version, expected sequence, expected record hash, checkpoint generation, MAC |
| task-event | task/version/authorization epoch, sequence, prior hash, event kind/payload digest, MAC |
| write-intent | task ID/epoch, provider, operation, canonical target, content digest, precondition, expiry, reservation/idempotency identity, provider operation ID, projected status |
| write-intent-approval | approval key ID, exact intent digest, predecessor task-event hash, protected signature |
| state-anchor-receipt | anchor namespace/backend/key ID, verified transition domain/digest, old/new generation and commitment, operation ID, broker receipt |
| qualification-attempt | allocated ordinal, immutable qualification tuple, started/terminal event, evidence root, chain hash, signature |
| qualification-tail | last allocated ordinal/hash, invariant tuple digest, live-anchor generation, signature |
| finalization-plan | lifecycle phase, exact owned object identities, containment/proof digests, ordered typed finalizers, predecessor generation, plan digest |
| migration | from/to versions, source digest, result digest, rollback transaction |

Unknown fields are retained. A document with a newer major schema version is
read-only and blocks mutation with a clear migration error.

## Source content identity

`SourceContentIdentityV1` is computed only from a frozen, clean,
commit-derived snapshot. The implementation enumerates the exact commit tree,
not ambient directory order, and sorts repository-relative Git path bytes
lexicographically. It rejects absolute paths, `.`/`..` components, NULs,
non-round-trippable platform names, case/normalization collisions, unsupported
special entries, and symlink traversal during materialization.

The digest input is a canonical length-prefixed byte stream beginning with
`agent-harness/source-content-identity/v1\0` and the inclusion-policy version.
For each entry it includes the raw relative path bytes, Git object kind, exact
Git mode, and one payload: SHA-256 of regular-file blob bytes, raw symlink
target bytes, or the exact submodule commit object ID plus recursively verified
declared submodule identity. The final identity is SHA-256 of that stream.
Executable bits therefore affect identity; timestamps, uid/gid, checkout
directory, and locale do not.

The index and tracked worktree must equal the selected commit byte-for-byte.
Dirty tracked or staged state, uninitialized or dirty submodules, and untracked
non-ignored executable/configuration inputs reject the source. Only the
versioned exclusion policy may omit ignored dependency caches, goal state,
evidence, and build output. Installation, packaging, tests that produce release
artifacts, and runtime projection execute from the frozen materialized snapshot
and may not read excluded paths; an access audit verifies this. Algorithm and
inclusion-policy versions, ordered-entry-manifest digest, source commit, and
frozen-snapshot digest are stored and bound into plans, receipts, installed
manifests, qualification tuples, and release evidence.

## Transaction model

Planning is read-only and deterministic. Fresh setup uses one acyclic hash DAG.
First, a domain-separated `SetupBodyV1` digest covers the canonical plan data
fields while excluding its own digest, the authority-bootstrap descriptor/
digest, and the final plan digest.
Second, the canonical authority-bootstrap descriptor binds that setup-body
digest plus the exact fixed locators, helper code identity/digest, immutable
item attributes, initial anchor namespace/generation, capabilities, and
conditional inverses. Third, its descriptor digest is placed into the complete
unsigned install plan and the final install-plan digest is computed. No stage
may use a provisional sentinel, omit a field, or contain its own or a later digest.

The final install-plan digest therefore covers installation ID, canonical
runtime and rollback roots, exact source commit and content identity, the
setup-body digest, exact authority-bootstrap descriptor and digest, ordered
adapter-plan digests, and ordered operations. It is not merely an operations
digest. Immediately before apply, the engine revalidates the expected
installation, both roots, source commit/content, adapter-plan identities, and
complete digest; a plan from another installation or source is rejected. Raw
parsed plans never cross a mutation boundary. Verification returns a
phase-specific capability such as `VerifiedBootstrapPlan`,
`VerifiedInstallPlan`, `VerifiedPreparedPublication`, `VerifiedRollbackPlan`,
`VerifiedUninstallPlan`, `VerifiedAnchorTransition`,
`VerifiedAuthorityRetirementPlan`, or `VerifiedFinalizationPlan`. Each
capability binds
the expected installation, lifecycle generation, live-anchor commitment,
trusted roots, complete plan digest, and expiry. Apply accepts only the
corresponding verified capability and consumes or invalidates it when bound
state advances.

Each operation declares one exclusive canonical target, captured parent and
target witnesses, a precondition, desired state, readback predicate, and exact
inverse. Supported install/rollback operation kinds are `mkdir`, `write-file`,
`copy-file`, `symlink`, `json-merge`, `managed-block`, `quarantine`,
`keychain-add`, `keychain-delete`, `keychain-replace`, and the composite
`credential-migrate`. Initial signing-key creation is the separately typed
`signing-key-bootstrap-add`. Permanent file/tree removal is a typed,
forward-only finalizer available only after a `VerifiedFinalizationPlan`.
Arbitrary shell text is never an operation. Distinct plan nodes may not own the
same canonical target. `credential-migrate` exclusively owns one configuration
target and journals its internal subphases; those subphases are not duplicate
plan targets.

Filesystem authorization is capability- and descriptor-relative rather than
pathname-based. Under the installation transaction lock, the engine opens a
trusted root directory, records its stable object identity, and walks every
component with directory-relative opens using `O_DIRECTORY | O_NOFOLLOW`.
Every mutable parent descriptor remains open through durable readback. Target
capture, temp creation, metadata changes, rename/link, readback, unlink, and
directory fsync all use that descriptor. Same-directory temporaries have
unpredictable names and are created with
`O_CREAT | O_EXCL | O_NOFOLLOW` and restrictive permissions. Cleanup unlinks a
temp only after its recorded object identity matches.

Before the first mutation, the engine captures target type, object identity,
bytes or symlink target, SHA-256, mode, uid, gid, ACL, and extended attributes
into the external rollback bundle and fsyncs the authenticated WAL and its
directory. It revalidates every parent and target witness immediately before
the commit primitive. An absent target uses an atomic no-clobber primitive; a
receipt-owned existing target uses an OS compare-and-swap primitive or an
exclusive protected mutation broker that excludes non-cooperating writers. If
the platform cannot provide the required safe primitive and exclusion boundary,
the operation fails closed. A changed, created, replaced, or symlinked
parent/target is a conflict and is never silently rebaselined. Restore never
follows a symlink while applying ownership, restores uid/gid whenever that
metadata is applicable, and readback-verifies every captured field.
Unsupported descriptor-relative or metadata primitives are explicit
non-qualifying capabilities, not pathname fallbacks.

Credential-bearing targets use sealed snapshots: on macOS their original bytes
are stored through a Keychain-backed snapshot reference, while the rollback
bundle contains only the reference, digest, and redacted metadata. Raw secret
bytes may not enter ordinary rollback objects, journals, receipts, or reports.
The owner-only file fallback remains a strict-doctor warning and cannot qualify
this machine's warning-free release.

Every Keychain put, delete, or replacement is itself an authenticated
write-ahead transaction operation. Before-state contains only a sealed
reference, digest, and redacted item identity; the secret is supplied over
stdin or an in-memory API, never argv or the journal. Apply requires
post-write/delete readback, and the authenticated receipt owns an exact inverse:
restore the prior item for a replacement/deletion or delete a newly created
item. Operational credentials and recovery/snapshot items have distinct
purposes and ownership; bulk cleanup may never remove a recovery item while
any configuration, rollback, or uninstall step still depends on it.

Apply stops on the first failed precondition or operation and rolls back all
completed operations in dependency order, not an unsafe flat reverse list. It
first quiesces the runtime, reads any sealed recovery bytes while their
references still exist, restores and verifies credential configuration so it
no longer points at the operational item, executes and verifies that item's
exact Keychain inverse, restores the remaining filesystem targets, and deletes
recovery material only after its last consumer succeeds. Rollback is
independently retryable and the installation control key remains available
through the final authenticated lifecycle transition.

Receipt creation and installation-index publication are one recoverable
generation-CAS protocol. Under the publication lock, apply writes new receipts
to immutable generation-qualified names, fsyncs them and their directories,
then writes an authenticated publication WAL and a full candidate index. The
candidate binds the transaction, predecessor generation/index digest, exact
ordered receipt mapping, and every receipt digest. After revalidating the
canonical predecessor, publication atomically replaces the canonical index,
fsyncs its directory, and reads the index back through normal verification.
That verified readback is the sole installation commit point. Before it, the
old index remains authoritative and prepared receipts are uncommitted; after
it, the complete new mapping is authoritative and cleanup is restartable.
Extra receipts never become installed state. Missing or invalid receipts,
same-generation forks, predecessor mismatch, or a hybrid index fail closed;
recovery never chooses by mtime or reconstructs an index from loose receipts.
The live installation anchor records the pending plan before the first external
mutation and consumes publication-domain `VerifiedAnchorTransition` values to
advance to the exact committed index/receipt root before success is
acknowledged.

If no installation signing key exists, the first transaction uses an
authenticated bootstrap WAL and an add-only fixed Keychain locator. It creates
the key and creator nonce in memory, fsyncs a WAL naming only the fixed locator,
immutable expected attributes, operation ID, and exact conditional inverse,
then performs `SecItemAdd` rather than upsert. The item stores the
installation/transaction/creator/WAL-digest markers and returns an opaque
persistent reference; no secret bytes enter the WAL. A pre-existing item
without a matching valid published receipt or matching authentic bootstrap WAL
is a collision, never silently adopted or overwritten. Recovery queries the
trusted fixed locator first and uses its immutable markers to select and
authenticate a WAL; it never trusts an unauthenticated WAL to choose a locator
or deletion target. An orphan prepared WAL with no matching item is
discard-only. The inverse deletes only the exact add result after matching all
markers. The first receipt and index publication transfer ownership from the
bootstrap transaction to the installation.

Uninstall accepts only verified installation state loaded from the fixed
installation-index location. Verification checks the index MAC and requires a
bijection between its ordered receipt entries and the receipt registry,
rejecting missing files, duplicate IDs/paths, foreign installation IDs,
unchecked documents, unexpected files omitted from the index, and receipt
digest/MAC failures before any restore or removal.

Its authenticated forward-recovery machine is `VERIFIED`,
`UNINSTALLING_PUBLISHED`, `CREDENTIALS_RESTORED`, `FILESYSTEM_RESTORED`,
`RUNTIME_DETACHED`, `TOMBSTONE_PURGED`, and `UNINSTALLED_PUBLISHED`. Each
transition publishes a full lifecycle index generation and is idempotently
resumable. The engine quiesces launchers, restores credential configuration and
operational Keychain items in dependency order, restores all remaining
filesystem targets, and then atomically renames the exact runtime object into
an external receipt-bound tombstone. Detachment, not recursive deletion,
removes it from the live path. A verified typed finalizer purges the tombstone
incrementally with object-identity and containment readback, recording progress
so a crash resumes without consulting caller paths. Only then is
`UNINSTALLED_PUBLISHED` committed. Recovery material and the control key
survive until their last verifier/lifecycle consumer.

Terminal removal is a separate `VerifiedAuthorityRetirementPlan` and signed
forward-only WAL with phases `RETIREMENT_VERIFIED`, `APPROVAL_RETIRED`,
`ANCHORS_RETIRED`, `RECOVERY_ITEMS_RETIRED`, `TERMINAL_ATTESTED`,
`CONTROL_KEY_RETIRED`, `RECEIPT_KEY_RETIRED`, `BROKER_RETIRED`, and
`RETIREMENT_COMPLETE`. It binds exact persistent references, fixed locators,
helper object identities, dependency edges, and readback predicates; raw paths
or caller-selected items never enter apply.

The native helper, installation integrity/control key, and anchor broker receipt
key remain until all earlier removals and absence readbacks complete. Before
removing either remaining key, the broker writes/fsyncs a redacted terminal
attestation MAC-authenticated by the still-live integrity authority and signed
by the asymmetric broker receipt key. That attestation contains the exact
remaining control-key, receipt-key, and external-helper finalizers plus the
fixed locator of a terminal retirement pin.

Still before either key is removed, the helper add-only creates and reads back
that non-synchronizing `ThisDeviceOnly` protected terminal pin. Its immutable
payload contains the attestation digest, receipt-public-key digest, retired
installation/authority era, and exact external-helper object identity/finalizer
digest. Its locator and expected immutable attributes are already bound by the
retirement plan; a pre-existing or mismatched item is a collision, never
adopted or overwritten. The pin exposes no key, signing method, anchor advance,
or general mutation authority. It is the permanent protected retirement
tombstone and is intentionally retained after uninstall so ordinary same-UID
files cannot replace the terminal trust root.

Only after the attestation and protected pin both read back exactly does
`TERMINAL_ATTESTED` complete. The control key is removed next and the receipt
key last. Once both keys are absent, the exact helper unlink/readback requires
both public verification of the attestation and live readback of the matching
protected pin; neither the self-contained attestation, replayable manifest/WAL,
nor a caller path is sufficient. Every pre/post attestation, terminal-pin,
deletion, and helper boundary is crash-tested, including replacement/replay of
all ordinary retirement artifacts after both keys are gone. Completion is
recognized from the protected pin, signed evidence, and exact absence readbacks
even if a crash follows the last deletion before a projection update. No later
operation may claim an anchored transition for the retired installation.

No API or flag accepts a caller-selected receipt subset, raw receipt path, raw
plan, or arbitrary cleanup path. `--keep-runtime` may retain a verified healthy
runtime; no flag may discard recovery data after a failed restore. Any restore,
anchor, publication, detach, purge, or readback failure preserves the journal,
rollback bundle, and recoverable tombstone state.

## Enrollment and identity

`agent-harness repo enroll --repo <path>` records the canonical path,
stable filesystem object identity of the opened repository root, canonical
worktree-specific Git directory and common directory plus their stable object
identities, immutable root commit, and remote fingerprint after explicit
confirmation. On POSIX the minimum stable object identity is `(st_dev,
st_ino)`; a filesystem generation/birth identifier is included where the OS
can supply one reliably. The root commit is obtained with
`git rev-list --max-parents=0 HEAD`; ordinary branch/HEAD advancement does not
invalidate enrollment. `start`, `resume`, and harness write profiles reject an
unenrolled repository. Moving or replacing a checkout, changing either Git
administration directory object, or changing its remote fingerprint requires
explicit re-enrollment. Read-only `doctor` and planning remain available while
unenrolled.

Each harness-created task worktree gets a versioned identity record containing
the parent enrollment ID, canonical worktree path, stable root object identity,
canonical worktree-specific Git directory and its stable object identity,
canonical common directory and its stable object identity, immutable root
commit, remote fingerprint, and random enrollment nonce. A nonce-bound marker
or xattr may add defense in depth, but it never substitutes for the three
independently reprobed object identities and a copied marker cannot bless a
replacement.

Validation opens the root as a directory without following a symlink, `fstat`s
it, resolves and opens both Git directories, checks all canonical paths and
object identities in one probe, runs repository-provenance checks, and then
proves the pathname still resolves to the retained root object. A mismatch
rejects same-path equivalent clones, standalone-directory swaps, recreated
linked worktrees, same-common-directory substitutions, and Git-administration
replacement. Validation never rewrites Git configuration, repairs a worktree,
refreshes stored identity, or manufactures a marker. The retained handle or an
immediate equivalent revalidation gates every writer-lease
acquire/renew/recovery, mutable operation dispatch, resume, and handoff.
Platforms without trustworthy directory object identity fail closed for
strong-mode mutation.

## Host adapter contract

Every adapter implements discovery, planning, verification, and removal:

```python
class HostAdapter(Protocol):
    host: str
    def discover(self, context: AdapterContext) -> HostCapabilities: ...
    def plan_install(
        self,
        context: AdapterContext,
        prior_receipt: VerifiedAdapterReceipt | None,
    ) -> AdapterPlan: ...
    def verify(
        self,
        context: AdapterContext,
        receipt: VerifiedAdapterReceipt,
    ) -> HostReport: ...
    def plan_remove(
        self,
        context: AdapterContext,
        receipt: VerifiedAdapterReceipt,
    ) -> AdapterPlan: ...
```

Detection requires a host-specific version probe. A generic executable name is
not sufficient. Adapters produce no writes outside their returned plan. Adapter
contexts carry the expected installation ID; receipt parsing and MAC/identity
verification occur before these methods are called. Ownership, update,
restore, removal, and uninstall entry points never accept raw mappings or raw
receipt paths.

- Codex: canonical `AGENTS.md` instructions, receipt-owned standalone profile
  files, per-run `--config` overrides, MCP, skills, and hooks where supported.
  Harness profiles overlay the user's base config without rewriting
  `~/.codex/config.toml`.
- Claude Code: `CLAUDE.md` bridge, strict MCP, sandbox/permission settings,
  hooks, skills, and subagents. Required settings are replayed on resume.
- Cursor: root/nested `AGENTS.md` plus Cursor-specific `.mdc` only when
  needed, native hooks with `failClosed: true`, MCP, CLI permissions, and
  separate CLI/IDE health probes.
- OMP: executable `omp` and native `~/.omp` / project `.omp`
  conventions. Harness launches use a runtime-owned repeatable `--config`
  overlay instead of rewriting the user's YAML. OMP is never detected or
  configured as upstream Pi. RPC waits for the startup `ready` frame and
  terminal `agent_settled` event.

Existing healthy capabilities are preserved. Duplicate cross-host skills or
MCP servers are projected from the canonical core when possible and otherwise
copied with exact hashes and receipts.

Capability cleanup is catalog-driven. Suspected duplicates, broken links,
stale registrations, and superseded binaries are first moved into an
owner-only quarantine transaction and every host is re-verified. Final deletion
requires qualified live matrices, stress proof, and rollback/reinstall proof;
it retains the canonical current version and one last-known-good version for
each agent host. Healthy unmanaged capabilities are never removed.

## Launch profiles

The default profiles are:

| Profile | Mutation | Network | Approval |
| --- | --- | --- | --- |
| read | no workspace mutation | denied unless verifier requires an allowlisted endpoint | never pauses |
| worktree-write | enrolled harness worktree only | denied by default | host-native on-request policy |
| yolo | explicit task and user authorization | explicit allowlist | never pauses |

A profile is a complete launch manifest: host version, argv, cwd, environment
allowlist, sandbox, approval mode, tools, MCP servers, hooks, timeout, turn
limit, and resume fields. Resume replays every non-persisted field. Global host
preferences are not rewritten to emulate profiles.

## Threat model and assurance boundary

The harness separates three authorities:

1. an installation-integrity key authenticates receipts, WALs, and internal
   event records with domain-separated MACs;
2. a distinct non-exportable approval key requires protected user presence and
   signs one exact external-write approval; and
3. a live compare-and-advance anti-rollback anchor holds namespace generations
   and commitments outside ordinary replayable harness files.

Production agent-facing APIs expose narrow verify, proposal, approval, reserve,
and domain-transition requests, never raw anchor compare-and-advance, raw key
bytes, or a generic signing oracle.
Owner-only mode bits alone are not an isolation boundary from another same-UID
process. A file-backed approval authority or file-backed/replayable anchor may
support development fixtures, but it disables production external writes and
release qualification.

The guarantees defend against harness-launched same-UID agents that can alter or
replay ordinary harness files and invoke agent-facing CLI/MCP methods, but
cannot read or inject the protected authority, satisfy user-presence signing,
or roll back the configured anchor. They do not defend against root or kernel
compromise, full login-account takeover, process injection into the authority,
trusted-UI compromise, provider-account takeover, or restoration of the
anchor's security domain. A local MAC proves integrity only; it does not prove
human authorization or freshness.

### Production authority bootstrap and backends

Authority provisioning is an explicit typed bootstrap phase completed before
the first installation transaction. A raw bootstrap document, flag, redirected
stdin, or MCP request cannot provision an authority. The protected local
interactive verifier consumes both the finalized install plan and its exact
authority-bootstrap descriptor. It recomputes, in order, the bootstrap-
independent `SetupBodyV1` digest, descriptor digest, and final install-plan
digest; requires every link to match; adds current fixed-locator
absence/collision observations; and only then returns one non-serializable
`VerifiedAuthorityBootstrapPlan`. That capability binds both source documents,
the complete setup/source/root identity, exact initial installation-anchor
namespace/generation, and the final install-plan digest as its pending-plan
commitment. A descriptor alone, a final plan alone, a sentinel digest, or a
pair from different setup bodies cannot provision authority state.

The protected local path consumes that capability, invokes the native broker,
and records an add-only, fixed-locator bootstrap WAL, so successful authority
bootstrap establishes the exact final install-plan commitment before the later
signing-key or installation mutation. Recovery
queries only those fixed locators, validates immutable installation, broker,
creator, and WAL markers, and never adopts or overwrites a foreign item. Partial
bootstrap is forward-recovered or conditionally removed only when every marker
matches. No ordinary installation receipt or live-anchor transition is claimed
before this root bootstrap completes.

The qualifying macOS backend is a native Security/LocalAuthentication broker.
First-use bootstrap compiles it from the frozen source snapshot into an
external verifier-owned bootstrap location and binds its code identity/content
digest into the bootstrap plan and authority manifest. The installation
transaction projects those exact bytes into the runtime, and the committed
receipt/index transfer ownership only after digest/code-identity readback. The
external bootstrap copy remains recovery material until that transfer. Strict
doctor rejects any mismatch. The broker provisions:

1. a distinct non-exportable approval key using Secure Enclave P-256 when the
   host supports it, with `privateKeyUsage` plus protected user presence; its
   public-key digest and broker identity are pinned;
2. a fixed, non-synchronizing `ThisDeviceOnly` Keychain anchor namespace and
   non-exportable asymmetric broker receipt key, accessible only through the
   verified narrow broker; and
3. no installation-integrity key, which remains the separate Foundation
   signing-key bootstrap and cannot substitute for either authority.

The anchor broker accepts only a one-use `VerifiedAnchorTransition`, never
caller-supplied raw old/new state. That capability binds domain/namespace,
installation plus task or qualification identity, operation kind, exact old/new
generations and commitments, complete WAL/event/check/record/plan digests,
authorization epoch when applicable, native caller/broker code identity,
operation nonce, and expiry. Domain-specific verifiers issue it only after
checking the current authenticated state; the narrow integrity authority
authenticates its native request without exposing a generic MAC. Initial
installation-anchor creation instead requires the protected
`VerifiedAuthorityBootstrapPlan` and local user-presence authorization.

The broker verifies and consumes that authorization, serializes the namespace,
requires exact current generation and commitment, advances by exactly one
generation, durably reads back the new state, and returns a broker-signed old/new
receipt. Forged, replayed, expired, cross-domain, wrong-code-identity, or
correct-old/arbitrary-new requests fail without an advance. Restart recovery can
finish only the exact prepared transition. The approval broker displays the canonical
provider/operation/target/content/expiry summary and signs only the versioned
external-write envelope after OS-verified user presence; it has no arbitrary
signing method.

Approval-key rotation requires protected user presence under both the currently
pinned authority and the candidate authority, records an authenticated
security transition, and advances every affected authorization epoch. Missing,
replaced, or unrecoverable authority state blocks external writes and
qualification; it is never silently recreated. There is no in-place lost-key
reprovisioning. If the approval key is unavailable but the live anchor,
integrity authority, broker receipt key, and helper remain healthy, the only
recovery is the verified uninstall/authority-retirement workflow followed by a
new protected setup and new authority/qualification era. If those retirement
authorities are also unavailable, only explicit offline disaster restoration
is possible and remains non-qualifying until a new installation era passes every
gate. Other operating systems may
provide a backend with equivalent guarantees. File-backed, replayable, generic
Keychain-command, mock, or unverified-code-identity backends remain
test/development fixtures and cannot qualify.

## Policy and external writes

All host events normalize to a typed operation before policy evaluation. A
required gate returns only `allow`, `ask`, or `deny` plus a stable reason code.
Internal errors return `deny` for harness launches. The authoritative intent
lifecycle lives in the current authenticated, hash-linked task-event chain and
live task anchor; `intent.json` and task snapshots are derived projections.
Editing a projection from `proposed` to `approved` never authorizes anything.

The approval signature covers the installation and pinned approval-key IDs,
intent ID, task ID/version/authorization epoch, predecessor task-event hash,
verified worktree and launch-manifest digests, provider, operation, canonical
target, content digest, provider precondition/revision, creation/expiry, and one
stable provider idempotency key. Protected approval is appended by
compare-and-swap only while that predecessor remains the current anchored task
head. Security-relevant task, identity, handoff, verifier-set, or launch changes
advance the authorization epoch and invalidate stale approvals.

The authoritative state machine is `proposed -> approved -> reserved ->
consumed`, with `reserved -> uncertain -> consumed | retryable -> reserved` for
reconciliation. Reservation verifies the protected signature and its presence
in the current anchored event chain, then compare-and-advances the task anchor
through an intent-domain `VerifiedAnchorTransition` before provider I/O. It
records the exact attempt and stable provider key.
Concurrent reservations yield one dispatch permit; a permit is task-head-,
epoch-, generation-, target-, content-, and expiry-bound and is single-use.

Verified provider status plus canonical target/content readback changes the
event state to `consumed`. A timeout, connection loss, conflicting precondition
or readback, missing operation identity, or any result that cannot prove whether
the provider committed becomes `uncertain`; neither `reserved` nor `uncertain`
can authorize a second dispatch. A provider's authoritative idempotency-key
lookup and unchanged precondition/readback may prove `retryable`; otherwise the
intent stays `uncertain` for human resolution. A retry reuses the exact key and
approval, requires a fresh anchored reservation transition, and is denied after
target, content, task head, epoch, generation, or approval expiry changes.
Providers without authoritative idempotency and status/readback guarantees do
not receive automatic retry. This proves one logical dispatch under the stated
provider contract, not distributed exactly-once execution.

## Verification and completion

Risk tiers select required verifier classes:

- green: deterministic command or artifact verifier.
- yellow: command plus independent review and negative-path check.
- red: command/artifact checks, security review, and real-surface verification.

Command verifiers store argv arrays and run without a shell. Artifact verifiers
store canonical paths and expected digests or predicates. Real-surface
verifiers store the host, starting state, workflow, evidence paths, and manual
or automated readback.

A check record is valid only if its verifier digest matches the current spec,
its predecessor hash matches the task chain, its MAC verifies, its result is
fresh enough for the task version, and required artifacts still match. Task
completion recomputes these facts; it never trusts a stored `passed` Boolean.

Before a required verifier executes, the scheduler allocates an attempt ID,
appends an authenticated `verifier-attempt-started` task event, and
consumes the event-bound verifier-domain `VerifiedAnchorTransition` to advance
the live task anchor. A killed or missing terminal verifier
therefore leaves an anchored pending attempt that blocks completion. The
terminal check record and task event close that exact attempt; no unstarted or
caller-invented result is accepted.

Each task also has a versioned, separately MAC-authenticated expected check
tail containing sequence and record hash. The live task commitment covers at
least installation ID, task ID/version/authorization epoch, task-event
sequence/hash, check sequence/hash, current verifier-set digest, and pending
verifier/dispatch attempt IDs. Under one interprocess lock, append verifies the
live anchor and old local commitment, fsyncs a WAL containing the exact old/new
commitments and record digest, appends and fsyncs the check and task events,
atomically replaces and fsyncs checkpoints and parent directories, then
consumes the check/task-domain `VerifiedAnchorTransition`, persists its broker
receipt, and only then marks the WAL committed. Recovery may complete only that exact prepared
transition; a conflicting anchor generation never selects a longest file or
truncates authenticated history.

Completion queries the live anchor and requires equality among its generation
and commitment, the actual event/check chains, authenticated checkpoints, task
projection, current verifier set, and absence of pending attempts. Deleting a
complete suffix, presenting stale checkpoints, or replaying an internally
consistent old event/check/projection/WAL set together with an old stored anchor
receipt still fails because the live anchor is newer. Anchor unavailability,
mismatch, rollback, or an incomplete anchored operation blocks completion.

## Credential references

Credential inventory records only host, source location, redacted field
identity, and an opaque sealed-snapshot reference; it does not persist a secret,
secret-derived fingerprint, or reversible command rendering. Healthy native
OAuth is preferred. When a host requires a secret, one
`credential-migrate` operation exclusively owns the configuration file and its
Keychain destination. It captures the original file through the sealed
rollback path, adds/replaces and readback-verifies the operational Keychain
item, builds a reference-only candidate in an isolated fixture location, proves
host authentication against that candidate, and only then performs one final
descriptor-relative atomic rewrite that replaces the plaintext field with the
persistent reference.

Its authenticated internal state machine records
`PREIMAGED -> DESTINATION_APPLIED -> CANDIDATE_PROBE_PASSED ->
FINAL_REWRITE_APPLIED -> COMMITTED`. Internal subphases are not separately
targeted plan operations. On failure or uninstall, the runtime is quiesced,
sealed source bytes are loaded while recovery references exist, the production
configuration is restored and verified, the exact operational Keychain inverse
is executed and verified, remaining filesystem state is restored, and recovery
snapshot items are deleted only after their last consumer. A crash at any
boundary resumes that ordering. Secret bytes never travel in argv, WAL,
receipt, report, log, error text, or durable output; only opaque item and sealed
snapshot identifiers may persist. An owner-only plaintext fallback is
non-qualifying and blocks warning-free strict doctor.

## Scheduler and recovery

Default host ceilings are Codex 8, Claude 8, Cursor 4, and OMP 4, with a total
ceiling of 24. The scheduler reserves a file-descriptor budget before spawn,
uses bounded queues and exponential backoff for transient `EMFILE`, and never
reduces the declared verification matrix to claim success.

Fixture processes prove admission logic, but release stress proof launches the
installed host clients across the declared 8/8/4/4 distribution. Relabelled
generic child processes are not sufficient live-host evidence.

Writer leases use an interprocess lock plus owner token, PID, process-start
identity, task version, verified worktree identity, and heartbeat. A stale
lease is recoverable only after proving the owner is gone and revalidating the
complete worktree identity. Lease acquire/renew/recovery and every writer
dispatch fail if the canonical path, retained/reprobed root object identity,
worktree-specific Git-directory path/object identity, common-directory
path/object identity, root/remote provenance, or nonce-bound marker (when
enabled) changed. Lease transitions are authenticated task events committed by
the live task anchor; snapshots and active-task indexes are derived caches.
Ledger appends are locked, fsynced, sequence-checked, hash-linked, and anchored.
Duplicate task starts, duplicate writers, lost append records, coordinated
local replay, and silent child failure are fatal verifier conditions.

## Retention and memory

- Active and blocked state: indefinite.
- Compact evidence and manifests: 365 days.
- Raw logs: 30 days.
- Unpromoted repository memory candidates: 90 days.
- Promoted memory: explicit human action only.

Cleanup first produces a raw dry-run inventory and never mutates from it.
Verification resolves every candidate descriptor-relative from a trusted root,
binds exact object identities, receipt ownership, containment, retention
cutoff, lifecycle/index generation, live-anchor commitment, and predecessor
event, and returns a phase-specific `VerifiedFinalizationPlan`. The only apply
API consumes that verified type and executes typed file, tree, evidence,
qualification-compaction, or tombstone finalizers through a forward-only WAL
with per-object readback and directory fsync. It refuses caller paths, raw
plans, changed objects, paths outside the installation, rollback material for
an installed/failed transaction, or data still referenced by any live task,
receipt, recovery step, or qualification tuple.

Compaction may replace raw evidence after its retention window, but it retains
authenticated, anchored status/digest tombstones for every allocated
qualification and verifier attempt, including failures, incompletes, crashes,
and cancellations. Cleanup cannot improve a qualification streak or roll back
the live qualification anchor.

## Doctor and host verification

Strict doctor succeeds only with `ok: true` and `warnings: []`. It validates
schema versions, ownership/modes, source commit, enrollment integrity,
transaction state, receipt MACs, hook reachability, profile validity, auth
health without secrets, executable identity, resource limits, rollback
availability, worktree/Git-directory object identities, descriptor-relative
filesystem primitives, authority/signing-key/publication/uninstall bootstrap
and recovery, native broker code identity/digest, pinned protected approval
authority, live anchor backend/namespace/receipt key and commitments, pending anchored
operations, domain-authorized transition enforcement, authority-retirement
state/terminal attestation, complete event/check/qualification chains, and
stale/duplicate capabilities. A missing, replayable, file-backed, mismatched, or unavailable
approval/anchor authority; unsupported applicable uid/gid restoration; or an
unsafe filesystem primitive is a stable failure, not a qualifying skip.

The live verifier exercises allow, deny, isolated write, verifier failure and
repair, resume/handoff, clean restart, unallowlisted-network denial,
unapproved-provider-write denial, and both committed and not-committed
ambiguous-write reconciliation paths on every supported surface. Network and
provider scenarios use verifier-owned loopback fixtures with production write
adapters and credentials absent; they prove host policy routing without remote
state change.

Native Cursor evidence is captured only by a verifier-owned broker that
allocates the run/scenario/nonce, launches or binds the native signed Cursor
executable, records PID/process-start and window identity, controls capture
timing, and owns screenshot/readback/hook/Git artifacts. Caller-uploaded paths
cannot establish IDE provenance. After a quit/restart, Cursor IDE must originate
a real authenticated handoff to another required agent surface, whose
acknowledgement and resulting shared task head are captured before the IDE
resumes.

Before any host launch, the qualification authority allocates and anchors a
monotonic attempt ordinal by consuming a qualification-domain
`VerifiedAnchorTransition` bound to its authenticated allocation event. Raw
anchor values cannot allocate. Each attempt has exactly one authenticated terminal
pass, fail, incomplete, cancelled, or crash event; started attempts without a
terminal event are incomplete. Qualification uses the last three allocated
ordinals, not the newest three successful files. All three must be terminal
passes and share one identical invariant tuple binding source commit and
`SourceContentIdentityV1`, installation ID and live anchor generation/root,
exact installation-index generation/document digest, ordered receipt
inventory/root, redacted effective config/hooks/policy/profile digests,
scenario/template/verifier-set digests, host executable paths/versions/binary
and capability digests, stable launch-contract digest, worktree identities,
evidence root, authority key IDs, anchor backend identity, and applicable OS
capabilities. Each run also binds its exact ordered full launch-manifest
digests; streak equality excludes only an explicitly enumerated run-local
projection. Any intervening or unresolved attempt or tuple change resets the
streak.

Stress verification uses the configured 24 lanes and proves no `EMFILE`, lost
or replayed record, duplicate writer, or unrecovered child failure. Rollback,
retention, and obsolete-item cleanup revalidate the same pre-uninstall full
qualification tuple against the current live installation/qualification
anchors before acting. A rollback report binds that authenticated retired tuple
digest separately from the post-reinstall tuple digest and terminal retirement
pin.

After terminal authority removal, reinstall begins a new qualification era with
freshly provisioned authority/anchor identities. It allocates and anchors three
new attempts; the last three allocated ordinals in that new era must all be
terminal passes under one new complete internally invariant tuple before
qualification, cleanup, or completion. No pre-uninstall attempt contributes to
that streak, and the new tuple never pretends to equal the retired
installation's tuple. Lost-approval-key recovery and offline disaster
restoration obey the same rule and remain non-qualifying until the new
three-pass streak completes.

## Source release gate

A source commit is installable only when:

1. focused tests and the full suite pass;
2. authoritative preflight passes from a fresh clone;
3. exact `node@22.23.2` and the installed supported Node version pass; the
   pinned Node 22 artifact must match npm integrity
   `sha512-OGbbJ0gJCDJ+wEw+VkMxVgdfqYI81k3xaXof3dF2zX078bOttW7ZyMdxJYzJn3hvTwMyYEw/SvnqKqOCiA1C4w==`
   and shasum `81841b82e8fc61c925bf052e7a7c9b72a51a2259`;
4. one canonical absolute Python 3.10+ interpreter is selected, version-checked,
   and bound before Foundation Task 1's first npm test, preflight, or other
   Python-capable command; all entrypoints pass with that interpreter recorded
   for the installed runtime, and an incompatible ambient default fails
   clearly;
5. `npm audit --omit=dev --audit-level=low` reports zero unresolved
   advisories, unless an explicit reviewed non-exploitability record exists;
6. the clean frozen source snapshot recomputes the declared
   `SourceContentIdentityV1`, and install/build consumers are proved not to read
   excluded untracked/ignored inputs;
7. the native macOS authority broker builds from that frozen snapshot, passes
   its no-Keychain self-test, and rejects altered/unsigned code identity; other
   platforms report unsupported/non-qualifying rather than substituting a file
   authority;
8. schema/examples validate and CLI/docs remain consistent;
9. source and diff leak scans pass;
10. every task has independent review and the whole branch has a final review.

## Non-goals

- Controlling vendor cloud-agent products or desktop applications not named by
  a host adapter.
- Treating OMP as upstream Pi.
- Publishing, pushing, or changing remote state during local installation.
- Automatic cross-repository memory promotion.
- Rewriting normal non-harness permission defaults.
- Using model self-report, mocks, or narrowed matrices as completion proof.
