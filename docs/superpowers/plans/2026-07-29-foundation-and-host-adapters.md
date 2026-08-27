# Transactional Foundation and Host Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build versioned core contracts, a fail-safe installation transaction, explicit repository enrollment, and collision-safe Codex, Claude Code, Cursor, and OMP adapters.

**Architecture:** Keep `src/agent_harness.py` as the compatibility facade while moving new correctness-critical behavior into focused `src/harness_core/` modules. Adapters emit immutable plans; one transaction engine owns all filesystem mutation and writes authenticated receipts outside the runtime deletion boundary.

**Tech Stack:** Python 3.10+ standard library, JSON Schema artifacts, Bash
integration tests, exact Node 22.23.2 plus the installed supported Node,
FastMCP, Zod, macOS/Linux filesystem metadata.

## Global Constraints

- Stable specification: `docs/superpowers/specs/2026-07-29-durable-cross-agent-harness.md`.
- Use TDD: observe the named test fail for the intended reason before implementation.
- Prefix every shell command with `rtk`.
- Before Task 1 Step 1 or any npm test, audit preflight, script, or Python-capable
  command, resolve `AGENT_HARNESS_PYTHON` exactly once to a canonical absolute
  executable path, prove that interpreter is Python 3.10 or newer, export it for
  the remaining plans, and record its real path/version in private execution
  evidence. Never rediscover or substitute an ambient interpreter.
  `tests/run.sh` validates this binding and invokes only the quoted
  `"$AGENT_HARNESS_PYTHON"`.
- Never weaken an existing gate or accept model verdict text as verification.
- Do not overwrite unmanaged files; no `--force` path may silently adopt them.
- Rollback data lives outside the runtime and survives failed uninstall.
- Receipt ownership is trusted only after MAC verification for the same
  installation; unchecked JSON never authorizes mutation.
- Raw parsed plans, receipts, indexes, snapshots, and cleanup inventories never
  cross a mutation boundary. Apply consumes phase-specific verified types bound
  to the installation, lifecycle generation, trusted roots, and live anchor.
- Task 2 implements the qualifying native authority broker and typed add-only
  authority bootstrap before Task 4 consumes a live anchor. First machine setup
  provisions it only through protected local interaction; file/mock authority
  fixtures never authorize production mutation or qualification.
- Fresh setup hashes an acyclic `SetupBodyV1` → authority-bootstrap descriptor
  → final install-plan DAG. The protected bootstrap verifier consumes both
  finalized documents and binds the exact final install digest into its
  non-serializable capability; sentinels and mutually recursive digests deny.
- Raw anchor namespace/old/new values never cross the broker boundary. Every
  post-bootstrap advance consumes a one-use domain-issued
  `VerifiedAnchorTransition` bound to exact authenticated transition evidence.
- All filesystem mutation is descriptor-relative from a pre-opened trusted root
  with no-follow traversal, atomic no-clobber/CAS behavior, and fail-closed
  capability reporting when the required primitive is unavailable.
- Credential-bearing targets use sealed rollback snapshots, never ordinary
  plaintext rollback objects.
- Persistent artifacts contain references, hashes, and redacted metadata—not secret values.
- Preserve normal host defaults; this plan installs only harness-owned adapter material.
- OMP is executable `omp` with `~/.omp` conventions; it is not upstream Pi.
- Keep `package-lock.json` and `npm-shrinkwrap.json` byte-identical.
- Each task ends in a local commit and independent task review; no push or PR.

---

### Task 1: Remove transitive dependency advisories

**Files:**
- Modify: `package.json`
- Modify: `package-lock.json`
- Modify: `npm-shrinkwrap.json`
- Modify: `tests/preflight.sh`

**Interfaces:**
- Consumes: current MCP imports in `runtime/mcp/server.mjs`.
- Produces: FastMCP `^4.12.1`, Zod `^4.1.13`, identical locks, and a zero-advisory release gate.

- [ ] **Step 0: Bind the canonical compatible Python**

Before running the audit or any other task command, choose one already
inventoried Python 3.10+ executable, resolve it to its real absolute executable
path, export that exact value as `AGENT_HARNESS_PYTHON`, and verify the reported
major/minor version with an argv-only probe. Record the exact real path and
version in private execution evidence. Keep the same exported value for every
subsequent Foundation, Policy/Scheduler, and Release command. A missing,
relative, symlink-aliased, changed, non-executable, or pre-3.10 value stops Task
1 before Step 1; the ambient `python3` is never a fallback.

- [ ] **Step 1: Record the failing security gate**

Run: `rtk npm audit --omit=dev --audit-level=low`

Expected: nonzero with advisories rooted in the locked `fastmcp@4.0.1`
dependency chain. Record the current count/severities as evidence—the observed
baseline was 9 total (5 high, 3 moderate, 1 low)—but do not make that
time-varying registry count the red assertion. The green/release assertion
remains exactly zero unresolved advisories.

- [ ] **Step 2: Add lock and audit assertions to preflight**

Add after syntax checks in `tests/preflight.sh`:

```bash
cmp -s "$ROOT/package-lock.json" "$ROOT/npm-shrinkwrap.json" || {
  echo "package-lock.json and npm-shrinkwrap.json diverged" >&2
  exit 1
}
(cd "$ROOT" && npm audit --omit=dev --audit-level=low >/dev/null)
```

Run: `rtk ./tests/preflight.sh --skip-macos-sim`

Expected: FAIL in the audit assertion.

- [ ] **Step 3: Upgrade only the direct dependency boundary**

Set exact declared ranges:

```json
"dependencies": {
  "fastmcp": "^4.12.1",
  "zod": "^4.1.13"
}
```

Regenerate the shrinkwrap with scripts disabled, then copy it byte-for-byte to the package lock:

```bash
rtk npm install --package-lock-only --ignore-scripts
rtk cp -p npm-shrinkwrap.json package-lock.json
```

Do not add `overrides` unless the normal dependency resolver still selects a vulnerable package and the task reviewer approves the exact override.

- [ ] **Step 4: Verify runtime compatibility and security**

Run:

```bash
rtk npm ci --ignore-scripts
rtk npm audit --omit=dev --audit-level=low
rtk node runtime/mcp/server.mjs --self-test
rtk npm test
rtk ./tests/preflight.sh --skip-macos-sim
```

Expected: zero advisories, MCP self-test exit 0, full suite pass, preflight pass.

- [ ] **Step 5: Commit**

```bash
rtk git add package.json package-lock.json npm-shrinkwrap.json tests/preflight.sh
rtk git commit -m "build: update secure MCP dependencies"
```

### Task 2: Add versioned contracts, protected authorities, receipt authentication, and unit-test runner

**Files:**
- Create: `src/harness_core/__init__.py`
- Create: `src/harness_core/contracts.py`
- Create: `src/harness_core/auth.py`
- Create: `src/harness_core/authorities.py`
- Create: `src/harness_core/source_identity.py`
- Create: `runtime/authority/macos-broker.swift`
- Create: `runtime/bin/ah-authority`
- Create: `tests/unit/support.py`
- Create: `tests/unit/test_contracts.py`
- Create: `tests/unit/test_auth.py`
- Create: `tests/unit/test_authorities.py`
- Create: `tests/unit/test_source_identity.py`
- Create: `tests/test_python_binding.sh`
- Create: `runtime/schemas/source-content-identity.v1.schema.json`
- Create: `runtime/schemas/workspace-manifest.v1.schema.json`
- Create: `runtime/schemas/install-plan.v1.schema.json`
- Create: `runtime/schemas/installation-index.v1.schema.json`
- Create: `runtime/schemas/installation-publication-wal.v1.schema.json`
- Create: `runtime/schemas/authority-bootstrap-wal.v1.schema.json`
- Create: `runtime/schemas/authority-manifest.v1.schema.json`
- Create: `runtime/schemas/signing-key-bootstrap-wal.v1.schema.json`
- Create: `runtime/schemas/enrollment.v1.schema.json`
- Create: `runtime/schemas/worktree-identity.v1.schema.json`
- Create: `runtime/schemas/adapter-plan.v1.schema.json`
- Create: `runtime/schemas/adapter-receipt.v1.schema.json`
- Create: `runtime/schemas/host-report.v1.schema.json`
- Create: `runtime/schemas/verifier-spec.v1.schema.json`
- Create: `runtime/schemas/check-record.v1.schema.json`
- Create: `runtime/schemas/check-tail.v1.schema.json`
- Create: `runtime/schemas/state-anchor-receipt.v1.schema.json`
- Create: `runtime/schemas/write-intent.v1.schema.json`
- Create: `runtime/schemas/finalization-plan.v1.schema.json`
- Create: `runtime/schemas/migration.v1.schema.json`
- Modify: `tests/run.sh`

**Interfaces:**
- Consumes: RFC3339 timestamps, installation UUIDs, and the already-bound
  canonical `AGENT_HARNESS_PYTHON`.
- Produces: `SchemaError`, `require_document`, `new_document`,
  `canonical_json_bytes`, narrow `IntegrityAuthority` verification/MAC
  operations, `VerifiedAuthorityBootstrapPlan`, `LiveAnchorBroker`,
  `ApprovalAuthority`, `VerifiedAnchorTransition`,
  `SourceContentIdentityV1`, `VerifiedInstallPlan`, `VerifiedRollbackPlan`,
  `VerifiedAdapterReceipt`, `VerifiedInstallationIndex`,
  `VerifiedInstallationState`, `VerifiedBootstrapPlan`, and
  `VerifiedFinalizationPlan` used by every later task.

- [ ] **Step 1: Write failing Python-binding and contract tests**

Before modifying the runner, add `tests/test_python_binding.sh` cases proving
that `tests/run.sh` rejects a missing binding, a relative or symlink-aliased
path, a non-executable, an interpreter below 3.10, and a path changed after
initial validation. Also prove a canonical compatible binding is used for the
unit-test subprocess rather than the ambient default.

```bash
rtk ./tests/test_python_binding.sh
```

Expected: FAIL because `tests/run.sh` neither validates nor consistently uses
the binding.

Write tests that require these behaviors:

```python
class ContractTests(unittest.TestCase):
    def test_canonical_json_is_stable(self):
        self.assertEqual(canonical_json_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}')

    def test_newer_schema_blocks_mutation(self):
        with self.assertRaisesRegex(SchemaError, "newer schema_version 2"):
            require_document({"schema": "agent-harness/workspace-manifest", "schema_version": 2}, "workspace-manifest")

    def test_unknown_fields_survive_validation(self):
        doc = valid_workspace_manifest(extra={"future": {"kept": True}})
        self.assertEqual(require_document(doc, "workspace-manifest")["future"], {"kept": True})

    def test_payload_cannot_replace_base_identity(self):
        with self.assertRaisesRegex(SchemaError, "reserved field"):
            new_document("workspace-manifest", INSTALLATION_ID,
                         created_at=CREATED_AT, schema_version=99)

    def test_bool_is_not_a_schema_version(self):
        with self.assertRaisesRegex(SchemaError, "positive integer"):
            require_document({**valid_workspace_manifest(), "schema_version": True},
                             "workspace-manifest")
```

Add source-identity red tests over frozen Git fixtures. Require the
domain-separated, length-prefixed `SourceContentIdentityV1` stream to sort raw
repository-relative Git path bytes and bind kind, exact Git mode, regular-file
blob digest, symlink target bytes, and recursive submodule identity. Prove that
executable-bit, symlink-target, tracked-content, submodule, algorithm-version,
or inclusion-policy changes alter the identity; timestamps and checkout
location do not. Reject dirty index/worktree state, dirty/uninitialized
submodules, unsupported paths/types, case or Unicode-normalization collisions,
and untracked non-ignored executable/config inputs. Prove frozen installation
consumers cannot read excluded dependency caches, goal/evidence state, or build
output.

Add authority red tests before implementation. A raw bootstrap plan,
non-interactive flag, redirected stdin, or MCP request cannot create authority
state. Cover fixed-locator add-only provisioning, foreign-item collision, crash
before/after every authority-WAL and Keychain/broker boundary, two concurrent
provisioners, broker restart, code-identity drift, copied/replayed WALs, stale
anchor generation/commitment, concurrent compare-and-advance, receipt tamper,
approval-key replacement, approval without protected user presence, and
attempted arbitrary signing. Construct a canonical bootstrap-independent
`SetupBodyV1`, bootstrap descriptor, and final install plan in that order. Add
red cases for a sentinel/self-derived digest, changed body after descriptor
creation, descriptor from another body, omitted body field, changed final plan,
and a final plan whose descriptor digest is valid but not linked to its body;
all must fail before compiling the helper, writing a WAL, or provisioning an
item. Add forged/replayed/expired/cross-domain
`VerifiedAnchorTransition` cases, wrong installation/task/qualification or
operation kind, wrong WAL/event/record digest, wrong caller code identity, and
the critical correct-old/arbitrary-new request. Raw old/new values and every
case must fail without advancing the broker. A file-backed/mock backend must
identify itself as non-qualifying. Tests use a fake native broker; they never
touch the user's real Keychain or request real user presence.

Run: `rtk npm test`

Expected: FAIL because `harness_core.contracts` does not exist and the runner
binding contract is not implemented.

- [ ] **Step 2: Implement canonical base validation and MAC primitives**

At the start of `tests/run.sh`, validate the exported interpreter with a
no-shell argv call, resolve its real path, require exact equality with the
exported absolute path, require Python 3.10+, and retain the validated value
unchanged. Run the unit suite only as:

```bash
PYTHONPATH="$ROOT/src" "$AGENT_HARNESS_PYTHON" -m unittest discover -s "$ROOT/tests/unit" -p 'test_*.py'
```

Implement:

```python
SCHEMA_VERSION = 1
BASE_FIELDS = frozenset({"schema", "schema_version", "created_at", "installation_id"})

class SchemaError(ValueError):
    pass

def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def new_document(
    kind: str,
    installation_id: str,
    *,
    created_at: str,
    **payload: object,
) -> dict[str, object]:
    uuid.UUID(installation_id)
    if BASE_FIELDS.intersection(payload):
        raise SchemaError("payload contains reserved field")
    require_rfc3339_utc(created_at)
    return {
        "schema": f"agent-harness/{kind}",
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "installation_id": installation_id,
        **payload,
    }

def require_document(value: object, kind: str, *, mutable: bool = True) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SchemaError(f"{kind} must be an object")
    if value.get("schema") != f"agent-harness/{kind}":
        raise SchemaError(f"expected agent-harness/{kind}")
    version = value.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SchemaError("schema_version must be a positive integer")
    if mutable and version > SCHEMA_VERSION:
        raise SchemaError(f"newer schema_version {version} is read-only")
    return dict(value)
```

Define an `IntegrityAuthority` with narrow, domain-separated methods for each
receipt, index, WAL, and internal-record kind. The production boundary accepts
an opaque key handle/key ID and canonical payload, never raw key bytes and never
an unrestricted signing request. Its private implementation uses HMAC-SHA256
over the kind/operation domain plus canonical JSON without the `mac` field,
requires the expected installation ID, and verifies with
`hmac.compare_digest`; tests use an explicit fake authority. Receipt
verification returns `VerifiedAdapterReceipt`; complete-plan verification
returns `VerifiedInstallPlan`; index verification returns
`VerifiedInstallationIndex` and only a complete registry-bijection loader may
construct `VerifiedInstallationState`. Bootstrap and finalization verification
return their distinct phase-specific types. Define `VerifiedRollbackPlan` here
so Task 3 can type and test restoration; only a test-only issuer is available
until Task 4 adds production derivation from a still-live verified transaction.
Constructors are module-private, non-serializable, bound to expected
installation/generation/root/anchor commitments, and cannot be reused after
bound state advances.

Implement `SourceContentIdentityV1` from an exact clean commit-tree snapshot.
Encode a domain string and policy version followed by length-prefixed,
byte-sorted entry records containing raw relative path, object kind, Git mode,
and regular-blob SHA-256, symlink-target bytes, or recursively verified
submodule identity. Materialize only from that frozen snapshot, perform the
specified dirty/untracked/collision rejection checks, and return the algorithm,
policy, ordered-manifest digest, source commit, and frozen-snapshot digest.

Each JSON Schema must set `additionalProperties: true` and enforce its required version-one fields.

- [ ] **Step 3: Implement the production authority bootstrap and narrow brokers**

Implement `authorities.py` as the only core interface to authority backends.
Define the exact canonical `SetupBodyV1` projection as the install-plan data
fields excluding its own digest, the authority-bootstrap descriptor/digest, and
the final plan digest.
`plan_authority_bootstrap` binds its domain-separated digest to fixed broker/
Keychain locators, installation and creator IDs, native broker code identity/
digest, immutable item attributes, capabilities, exact conditional inverses,
and initial installation-anchor namespace/generation. Its descriptor digest is
then placed into the final install plan.

`verify_authority_bootstrap(final_install_plan, bootstrap_descriptor, ...)`
recomputes the setup-body digest, descriptor digest, and final install-plan
digest in that order, verifies every cross-link, and binds those exact values
plus current absence/collision observations into a one-use
`VerifiedAuthorityBootstrapPlan`. The capability's pending-plan commitment is
the exact final install-plan digest. No serialized digest contains itself or a
later digest, and only the protected local interactive path may consume the
capability.

On macOS, compile the reviewed `runtime/authority/macos-broker.swift` source
from the frozen snapshot into an external verifier-owned bootstrap location,
bind its code identity/content digest into the plan, and invoke it with argv
arrays plus bounded stdin. The later installation transaction projects those
exact bytes into the runtime; verified receipt/index publication transfers
ownership only after digest/code-identity readback, while the external bootstrap
copy remains recovery material until then. The helper uses Security and
LocalAuthentication to provision, at fixed non-synchronizing `ThisDeviceOnly`
Keychain locators:

1. a non-exportable Secure Enclave P-256 approval key when supported, with
   `privateKeyUsage` and protected user presence, returning only its public-key
   digest and opaque persistent reference;
2. a separate anchor namespace and non-exportable broker-receipt key restricted
   to the verified helper code identity; and
3. an add-only authority bootstrap record containing installation, creator,
   helper, locator, and WAL-digest markers but no key bytes.

The same narrow helper later supports one retirement-only add operation for the
fixed `ThisDeviceOnly` terminal-pin locator already bound by the authority
manifest. That operation accepts only `VerifiedAuthorityRetirementPlan`,
creates immutable public digests/identities rather than key material, rejects a
pre-existing item as a collision, and exposes no update/delete method.

The bootstrap WAL is written/fsynced before dispatch and becomes complete only
after the broker signs and reads back the full authority manifest. Recovery
queries only the fixed locators, never an unauthenticated caller/WAL locator;
it resumes the exact matching bootstrap or conditionally removes only exact
matching partial add results. Foreign/pre-existing items are collisions and
are never adopted, replaced, or upserted.

Define one-use, non-serializable `VerifiedAnchorTransition` values bound to
domain/namespace, installation plus task or qualification identity, operation
kind, exact old/new generations and commitments, complete plan/WAL/event/check/
record digests, authorization epoch where applicable, native caller/broker code
identity, nonce, and expiry. Only domain-specific transaction/event/
qualification verifiers may construct them after current-state verification;
the narrow `IntegrityAuthority` authenticates the native request without
exposing a generic MAC. Initial anchor creation is instead bound to the
protected `VerifiedAuthorityBootstrapPlan`.

`LiveAnchorBroker.compare_and_advance(transition:
VerifiedAnchorTransition)` serializes the bound namespace, verifies and
consumes the one-use authorization, requires its exact old
generation/commitment, advances exactly one generation to its exact new
commitment, durably reads back the state, and returns a broker-signed old/new
receipt. No public/native overload accepts raw namespace/old/new values.
`ApprovalAuthority` exposes only public-key verification, health, and
`approve_external_write(envelope, display_summary)`; the native broker displays
the canonical summary and signs the versioned envelope only after OS-verified
user presence. It exposes neither generic signing nor raw key material.
Missing Secure Enclave/user-presence support, helper code-identity drift,
Keychain replacement, or anchor readback/CAS failure is a stable capability
failure. File-backed and fake implementations are explicit non-qualifying test
backends. Other platforms must provide an equivalent backend or remain
non-qualifying.

Run:

```bash
rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest \
  tests.unit.test_authorities tests.unit.test_auth -v
```

Expected: typed/fake authority tests pass; on macOS a compile/self-test verifies
the native broker without provisioning real user authority state.

- [ ] **Step 4: Verify all schema examples**

Add a table-driven test loading every `runtime/schemas/*.v1.schema.json` and checking `$id`, `type`, required base fields, and `additionalProperties`.
Add auth tests for valid receipt, edited payload, wrong installation, wrong key,
missing MAC, malformed MAC, verified-type non-forgeability, and attempted reuse
of a verified value under another expected installation/generation/anchor.
Prove agent-facing code cannot request an arbitrary MAC or access key bytes and
that raw plans/indexes/WALs/finalization inventories fail before mutation. The
new schemas require the deterministic source identity, complete unsigned
install-plan identity, exact installation-index receipt inventory/count,
predecessor-bound publication WAL, protected add-only authority bootstrap and
manifest including the fixed protected terminal-pin locator/immutable access
attributes, live-anchor receipt with verified domain-transition digest,
add-only signing-key bootstrap WAL and
conditional inverse, complete immutable worktree object identities, separately
MAC-authenticated expected check-tail sequence/hash, and exact typed
finalization targets.

Run: `rtk npm test`

Expected: unit tests and existing integration suite pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core tests/unit tests/test_python_binding.sh \
  tests/run.sh runtime/schemas runtime/authority/macos-broker.swift \
  runtime/bin/ah-authority
rtk git commit -m "feat: add versioned contracts and protected authorities"
```

### Task 3: Capture complete filesystem metadata

**Files:**
- Create: `src/harness_core/safe_fs.py`
- Create: `src/harness_core/fsmeta.py`
- Create: `tests/unit/test_safe_fs.py`
- Create: `tests/unit/test_fsmeta.py`

**Interfaces:**
- Consumes: a pre-opened `TrustedRoot`, descriptor-relative path, stable
  directory/target witnesses, rollback object directory, and phase-specific
  verified authorization.
- Produces: `open_trusted_root`, `resolve_no_follow`, descriptor-relative
  no-clobber/CAS primitives,
  `capture_path(root, relative_path, objects_dir, sealer=None) -> PathSnapshot`,
  and `restore_path(snapshot, root, objects_dir, authorization:
  VerifiedRollbackPlan, sealer=None) -> None`.

- [ ] **Step 1: Write failing round-trip tests**

Cover an absent path, regular file bytes/mode/uid/gid, symlink target plus
symlink uid/gid, directory mode/uid/gid, extended attribute when supported,
and a macOS ACL when `chmod +a` is available. Use `lstat`-based assertions to
prove symlink metadata is captured and restored without following the link. The
file test must prove byte and all metadata restoration after mutation.
Also cover a sensitive file through a fake sealer and prove its canary bytes
never enter `objects_dir` or the serialized snapshot.
Add injected ownership-restore and ownership-readback failures. Where the test
process has permission to change uid/gid, perform a real round trip; otherwise
record an explicit unit-fixture capability skip while the injected failure
cases remain mandatory. That skip cannot satisfy release qualification; the
Release Task 4 qualifying host must perform the applicable real round trip.
Add deterministic safe-filesystem races: replace a parent directory with a
symlink after planning, swap an ancestor after capture, create an expected-
absent target after the prepared WAL fsync, modify/replace an existing target
immediately before commit, replay a copied temp name, and replace a temp before
cleanup. Every case must conflict without changing the attacker-selected
object. Require atomic no-clobber for absence, compare-and-swap or protected
exclusive mutation for existing targets, retained parent descriptors, and
object-identity readback. Inject an OS lacking a required `openat`/no-follow,
directory-fsync, no-clobber, or safe existing-target primitive and prove it
fails closed rather than using a pathname fallback.

```python
root = open_trusted_root(test_root)
snapshot = capture_path(root, "target", objects)
target.write_bytes(b"changed")
os.chmod(target, 0o644)
restore_path(snapshot, root, objects, authorization)
self.assertEqual(target.read_bytes(), b"original")
self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
```

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_safe_fs tests.unit.test_fsmeta -v`

Expected: FAIL because `capture_path` is missing.

- [ ] **Step 2: Implement immutable snapshot records**

Use this public shape:

```python
@dataclass(frozen=True)
class PathSnapshot:
    trusted_root_id: FileObjectId
    relative_path: str
    parent_witness: DirectoryWitness
    target_object_id: FileObjectId | None
    kind: Literal["absent", "file", "directory", "symlink"]
    sha256: str | None
    storage: Literal["none", "object", "sealed"]
    object_name: str | None
    sealed_reference: dict[str, str] | None
    link_target: str | None
    mode: int | None
    uid: int | None
    gid: int | None
    xattrs: dict[str, str]
    acl: str | None
```

`open_trusted_root` opens and `fstat`s an explicitly approved root directory.
`resolve_no_follow` walks every relative component with directory-relative
`O_DIRECTORY | O_NOFOLLOW` opens and retains the final parent descriptor.
Capture, object-store creation, temp creation, rename/link/unlink, metadata,
readback, cleanup, and directory fsync use those descriptors. Temp names are
unpredictable and use `O_CREAT | O_EXCL | O_NOFOLLOW`; cleanup verifies the
recorded temp identity before unlink. Store file bytes under
`objects/<sha256>` using descriptor-relative create-exclusive writes, mode
`0600`, fsync, and digest readback. Encode xattr values with base64. Restore
uid/gid with the platform's non-following ownership API before final
mode/ACL/xattr verification, and never dereference a symlink while capturing,
restoring, or reading back metadata. On macOS use native descriptor-bound ACL
and xattr APIs (or a retained-fd adapter proved equivalent); never rewalk an
untrusted pathname for metadata. On platforms without ACL or
symlink-ownership support, record the capability explicitly rather than
silently claiming restoration.
When a caller marks a file sensitive, require a sealer, store only its opaque
reference and digest, and refuse to fall back to the ordinary object store.

- [ ] **Step 3: Reject unsafe restoration**

Add tests and implementation that reject absolute paths, root-relative paths
containing `..` after normalization, unsupported special files, digest mismatch, an object
outside `objects_dir`, failed uid/gid restore, or uid/gid/symlink-identity
readback mismatch. Also reject a changed trusted-root identity, any changed ancestor/parent/target
witness, unsafe temp identity, unsupported safe primitive, or stale lifecycle/
anchor binding. Public restoration without a `VerifiedRollbackPlan`, with a raw
parsed receipt/snapshot/plan, or with a verified value bound to another
installation/generation must fail before target mutation. Failed-apply rollback
derives a one-use `VerifiedRollbackPlan` from the still-live verified install
transaction; it never passes the raw install plan to restore.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_fsmeta -v`

Expected: all metadata and rejection tests pass.

- [ ] **Step 4: Commit**

```bash
rtk git add src/harness_core/safe_fs.py src/harness_core/fsmeta.py \
  tests/unit/test_safe_fs.py tests/unit/test_fsmeta.py
rtk git commit -m "feat: snapshot filesystem metadata for rollback"
```

### Task 4: Implement write-ahead transactions and fail-safe uninstall

**Files:**
- Create: `src/harness_core/transaction.py`
- Create: `src/harness_core/publication.py`
- Create: `src/harness_core/finalization.py`
- Create: `src/harness_core/authority_retirement.py`
- Create: `tests/unit/test_transaction.py`
- Create: `tests/unit/test_publication.py`
- Create: `tests/unit/test_finalization.py`
- Create: `tests/unit/test_authority_retirement.py`
- Create: `runtime/schemas/authority-retirement-wal.v1.schema.json`
- Create: `runtime/schemas/terminal-authority-attestation.v1.schema.json`
- Modify: `src/harness_core/auth.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: `PathSnapshot`, a complete unsigned `InstallPlan`, versioned
  adapter operations, integrity/anchor brokers, and fixed installation/index
  locations.
- Produces: `plan_digest`, `verify_install_plan(...) -> VerifiedInstallPlan`,
  `apply_plan(plan: VerifiedInstallPlan, ...) -> VerifiedPreparedPublication`,
  `publish_installation(prepared: VerifiedPreparedPublication) ->
  VerifiedInstallationState`,
  `rollback_transaction(plan: VerifiedRollbackPlan, ...)`,
  `verify_uninstall(...) -> VerifiedUninstallPlan`,
  `uninstall_transaction(plan: VerifiedUninstallPlan)`, and
  `apply_finalization(plan: VerifiedFinalizationPlan)`,
  domain-authorized `VerifiedAnchorTransition` issuance,
  `verify_authority_retirement(...) -> VerifiedAuthorityRetirementPlan`, and
  `retire_authorities(plan: VerifiedAuthorityRetirementPlan)`.

- [ ] **Step 1: Write failing transaction tests**

Tests must cover no-write planning, ordered apply, readback mismatch, injected
failure after operation N, dependency-ordered retryable rollback, and uninstall
refusing to detach the runtime when restore fails. Add red cases proving the
digest changes with installation ID, either canonical root, source commit or
content identity, setup-body digest, authority-bootstrap descriptor/digest,
adapter-plan digest/order, and operation order; reject each broken DAG link,
sentinel/self-reference, and
cross-install/source replay and stale lifecycle/anchor state before the first
prepared journal record. Raw plans, raw receipts, raw indexes, raw snapshots,
and the wrong phase-specific verified type must fail at every mutation API.

Prove a prepared receipt is not committed state. Under an exclusive publication
lock, inject crashes/errors before and after every receipt write/fsync/rename,
publication-WAL fsync, full-candidate-index fsync, predecessor revalidation,
canonical-index replace, index-directory fsync, verified index readback, live
anchor CAS, and cleanup deletion. Before the verified index readback, the exact
old index/receipt mapping must remain authoritative; afterward the exact new
full mapping must. No recovery may expose a hybrid, infer an index from loose
receipts, choose by mtime, or acknowledge success before anchor/readback.
Exercise `EIO`/`ENOSPC`, same-generation forks, predecessor conflicts, missing
or extra receipt files, and two concurrent publishers.

Add first-key bootstrap crash tests before/after WAL fsync, add-only Keychain
dispatch, unknown add result, persistent-reference recording, commit intent,
first receipt/index publication, and WAL cleanup. Tamper every WAL/locator/
inverse/creator field; replay across installation/generation/machine; race two
first installers; seed a foreign item at the fixed locator; replace the item
between match and inverse. Recovery may discard an inert orphan WAL, delete
only the exact matching add result, adopt only through a valid published
receipt, and never use an unauthenticated WAL to choose a Keychain target.

Construct a verified installation index and prove that missing, duplicate,
foreign, unchecked, unexpected/omitted, digest-mismatched, or MAC-invalid
receipts and caller-selected subsets fail before any inverse/restore/detach.
Crash after every uninstall phase and require forward recovery through
`VERIFIED`, `UNINSTALLING_PUBLISHED`, `CREDENTIALS_RESTORED`,
`FILESYSTEM_RESTORED`, `RUNTIME_DETACHED`, `TOMBSTONE_PURGED`, and
`UNINSTALLED_PUBLISHED`. Partial tombstone purge resumes by verified object
identity. Raw cleanup paths/plans and changed finalizer targets fail before
deletion.

Add anchor-transition authorization tests at every installation publication
and lifecycle transition: raw namespace/old/new calls, forged or wrong-domain
capabilities, replay, correct-old/arbitrary-new commitment, changed bound WAL/
plan/receipt root, wrong native caller identity, and reuse after a state advance
must fail without broker mutation.

After `UNINSTALLED_PUBLISHED`, cover authority retirement phases
`RETIREMENT_VERIFIED`, `APPROVAL_RETIRED`, `ANCHORS_RETIRED`,
`RECOVERY_ITEMS_RETIRED`, `TERMINAL_ATTESTED`, `CONTROL_KEY_RETIRED`,
`RECEIPT_KEY_RETIRED`, `BROKER_RETIRED`, and `RETIREMENT_COMPLETE`. Inject a
crash before and after every Keychain deletion, absence readback, WAL fsync,
terminal-attestation write/signature/fsync, add-only protected terminal-pin
creation/readback, control-key deletion, receipt-key deletion, and
external-helper unlink/readback. Tamper/replay the plan, WAL, attestation,
public key, dependency order, persistent references, protected pin, or helper
object identity. After both keys are absent, replace/replay every ordinary
retirement artifact as one coordinated set; recovery must still deny unless
the live protected pin matches the exact attestation digest, receipt-public-key
digest, retired era, and helper identity/finalizer. Recovery must retain the
helper plus integrity and asymmetric receipt keys through attestation and pin
readback, delete the control key then receipt key, retain the protected pin as
a permanent non-authority retirement tombstone, and recognize already-completed
deletes without recreating an authority.
Validate both new authority-retirement schemas with the same base-field,
version, unknown-field retention, and `additionalProperties: true` contract as
Task 2.

```python
verified = verify_install_plan(raw_plan, expected_installation, live_anchor)
with self.assertRaises(TransactionError):
    apply_plan(verified, fail_after=1)
self.assertEqual(first_target.read_bytes(), b"before")
self.assertTrue((rollback_root / transaction_id / "journal.jsonl").exists())
```

Run:

```bash
rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest \
  tests.unit.test_transaction tests.unit.test_publication \
  tests.unit.test_finalization tests.unit.test_authority_retirement -v
```

Expected: FAIL because `harness_core.transaction` does not exist.

- [ ] **Step 2: Define deterministic operations**

Implement a frozen `Operation` with `kind`, trusted-root identity,
descriptor-relative target, parent/target witness, precondition, desired state,
readback predicate, and exact inverse. `plan_digest` is SHA-256 of the canonical
complete unsigned install plan. Compute its acyclic identity in three stages:
the bootstrap-independent `SetupBodyV1` digest; the authority-bootstrap
descriptor digest bound to that body; then the final plan digest containing
both. The final digest includes installation ID, canonical runtime and rollback
roots, exact source commit/content identity, ordered adapter-plan and
authority-bootstrap descriptor digests, and ordered operation JSON. Reject
duplicate canonical targets and
operation kinds outside the specification. One `credential-migrate` operation
may own multiple journaled internal phases for its one config target; adding any
second plan owner remains invalid. `signing-key-bootstrap-add` and permanent
finalizers are separate lifecycle operations, not ordinary adapter operations.
The digest/signature field itself is excluded; no other plan field is excluded.

`verify_install_plan` performs all parsing, schema, identity, containment,
source, lifecycle, operation, capability, and live-anchor checks and returns a
non-serializable `VerifiedInstallPlan`. No public mutation function overload
accepts `InstallPlan`, mappings, or paths.

- [ ] **Step 3: Implement write-ahead apply**

Immediately before the first journal write, recompute and compare the complete
plan digest and re-probe the expected installation, canonical roots, exact
source commit/content identity, setup-body digest, authority-bootstrap
descriptor digest, and every ordered adapter-plan digest. Reject any
identity/capability/anchor drift without mutation. Acquire the stable
installation transaction lock. On fresh setup, require the authority bootstrap
readback already equals the plan-bound initial pending-setup commitment; do not
advance it again. On upgrade/existing setup, issue one
`VerifiedAnchorTransition` from the verified install plan and exact
pending-plan WAL/commitment and consume it to advance the live installation
anchor. Retain trusted root/parent descriptors. Raw old/new commitments or a
transition from another domain cannot reach the broker. Then, for each
operation:

1. securely walk from the trusted root and capture parent/target witnesses plus
   the complete rollback snapshot;
2. append/fsync a `prepared` WAL record and its directory;
3. create/write/metadata-set/fsync an unpredictable descriptor-relative temp;
4. revalidate every retained witness and exact precondition;
5. use atomic no-clobber for absence or the verified safe CAS/exclusion
   primitive for an owned target;
6. fsync the retained parent directory;
7. open/read back the installed object with `O_NOFOLLOW`, require the expected
   object identity/digest/metadata, and revalidate root reachability;
8. append and fsync an `applied` record.

On any exception, append `apply-failed`, derive a one-use
`VerifiedRollbackPlan`, and execute dependency-ordered rollback. Never use
`shell=True` or fall back to pathname mutation. After all readbacks pass, write
and fsync immutable generation-qualified prepared receipts, construct/fsync the
authenticated publication WAL and full candidate index, and return
`VerifiedPreparedPublication`. Prepared receipts are not committed ownership
and apply does not report installation success.

- [ ] **Step 4: Publish atomically and implement forward-recoverable uninstall**

Implement first-key bootstrap as the first typed lifecycle transaction. A
`VerifiedBootstrapPlan` fixes the trusted Keychain locator, installation/
transaction/creator IDs, immutable expected attributes, WAL digest, and
conditional inverse. Generate the key only in memory; fsync an authenticated
bootstrap WAL; perform add-only `SecItemAdd`; persist/read back the returned
opaque reference and immutable markers; and let the first verified
receipt/index publication transfer ownership. Recovery queries the fixed
locator before trusting a WAL, discards only inert orphan WALs, deletes only an
exact matching add result, treats a foreign/pre-existing item as collision, and
never overwrites/upserts or silently mints a replacement for a published
missing key.

`publish_installation` holds the publication lock, verifies the candidate's
predecessor generation/digest against the canonical index, atomically replaces
the canonical index, fsyncs its directory, and loads it through the normal
fixed-location verifier. That verified index readback is the sole commit point.
It then issues and consumes the one-use publication-domain
`VerifiedAnchorTransition` bound to the exact WAL, verified index readback, and
receipt root before acknowledging success. Recovery completes only the exact
WAL transition; if the old index remains, prepared generations are uncommitted,
and if the new verified index remains, cleanup resumes. Never merge loose
receipts or infer committed state.

`VerifiedInstallationState` is produced only by loading the fixed
manifest-declared index, checking the live installation anchor, verifying its
separate MAC for the expected installation, scanning the receipt registry,
requiring an exact indexed bijection/count, and MAC-verifying every receipt into
`VerifiedAdapterReceipt`. `verify_uninstall` additionally binds current
lifecycle generation, exact runtime/rollback object identities, recovery
dependencies, tombstone target, and typed finalizers into
`VerifiedUninstallPlan`. No uninstall API accepts receipt paths, raw state, or a
caller subset.

Implement uninstall as authenticated, idempotent forward recovery through:

```text
VERIFIED
UNINSTALLING_PUBLISHED
CREDENTIALS_RESTORED
FILESYSTEM_RESTORED
RUNTIME_DETACHED
TOMBSTONE_PURGED
UNINSTALLED_PUBLISHED
```

Quiesce all launchers first. Load sealed recovery bytes while their items
exist; restore/verify credential config; execute/verify operational Keychain
inverses; restore/verify remaining files, symlinks, modes, uid/gid, ACLs, and
xattrs; then atomically rename the exact runtime directory object into the
external receipt-bound tombstone. Never call `shutil.rmtree` on the live
runtime path. Verify and consume a `VerifiedFinalizationPlan` to purge exact
tombstone entries incrementally, WAL each durable step, fsync parent
directories, and resume after crashes. Publish `UNINSTALLED_PUBLISHED` only
after purge verification. Recovery snapshots and the installation control key
remain until their last dependency and final authenticated lifecycle
transition.

Only after `UNINSTALLED_PUBLISHED`, verify a separate
`VerifiedAuthorityRetirementPlan` binding the exact authority manifest,
persistent references/fixed locators, helper object identities, dependency
graph, current retired installation era, live anchor, and the fixed
non-synchronizing `ThisDeviceOnly` protected terminal-pin locator plus immutable
expected attributes. Execute its signed forward WAL through:

```text
RETIREMENT_VERIFIED
APPROVAL_RETIRED
ANCHORS_RETIRED
RECOVERY_ITEMS_RETIRED
TERMINAL_ATTESTED
CONTROL_KEY_RETIRED
RECEIPT_KEY_RETIRED
BROKER_RETIRED
RETIREMENT_COMPLETE
```

Retain the external native helper, installation control/integrity key, and
asymmetric broker receipt key through every earlier removal/readback. Before
removing them, fsync a redacted terminal attestation MAC-authenticated by the
control key and signed by the broker receipt key. It includes the receipt public
key plus the exact remaining key/helper finalizers and terminal-pin locator.
Before completing `TERMINAL_ATTESTED`, add-only create and read back the
protected terminal pin containing the attestation digest, receipt-public-key
digest, retired installation/authority era, and exact helper object
identity/finalizer digest. A foreign or mismatched item blocks retirement.

Remove/readback the control key, then the receipt key. From that boundary
onward, both public verification of the fixed attestation and live readback of
the matching protected pin are required to authorize the exact
descriptor-relative helper unlink/readback; no self-contained attestation,
mutable WAL flag, replayable manifest, or caller path is sufficient. The pin
survives as a permanent non-authority retirement tombstone and authorizes
nothing else. Recovery recognizes an already absent exact item, never recreates
authority state, and cannot claim another anchor transition. Any earlier
failure preserves the journal, rollback bundle, required signer/helper, and
tombstone for retry.

- [ ] **Step 5: Route legacy uninstall through the core**

Change `src/agent_harness.py:uninstall` into a compatibility facade that loads
fixed verified state, verifies/consumes `VerifiedUninstallPlan`, and resumes the
core phase machine. It never receives a caller runtime path, calls
`shutil.rmtree`, or bypasses typed finalization. Preserve recovery state and
print the exact resume/rollback command on failure.

Run: `rtk npm test`

Expected: existing lifecycle tests plus new failure-injection tests pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/harness_core/transaction.py src/harness_core/publication.py \
  src/harness_core/finalization.py src/harness_core/authority_retirement.py \
  src/harness_core/auth.py \
  tests/unit/test_transaction.py tests/unit/test_publication.py \
  tests/unit/test_finalization.py tests/unit/test_authority_retirement.py \
  runtime/schemas/authority-retirement-wal.v1.schema.json \
  runtime/schemas/terminal-authority-attestation.v1.schema.json \
  src/agent_harness.py
rtk git commit -m "feat: make install and uninstall transactional"
```

### Task 5: Add collision-safe canonical asset projection

**Files:**
- Create: `src/harness_core/assets.py`
- Create: `tests/unit/test_assets.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: canonical runtime assets, descriptor-bound destination observations, and a prior
  `VerifiedAdapterReceipt` bound to the expected installation, or `None` for a
  clean absent target.
- Produces: `plan_asset_projection(...) -> list[Operation]` and exact asset receipt entries.

- [ ] **Step 1: Write failing collision tests**

Cover absent destination, matching receipt-owned destination, unmanaged identical bytes, unmanaged different bytes, symlink collision, modified managed file, and idempotent reapply. Unmanaged paths must be skipped with a collision result even when `force=True`.
Add forged, edited, wrong-key, and wrong-installation receipt cases; each must
remain an unmanaged collision.
After each CREATE/UPDATE classification, inject target or parent creation,
replacement, and symlink substitution before apply; the transaction
precondition/witness must reject rather than overwrite.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_assets -v`

Expected: FAIL because projection planning is absent.

- [ ] **Step 2: Implement ownership decisions**

```python
def classify_target(observation: TargetObservation, desired_sha256: str,
                    receipt: VerifiedAdapterReceipt | None) -> TargetDecision:
    if observation.kind == "absent":
        return TargetDecision.CREATE
    if receipt and receipt.matches(observation):
        return TargetDecision.UPDATE_MANAGED
    return TargetDecision.COLLISION_UNMANAGED
```

Do not equate matching bytes with ownership. Emit a structured collision containing path, type, and current digest without file contents.
This API cannot parse or verify receipt JSON; its only receipt-bearing argument
is the verified type already bound to `AdapterContext.installation_id`.
Every emitted operation binds the trusted-root, parent, target-object, and
digest witnesses from the observation; apply revalidates them and uses
no-clobber/CAS rather than trusting the planning classification.

- [ ] **Step 3: Replace unconditional skill/agent copies**

Route `install_asset_files`, Cursor rule installation, opencode compatibility assets, and legacy Pi compatibility assets through projection planning. Remove direct `shutil.copy2` writes from adapter code.

- [ ] **Step 4: Verify restore preserves unmanaged paths**

Add a fixture-home integration scenario where same-named user skills and rules pre-exist. Setup must report collisions, leave hashes unchanged, and uninstall must preserve them.

Run: `rtk npm test`

Expected: all collision and lifecycle tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/assets.py tests/unit/test_assets.py src/agent_harness.py tests/run.sh
rtk git commit -m "feat: project canonical assets without collisions"
```

### Task 6: Require explicit repository enrollment

**Files:**
- Create: `src/harness_core/enrollment.py`
- Create: `tests/unit/test_enrollment.py`
- Modify: `src/agent_harness.py`
- Modify: `runtime/mcp/server.mjs`

**Interfaces:**
- Consumes: canonical repository path and Git identity probes.
- Produces: `enroll_repository`, `verify_enrollment`,
  `create_worktree_identity`, `verify_worktree_identity`,
  `VerifiedWorktreeIdentity`, and CLI/MCP `repo_enroll` / `repo_status`.

- [ ] **Step 1: Write failing enrollment tests**

Cover canonical symlink normalization, Git common-dir identity, immutable root
commit, normal branch/HEAD advancement, remote fingerprint, moved checkout,
changed remote, explicit re-enrollment, and task start refusal for an unenrolled
repository.
Create harness worktrees and cover their parent-enrollment binding, canonical
path, stable root object identity, worktree-specific Git-directory path/object
identity, common-directory path/object identity, immutable root/remote
identity, and random enrollment nonce. Add red cases for: an equivalent clone
replacing the exact path; two identical standalone clones swapped by rename; a
linked worktree recreated while reusing its Git-admin path; substitution by
another worktree sharing the common directory with its admin pointer rebound;
replacement of only the Git or common directory object; and a complete copied
marker/xattr. All must fail even when the legacy path/root/remote/Git-path tuple
matches. Normal branch checkout and worktree file changes must preserve
identity. Validation failures must leave every Git config/remote and enrollment
byte unchanged and never invoke repair/rebaseline.

```python
with self.assertRaisesRegex(EnrollmentError, "not enrolled"):
    require_enrollment(runtime, repo)
```

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_enrollment -v`

Expected: FAIL because enrollment is absent.

- [ ] **Step 2: Implement identity records**

Use `git rev-parse --path-format=absolute --git-common-dir`,
`git rev-list --max-parents=0 HEAD`, and a SHA-256 fingerprint of the normalized
remote URL with credential/userinfo removed. Store no remote credentials.
Changing HEAD alone must not invalidate an enrollment.
Open the canonical repository root directory without following symlinks and
record its stable filesystem object ID. Resolve/open and record stable IDs for
the worktree-specific Git directory and common directory as well. POSIX uses at
least `(st_dev, st_ino)` plus a reliable generation/birth identifier when
available; unsupported strong identity is a fail-closed capability.

For each harness-created worktree, also resolve
`git rev-parse --path-format=absolute --git-dir` and persist a versioned
immutable identity containing the parent enrollment ID, canonical worktree
path/root object ID, worktree-specific Git-directory path/object ID, common
directory path/object ID, immutable root commit, remote fingerprint, and a
cryptographically random enrollment nonce. A nonce-bound xattr/marker is
optional defense in depth and never substitutes for object IDs. Keep the
authoritative record in owner-only harness state.

`verify_worktree_identity` opens and `fstat`s the root, resolves/opens both Git
directories, compares every path/object/provenance field from one consistent
probe, and then proves the pathname still resolves to the retained root object.
It returns a non-forgeable `VerifiedWorktreeIdentity` carrying the retained
handle or an immediately expiring witness. Any mismatch requires explicit
re-enrollment; verification never refreshes fields, creates a marker, changes
Git config/remotes, or runs `git worktree repair`. Matching only paths, root
commit/remote, or the shared common directory is insufficient.

- [ ] **Step 3: Add explicit CLI commands**

Add:

```text
agent-harness repo enroll --repo PATH --confirm --json
agent-harness repo status --repo PATH --json
agent-harness repo remove --repo PATH --confirm --json
```

Non-interactive enrollment requires `--confirm`; discovery cannot imply consent.

- [ ] **Step 4: Gate task entry points**

Require a valid enrollment in `start_task` and `make_worktree`, then create and
persist the immutable worktree identity. Require complete identity
revalidation in `resume_task`, writer launch profiles, and immediately before
every lease acquire/renew/recovery, handoff, and mutable operation, carrying the
retained verified root capability into descriptor-relative dispatch. Keep
read-only doctor/plan commands available and
return stable reason codes `repo-not-enrolled` or
`worktree-identity-mismatch`.

Update the MCP tools and fixture setup to enroll disposable repositories explicitly.

Run: `rtk npm test`

Expected: negative unenrolled tests fail closed and existing flows pass after explicit fixture enrollment.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/enrollment.py tests/unit/test_enrollment.py src/agent_harness.py runtime/mcp/server.mjs tests/run.sh
rtk git commit -m "feat: require explicit repository enrollment"
```

### Task 7: Introduce the adapter protocol and Codex adapter

**Files:**
- Create: `src/harness_core/adapters/__init__.py`
- Create: `src/harness_core/adapters/base.py`
- Create: `src/harness_core/adapters/codex.py`
- Create: `tests/unit/test_adapter_codex.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: `AdapterContext`, core transactions, assets, and contracts.
- Produces: `HostAdapter` protocol, `discover_host_adapters`, and Codex plan/report objects.

- [ ] **Step 1: Write failing capability and plan tests**

Test `CODEX_HOME` precedence, `AGENTS.override.md` selection, version probe
validation, three standalone profile plans, per-run override serialization,
canonical skill projection, byte-exact base-config preservation, profile-name
collision, malformed base-config refusal, and no direct writes during planning.
Pass only `VerifiedAdapterReceipt` values into update/verification/removal and
add raw mapping, forged value, and wrong-installation red cases that fail
before planning or mutation.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_adapter_codex -v`

Expected: FAIL because the adapter protocol and Codex adapter are absent.

- [ ] **Step 2: Define the shared protocol**

```python
@dataclass(frozen=True)
class AdapterContext:
    home: Path
    runtime: Path
    source_commit: str
    installation_id: str
    repo: Path | None
    env: Mapping[str, str]

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

`AdapterContext.installation_id` is the expected installation binding.
Lifecycle orchestration parses and verifies raw receipt documents before
calling an adapter. No adapter ownership, update, verification, restore, or
removal method accepts a raw mapping or receipt path.

- [ ] **Step 3: Implement Codex discovery and planning**

Require `codex --version` output to identify Codex. Plan managed instructions,
canonical skills, and three receipt-owned
`$CODEX_HOME/agent-harness-{read,worktree-write,yolo}.config.toml` files.
The profile files contain only harness overlay values for MCP, hooks when the
probed version supports them, sandbox, and approval behavior; the wrapper
selects them with `--profile` and later launch manifests add task-specific
values through `--config`. Never rewrite the user's base `config.toml`.
Run a read-only Codex config/capability probe before apply and reject malformed
base config or colliding unmanaged profile files without mutation.

- [ ] **Step 4: Replace the legacy Codex installer**

Make `install_codex_adapters` a compatibility wrapper that requests a plan and transaction apply. Its returned JSON includes plan digest, receipt path, capability version, and collisions.

Run: `rtk npm test`

Expected: Codex unit/integration tests and existing adapter assertions pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/adapters src/harness_core/assets.py tests/unit/test_adapter_codex.py src/agent_harness.py tests/run.sh
rtk git commit -m "feat: add transactional Codex adapter"
```

### Task 8: Add Claude Code and Cursor adapters

**Files:**
- Create: `src/harness_core/adapters/claude.py`
- Create: `src/harness_core/adapters/cursor.py`
- Create: `tests/unit/test_adapter_claude.py`
- Create: `tests/unit/test_adapter_cursor.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: shared adapter protocol and transaction engine.
- Produces: Claude and Cursor capability-aware plans and host reports.

- [ ] **Step 1: Write failing Claude tests**

Cover `CLAUDE_CONFIG_DIR`, `CLAUDE.md` bridge, settings precedence, deny/ask/allow semantics, sandbox `failIfUnavailable`, strict MCP, required hook merge, invalid JSON refusal, resume flag replay, and preservation of user arrays.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_adapter_claude -v`

Expected: FAIL because the Claude adapter is absent.

- [ ] **Step 2: Implement the Claude adapter**

Plan only managed blocks/entries with receipts. Required harness launches set sandbox enabled, `failIfUnavailable: true`, `allowUnsandboxedCommands: false`, strict network allowlist, and strict MCP. Verification checks version/auth/doctor plus required hook and MCP readback without printing credentials.

- [ ] **Step 3: Write failing Cursor tests**

Cover exact Cursor CLI identity (reject unrelated `agent`), native `.mdc` format, `failClosed: true` hooks, CLI permission merge, existing MCP JSON, IDE-vs-CLI capability fields, invalid JSON refusal, and collision preservation.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_adapter_cursor -v`

Expected: FAIL because the Cursor adapter is absent.

- [ ] **Step 4: Implement the Cursor adapter**

Probe `agent --version` and `cursor-agent --version` but accept only Cursor-identifying output. Install native hooks and MCP independently so an existing MCP entry cannot skip hooks. Project artifacts require enrolled/trusted repositories and are receipt-owned.

- [ ] **Step 5: Route legacy functions through both adapters**

Replace direct writes in `install_claude_adapters` and `install_cursor_adapters` with plan/apply calls. Add receipt-based removal and host reports.

Run: `rtk npm test`

Expected: both adapter suites, malformed-config negatives, and lifecycle integration pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/harness_core/adapters/claude.py src/harness_core/adapters/cursor.py tests/unit/test_adapter_claude.py tests/unit/test_adapter_cursor.py src/agent_harness.py tests/run.sh
rtk git commit -m "feat: add transactional Claude and Cursor adapters"
```

### Task 9: Add a native Oh My Pi adapter

**Files:**
- Create: `src/harness_core/adapters/omp.py`
- Create: `runtime/mcp/omp-extension.ts`
- Create: `runtime/bin/ah-omp`
- Create: `tests/unit/test_adapter_omp.py`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: OMP `omp` CLI, read-only user configuration, a runtime-owned
  repeatable `--config` overlay, project `.omp` resources, and OMP RPC.
- Produces: OMP adapter plan/report, policy extension, wrapper, and peer capability.

- [ ] **Step 1: Write failing identity and configuration tests**

Require `omp --version` to identify Oh My Pi; prove a `pi` executable alone
does not activate this adapter. Cover repeatable overlay precedence, byte-exact
owner YAML preservation, malformed owner YAML refusal without rewrite,
cwd-only project config, native `.omp/AGENTS.md`, extension projection, skills,
and legacy `PI_CODING_AGENT_DIR` readback without treating it as Pi.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_adapter_omp -v`

Expected: FAIL because the OMP adapter is absent.

- [ ] **Step 2: Implement OMP plan and verification**

Plan a thin global instruction reference, policy extension, canonical skills,
wrapper, and harness-owned YAML overlay beneath the runtime. Pass the overlay
with OMP's repeatable `--config` flag; never round-trip or rewrite the user's
YAML. Invalid user YAML is a required-launch failure with no mutation. Do not
install `~/.pi` artifacts. Host report distinguishes CLI, config, RPC protocol,
auth, and extension health.

- [ ] **Step 3: Implement RPC lifecycle handling**

The wrapper must wait for `ready`, negotiate the supported protocol, enforce physical/reassembled frame limits, correlate request IDs, and treat `agent_settled`—not prompt acceptance—as completion. Unknown frames are retained in redacted evidence.

- [ ] **Step 4: Add OMP peer support**

Add `omp` to `agent_capabilities`, `wrapper_for`, parser choices, and conductor host limits. The initial implementation may run one OMP lane; the 4-lane ceiling is implemented in the scheduler plan.

Run: `rtk npm test`

Expected: OMP detection/config/RPC tests pass; upstream Pi-only fixtures remain unselected.

- [ ] **Step 5: Commit**

```bash
rtk git add src/harness_core/adapters/omp.py runtime/mcp/omp-extension.ts runtime/bin/ah-omp tests/unit/test_adapter_omp.py src/agent_harness.py tests/run.sh
rtk git commit -m "feat: add native OMP adapter"
```


### Task 10: Migrate plaintext credentials to native auth references

**Files:**
- Create: `src/harness_core/credentials.py`
- Create: `tests/unit/test_credentials.py`
- Modify: `src/harness_core/adapters/codex.py`
- Modify: `src/harness_core/adapters/claude.py`
- Modify: `src/harness_core/adapters/cursor.py`
- Modify: `src/harness_core/adapters/omp.py`
- Modify: `src/harness_core/fsmeta.py`
- Modify: `src/harness_core/transaction.py`
- Modify: `runtime/schemas/adapter-plan.v1.schema.json`
- Modify: `runtime/schemas/adapter-receipt.v1.schema.json`
- Modify: `src/agent_harness.py`

**Interfaces:**
- Consumes: adapter-declared credential fields, host native-auth health, synthetic secret bytes, and transaction engine.
- Produces: `inventory_credentials`, `plan_credential_migration`,
  `resolve_credential_reference`, one composite
  `CredentialMigrationOperation` per config target, narrow authenticated
  `keychain-add`, `keychain-delete`, and `keychain-replace` operations with
  receipt-owned inverses, and verified final replacement of plaintext sources.

- [ ] **Step 1: Write failing synthetic-secret tests**

Seed fixture configs and environments with unique synthetic canaries. Cover
already-healthy OAuth, explicitly approved user-authored fields, unsupported
credential fields, Keychain store failure, sealed-snapshot failure, host auth
verification failure, config reference write failure, rollback, uninstall
restore, and successful migration. Scan returned objects, ordinary rollback
objects, journals, receipts, logs, errors, and Git diff; the canary must never
appear.
Before production changes, add explicit red cases for put of a new item,
replacement and deletion of an existing item, crash after the Keychain write
but before the applied journal record, post-write/delete readback mismatch,
failed-apply inverse failure, and uninstall. Assert the prepared record contains
only a sealed before-state reference/digest and redacted service/account
identity, never secret bytes or a secret-derived fingerprint.

For a credential reference and plaintext field in the same config file, prove
that separate `write-reference(config)` and `remove-plaintext(config)` plan
nodes are rejected as duplicate owners while one composite
`credential-migrate(config)` node is accepted. Inject failure/crash at every
internal phase and assert this dependency order: quiesce runtime; load sealed
source bytes; restore/readback the config; execute/readback the exact
operational Keychain inverse; restore remaining filesystem state; delete
recovery snapshot items last. Early bulk deletion of recovery-purpose items
must fail. Repeated recovery/uninstall is idempotent and retains the control key
through the final lifecycle publication.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_credentials -v`

Expected: FAIL because credential inventory and sealed migration are absent.

- [ ] **Step 2: Define reference-only records**

```python
@dataclass(frozen=True)
class CredentialReference:
    backend: Literal["native-auth", "macos-keychain", "owner-file"]
    service: str
    account: str
    env_name: str | None

@dataclass(frozen=True)
class CredentialFinding:
    finding_id: str
    host: str
    source_path: str
    field_path: tuple[str, ...]
    opaque_source_version: str
    supported_reference: bool
```

Plans and reports carry only the random finding ID, redacted field/reference
identity, and a sealer-issued opaque source-version handle. They never carry a
secret or secret-derived digest/fingerprint. Unknown or unsupported plaintext
fields are strict failures and remain untouched. An approved finding also
carries a broker-validated sealed snapshot reference for the complete original
source file; the reference contains no secret bytes and is purpose-tagged
`recovery`.

- [ ] **Step 3: Implement authenticated write-ahead Keychain operations**

If the host reports healthy native OAuth, remove only the exact,
broker-version-approved plaintext finding under a transaction, regardless of whether
the source was originally user-authored or harness-managed. Otherwise express
each Keychain put, delete, or replacement as a typed transaction operation.
Before dispatch, seal the existing item when present and fsync a prepared record
containing only its opaque reference, `operational`/`recovery` purpose, redacted
identity, broker operation ID, and exact conditional inverse. Supply secret
bytes through an in-memory narrow Keychain broker—never argv, a generic signing
API, or a journal field. After dispatch, have the broker re-read and compare
presence/value/metadata in protected memory and return an opaque attestation
before appending `applied`; persist no value digest. The MAC-authenticated
receipt owns only the exact add result or sealed prior item. The owner-file
fallback is `0600` outside the runtime, cannot authorize production writes, and
creates a strict-doctor qualification failure.

- [ ] **Step 4: Probe an isolated candidate, then perform one final rewrite**

Before any source mutation, seal the complete original file through a
Keychain-backed recovery snapshot and persist only its opaque reference in the
rollback journal. Execute one composite operation with authenticated internal
states:

```text
PREIMAGED
DESTINATION_APPLIED
CANDIDATE_PROBE_PASSED
FINAL_REWRITE_APPLIED
COMMITTED
```

After Keychain broker readback, generate a reference-only candidate
configuration in an isolated verifier-owned location and run the host health
probe against that candidate. Do not mutate the production configuration for
the probe. Only a passing isolated probe permits one descriptor-relative atomic
production rewrite that simultaneously installs the reference and removes the
approved plaintext field; verify the complete desired config before commit.

On failure or uninstall, quiesce the runtime, load the sealed original while
recovery items exist, restore and verify the complete production configuration
first, then execute/readback the exact operational Keychain inverse, restore
remaining filesystem state, and delete recovery-purpose items only after their
last consumer. A failed inverse cannot report rollback success. A successful
migration retains sealed before-state references until verified uninstall/final
cleanup. Keep the installation control key through final lifecycle
publication. Re-read the source after the final rewrite and prove the canary is
absent without printing bytes or a durable fingerprint.

- [ ] **Step 5: Add digest-bound CLI flow**

Support `credentials plan --json` and `credentials apply --plan PATH --expect-digest SHA256 --confirm --json`. MCP and non-interactive agents may inspect findings but cannot approve migration.
`apply` parses the file only as input to full current-state verification and
passes the resulting phase-specific verified credential plan to the transaction
engine; the raw path/document never authorizes mutation. `--confirm` is honored
only from the protected local interactive approval path, never MCP or redirected
stdin.

Run:

```bash
rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_credentials -v
rtk npm test
```

Expected: every failure restores the synthetic source, successful migration passes host-auth readback, and leak scans find no canary.

- [ ] **Step 6: Commit**

```bash
rtk git add src/harness_core/credentials.py src/harness_core/fsmeta.py src/harness_core/transaction.py runtime/schemas/adapter-plan.v1.schema.json runtime/schemas/adapter-receipt.v1.schema.json tests/unit/test_credentials.py src/harness_core/adapters src/agent_harness.py tests/run.sh
rtk git commit -m "feat: migrate credentials to native references"
```

### Task 11: Integrate manifests, migrations, setup, upgrade, and uninstall

**Files:**
- Create: `src/harness_core/install.py`
- Create: `src/harness_core/migrations.py`
- Create: `tests/unit/test_install_lifecycle.py`
- Modify: `bin/agent-harness`
- Modify: `src/harness_core/auth.py`
- Modify: `src/agent_harness.py`
- Modify: `INSTALL.md`

**Interfaces:**
- Consumes: all foundation modules and adapter implementations.
- Produces: `plan_setup`, protected first-use authority bootstrap/resolution,
  `verify_setup_plan`, `apply_setup(VerifiedInstallPlan)`,
  `publish_setup(VerifiedPreparedPublication)`, `plan_upgrade`,
  `load_verified_installation(expected_installation_id)`, lifecycle health
  inputs, indexed receipt-complete uninstall with no caller receipt subset, and
  protected typed authority retirement after `UNINSTALLED_PUBLISHED`.

- [ ] **Step 1: Write failing clean and legacy lifecycle tests**

Cover generated installation UUID, explicit workspace manifest, pure no-write
plan, apply, idempotent reapply, partial failure, version-one migration,
malformed/newer manifest refusal, missing/wrong installation key, receipt
tamper, an incompatible default Python with an explicit compatible
interpreter, uninstall restore failure, successful sealed-secret restore, and
reinstall of the same source commit.
Cover fresh protected authority provisioning, existing valid authority reuse,
foreign fixed-locator collision, incomplete bootstrap forward recovery,
noninteractive first install refusal, native broker code-identity mismatch,
approval/anchor item replacement, and file-backed authority rejection before
the installation transaction begins.
Before production changes, add red cases for cross-install and cross-source
plan replay; changed canonical runtime/rollback root; changed source content at
the same claimed commit; changed adapter-plan digest/order; missing, duplicate,
foreign, unchecked, unexpected/omitted, or digest-mismatched indexed receipts;
and caller attempts to pass a receipt subset. Assert every case fails before
the first apply, restore, Keychain inverse, or removal operation as applicable.
Integrate the Task 4 crash matrix: setup/upgrade must expose exactly the old or
new full index/receipt generation at every publication crash point, bootstrap
must be add-only/collision-safe, replaying an older but internally valid
index/receipt/WAL set must fail the live installation anchor, and uninstall
must resume every published phase through atomic runtime detach and typed
tombstone purge. Authority retirement must then resume every phase through
publicly verifiable terminal attestation, ordered key deletion, and exact helper
removal. Prove raw lifecycle/retirement plans and raw cleanup inventories never
reach mutation, and prove raw/correct-old-arbitrary-new anchor requests never
advance.

Run: `rtk env PYTHONPATH=src "$AGENT_HARNESS_PYTHON" -m unittest tests.unit.test_install_lifecycle -v`

Expected: FAIL because integrated lifecycle orchestration is absent.

- [ ] **Step 2: Implement install orchestration**

```python
def plan_setup(request: SetupRequest) -> InstallPlan:
    manifest = propose_manifest(request)
    adapter_plans = tuple(
        adapter.plan_install(
            request.context,
            request.verified_installation.receipt_for(adapter.host)
            if request.verified_installation else None,
        )
        for adapter in request.adapters
    )
    setup_body = SetupBodyV1(
        installation_id=manifest.installation_id,
        runtime_root=manifest.canonical_runtime_root,
        rollback_root=manifest.canonical_rollback_root,
        source_identity=request.source_identity,
        adapter_plan_digests=tuple(plan.digest for plan in adapter_plans),
        operations=merge_plans(
            (request.authority_projection_plan, *adapter_plans)
        ),
    )
    bootstrap = plan_authority_bootstrap(
        setup_body.digest,
        request.authority_bootstrap_requirements,
    )
    return InstallPlan.from_body(
        setup_body,
        authority_bootstrap=bootstrap,
    )
```

`propose_manifest` is pure: request-supplied/injected clock and identity inputs
determine its output, and it writes nothing. It accepts only a recomputed
`SourceContentIdentityV1` from the clean frozen snapshot and every build/apply
consumer reads that snapshot rather than excluded ambient files.

`verify_setup_plan` revalidates the approved complete unsigned-plan digest,
installation ID, trusted runtime/rollback roots and object identities, exact
source commit/content identity, the ordered setup-body/bootstrap-descriptor/
final-plan digest DAG, ordered adapter-plan digests, operation witnesses/
capabilities, lifecycle predecessor, and live installation anchor, then returns
`VerifiedInstallPlan`.

For first setup, the protected local interactive wrapper first reparses the
final install plan and exact bootstrap descriptor, calls Task 2's ordered
verifier to produce and consume `VerifiedAuthorityBootstrapPlan`,
forward-recovers or
provisions the fixed native authority state, verifies its readback/manifest,
and establishes the final-install-digest-bound initial live installation-anchor
generation/pending-setup commitment before signing-key or installation
mutation. It then
reparses and fully revalidates the unchanged complete setup plan against that
live anchor before producing `VerifiedInstallPlan`. Noninteractive setup may
reuse an already healthy pinned authority but cannot provision, replace, or
rebaseline one. No installation operation or receipt is prepared between
authority bootstrap and this full revalidation.

`apply_setup` accepts only the resulting verified install type. It bootstraps or
resolves the separate installation integrity key through the Task 4 add-only
WAL protocol, projects/readback-verifies the exact bootstrap broker bytes into
the runtime as a core receipt, applies remaining operations, and produces immutable
generation-qualified prepared receipts plus `VerifiedPreparedPublication`.
`publish_setup` writes one full candidate index containing the exact ordered
core-authority and adapter receipt IDs, canonical paths, digests, count,
transaction/generation, and
predecessor index digest, then performs the publication lock/CAS, atomic
replace, directory fsync, verified readback, and live-anchor advance. Receipt
and index publication are one protocol; no receipt is independently committed
and no success is returned between those steps. Setup JSON returns
`plan_digest`, `transaction_id`, `installation_id`, committed index
generation/root, receipts, collisions, failures, warnings, anchor receipt, and
rollback/resume command.

- [ ] **Step 3: Add explicit plan/apply CLI flow**

Support:

```text
agent-harness setup plan ... --json
agent-harness setup apply --plan PATH --expect-digest SHA256 --json
agent-harness upgrade plan ... --json
agent-harness upgrade apply --plan PATH --expect-digest SHA256 --json
agent-harness uninstall plan --retire-authorities --json
agent-harness uninstall apply --plan PATH --expect-digest SHA256 --confirm --json
```

Each apply command parses the file, performs complete current-state
verification, and passes only `VerifiedInstallPlan` to apply; the path, raw
document, and digest match alone never authorize mutation. Keep legacy one-shot
setup only as a protected local interactive wrapper that prints the plan and
asks before verification/apply. Non-interactive use requires the expected
digest and all verification gates but cannot synthesize protected approval.
On first setup, only that protected local path may consume the distinct
`VerifiedAuthorityBootstrapPlan`; after authority readback it must reverify the
unchanged install-plan digest before normal apply. The noninteractive command
fails with `authority-not-provisioned` rather than creating one.
`--retire-authorities` binds the post-uninstall retirement graph into the
reviewed plan but cannot run it early. Its apply path consumes
`VerifiedUninstallPlan` through `UNINSTALLED_PUBLISHED`, then independently
verifies/consumes `VerifiedAuthorityRetirementPlan`. It is the only supported
lost-approval-key remediation when the remaining retirement authorities are
healthy.

Reuse the already validated canonical `AGENT_HARNESS_PYTHON` binding; reject any
path/version drift and record it as the installed interpreter. Generated shims
execute that exact canonical interpreter plus the source entrypoint; they must
not delegate back to an incompatible `#!/usr/bin/env python3`.
Direct source entrypoints fail early with a clear version error.

- [ ] **Step 4: Expose lifecycle health inputs**

Return structured findings for schema versions, source commit, modes, receipt
MACs, installation-index completeness, uid/gid and symlink-aware metadata
readback, adapter readback, enrollment/worktree identity integrity, transaction
state, publication/bootstrap/uninstall WAL recovery, canonical index versus live
installation anchor, descriptor-relative primitive availability, protected
authority health, typed-finalizer state, and rollback availability. Preserve the existing doctor command as a
compatibility facade; the aggregate strict-doctor policy is implemented in the
release plan.

- [ ] **Step 5: Update install documentation and run the lifecycle gate**

Document no-write planning, digest-bound apply, enrollment, strict doctor, fail-safe uninstall, and rollback retry.

Run:

```bash
rtk npm test
rtk npm run preflight
rtk git diff --check
```

Expected: full lifecycle, source preflight, and diff checks pass.

- [ ] **Step 6: Commit**

```bash
rtk git add src/harness_core/install.py src/harness_core/migrations.py src/harness_core/auth.py tests/unit/test_install_lifecycle.py bin/agent-harness src/agent_harness.py INSTALL.md
rtk git commit -m "feat: integrate transactional harness lifecycle"
```
