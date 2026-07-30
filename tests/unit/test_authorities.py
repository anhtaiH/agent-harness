from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import hmac
import json
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import harness_core.auth as auth_module
import harness_core.authorities as authorities_module
from harness_core.auth import (
    IntegrityError,
    create_test_integrity_authority,
    load_installation_state,
)
from harness_core.authorities import (
    AUTHORITY_BOOTSTRAP_CRASH_POINTS,
    APPROVAL_KEY_LOCATOR,
    AuthorityBootstrapDescriptor,
    AuthorityBootstrapRequirements,
    AuthorityError,
    CapabilityFailure,
    InjectedAuthorityCrash,
    LiveAnchorBroker,
    SetupBodyV1,
    VerifiedAnchorTransition,
    bootstrap_authority,
    build_final_install_plan,
    create_test_approval_authority,
    create_test_live_anchor_broker,
    final_install_plan_digest,
    issue_installation_anchor_transition,
    plan_authority_bootstrap,
    protected_interaction_for_test,
    recover_authority_bootstrap,
    verify_authority_bootstrap,
)
from harness_core.contracts import (
    canonical_json_bytes,
    new_document,
    require_document,
)
from tests.unit.support import (
    ANCHOR_COMMITMENT,
    CREATED_AT,
    INSTALLATION_ID,
    MemoryAuthorityBackend,
    OTHER_ANCHOR_COMMITMENT,
    OTHER_INSTALLATION_ID,
    ROLLBACK_ROOT,
    RUNTIME_ROOT,
)


BROKER_CODE_IDENTITY = "native-broker-code-v1"
BROKER_CONTENT_DIGEST = "b" * 64
CREATOR_ID = "creator-123"
NAMESPACE = "agent-harness.installation-anchor.v1"
CALLER_CODE_IDENTITY = "transaction-engine-code-v1"
APPROVAL_NOW = 1_785_328_496


def source_identity() -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "algorithm_version": 1,
        "inclusion_policy": "git-tracked-clean-tree",
        "policy_version": 1,
        "ordered_manifest_digest": "c" * 64,
        "source_commit": "a" * 40,
        "frozen_snapshot_digest": "d" * 64,
        "digest": "e" * 64,
        "entries": [],
    }


def setup_body(**changes: object) -> SetupBodyV1:
    values: dict[str, object] = {
        "installation_id": INSTALLATION_ID,
        "runtime_root": RUNTIME_ROOT,
        "rollback_root": ROLLBACK_ROOT,
        "source_identity": source_identity(),
        "adapter_plan_digests": ("f" * 64,),
        "operations": (
            {
                "kind": "write-file",
                "target": ".codex/AGENTS.md",
                "digest": "1" * 64,
            },
        ),
    }
    values.update(changes)
    return SetupBodyV1(**values)


def requirements(wal_path: Path, **changes: object) -> AuthorityBootstrapRequirements:
    values: dict[str, object] = {
        "installation_id": INSTALLATION_ID,
        "creator_id": CREATOR_ID,
        "launcher_code_identity": BROKER_CODE_IDENTITY,
        "launcher_content_digest": BROKER_CONTENT_DIGEST,
        "native_broker_code_identity": BROKER_CODE_IDENTITY,
        "native_broker_content_digest": BROKER_CONTENT_DIGEST,
        "wal_locator": str(wal_path),
        "initial_anchor_namespace": NAMESPACE,
        "initial_anchor_generation": 0,
        "initial_anchor_commitment": ANCHOR_COMMITMENT,
    }
    values.update(changes)
    return AuthorityBootstrapRequirements(**values)


def complete_plan(wal_path: Path, body: SetupBodyV1 | None = None):
    body = body or setup_body()
    descriptor = plan_authority_bootstrap(body.digest, requirements(wal_path))
    plan = build_final_install_plan(body, descriptor, created_at=CREATED_AT)
    return body, descriptor, plan


class NativeControllerCapabilityTests(unittest.TestCase):
    def test_transient_key_is_explicitly_nonpersistent(self):
        class Bindings:
            attr_key_type = 11
            attr_key_size_in_bits = 12
            attr_is_permanent = 13
            key_type_ec_p256 = 14
            cf_boolean_false = 15
            dictionary_key_callbacks = 16
            dictionary_value_callbacks = 17

            def __init__(self):
                self.dictionary_pairs = []
                self.released = []

            def cf_number_create(self, *_):
                return 21

            def cf_dictionary_create(
                self,
                _allocator,
                keys,
                values,
                count,
                _key_callbacks,
                _value_callbacks,
            ):
                self.dictionary_pairs = list(
                    zip(list(keys)[:count], list(values)[:count])
                )
                return 22

            def sec_key_create_random_key(self, _attributes, _error):
                return 23

            def sec_key_copy_public_key(self, _private_key):
                return 24

            def sec_key_copy_external_representation(
                self,
                _public_key,
                _error,
            ):
                return 25

            def data_bytes(self, _data):
                return b"\x04" + b"\x01" * 64

            def release(self, value):
                if value:
                    self.released.append(value)

        bindings = Bindings()
        with patch.object(
            authorities_module,
            "_SecurityBindings",
            return_value=bindings,
        ):
            key = authorities_module._TransientControllerKey.generate()
        self.assertIn(
            (bindings.attr_is_permanent, bindings.cf_boolean_false),
            bindings.dictionary_pairs,
        )
        self.assertEqual(len(key.public_key_der), 91)
        key.close()
        self.assertEqual(bindings.released.count(23), 1)

    def test_transient_key_failure_releases_and_consumes_private_ref(self):
        class Bindings:
            ecdsa_message_sha256 = 31

            def __init__(self):
                self.released = []

            def data(self, _message):
                return 32

            def sec_key_create_signature(
                self,
                _private_key,
                _algorithm,
                _message,
                _error,
            ):
                return None

            def release(self, value):
                if value:
                    self.released.append(value)

        bindings = Bindings()
        key = authorities_module._TransientControllerKey(
            bindings,
            33,
            b"\x30\x59" + b"\x00" * 89,
        )
        for operation in (
            copy.copy,
            copy.deepcopy,
            pickle.dumps,
            json.dumps,
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(TypeError):
                    operation(key)
        with self.assertRaisesRegex(
            CapabilityFailure,
            "signature failed",
        ):
            key.sign_and_destroy(b"authorization")
        self.assertEqual(bindings.released.count(32), 1)
        self.assertEqual(bindings.released.count(33), 1)
        with self.assertRaisesRegex(CapabilityFailure, "already consumed"):
            key.sign_and_destroy(b"authorization")
        self.assertEqual(bindings.released.count(33), 1)


class AuthorityBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.wal = self.root / "authority-bootstrap.wal"
        self.backend = MemoryAuthorityBackend(code_identity=BROKER_CODE_IDENTITY)
        self.interaction = protected_interaction_for_test(
            origin="local-cli", stdin_is_tty=True, user_presence=True
        )
        self.body, self.descriptor, self.plan = complete_plan(self.wal)

    def tearDown(self):
        self.temp.cleanup()

    def verify(self, *, backend=None, plan=None, descriptor=None):
        backend = backend or self.backend
        descriptor = descriptor or self.descriptor
        return verify_authority_bootstrap(
            plan or self.plan,
            descriptor.to_document()
            if hasattr(descriptor, "to_document")
            else descriptor,
            expected_installation_id=INSTALLATION_ID,
            observations=backend.observe(descriptor.locators),
        )

    def assert_rejected_before_mutation(self, plan, descriptor=None):
        with self.assertRaises((AuthorityError, ValueError, TypeError)):
            verify_authority_bootstrap(
                plan,
                (descriptor or self.descriptor).to_document(),
                expected_installation_id=INSTALLATION_ID,
                observations=self.backend.observe(
                    (descriptor or self.descriptor).locators
                ),
            )
        self.assertEqual(self.backend.provision_calls, 0)
        self.assertFalse(self.wal.exists())

    def test_serialized_descriptor_rejects_invalid_native_role_pins(self):
        cases = {
            "launcher-code-hash": (
                "launcher_code_directory_hash",
                "g" * 40,
            ),
            "broker-code-hash": (
                "native_broker_code_directory_hash",
                "e" * 39,
            ),
            "controller-key": (
                "controller_public_key_digest",
                "C" * 64,
            ),
            "provider": ("authority_provider", "caller-selected"),
            "profile": ("verifier_mode", "debug"),
        }
        for case, (field, changed) in cases.items():
            with self.subTest(case=case):
                document = self.descriptor.to_document()
                document[field] = changed
                with self.assertRaises(AuthorityError):
                    AuthorityBootstrapDescriptor.from_document(document)

    def test_setup_body_descriptor_and_final_plan_form_acyclic_hash_dag(self):
        self.assertEqual(self.descriptor.setup_body_digest, self.body.digest)
        self.assertEqual(
            self.plan["authority_bootstrap_digest"], self.descriptor.digest
        )
        self.assertEqual(self.plan["plan_digest"], final_install_plan_digest(self.plan))
        verified = self.verify()
        self.assertEqual(verified.setup_body_digest, self.body.digest)
        self.assertEqual(verified.descriptor_digest, self.descriptor.digest)
        self.assertEqual(verified.pending_plan_commitment, self.plan["plan_digest"])
        incomplete_source = source_identity()
        incomplete_source.pop("entries")
        with self.assertRaisesRegex(AuthorityError, "source identity is incomplete"):
            replace(self.body, source_identity=incomplete_source).digest

    def test_verified_bootstrap_owns_an_immutable_detached_snapshot(self):
        verified = self.verify()
        original = self.descriptor.to_document()

        descriptor_view = verified.descriptor
        descriptor_view.locator_map["approval_key"] = "attacker-controlled"
        descriptor_view.item_attributes["approval_key"]["access"] = "attacker"
        descriptor_view.conditional_inverses[0]["locator"] = "attacker-controlled"

        self.assertEqual(verified.descriptor.to_document(), original)
        self.assertEqual(verified.descriptor_digest, self.descriptor.digest)
        self.assertEqual(verified.pending_plan_commitment, self.plan["plan_digest"])
        for field_name in (
            "setup_body_digest",
            "descriptor_digest",
            "pending_plan_commitment",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaises(AttributeError):
                    setattr(verified, field_name, "0" * 64)

        manifest = bootstrap_authority(
            verified, self.backend, interaction=self.interaction
        )
        self.assertEqual(manifest["bootstrap_digest"], self.descriptor.digest)
        signature = manifest["broker_signature"]
        unsigned_manifest = {
            key: value
            for key, value in manifest.items()
            if key != "broker_signature"
        }
        self.assertTrue(
            self.backend.verify_receipt(
                canonical_json_bytes(unsigned_manifest), signature
            )
        )
        provisioned_locators = (
            locator
            for name, locator in self.descriptor.locator_map.items()
            if name != "terminal_pin"
        )
        for locator in provisioned_locators:
            self.assertIsNotNone(self.backend.read_item(locator))
        self.assertIsNone(self.backend.read_item("attacker-controlled"))

    def test_broken_body_descriptor_or_final_plan_links_fail_before_side_effects(self):
        attacks: list[dict[str, object]] = []

        sentinel = copy.deepcopy(self.plan)
        sentinel["setup_body_digest"] = "PENDING"
        sentinel["plan_digest"] = final_install_plan_digest(sentinel)
        attacks.append(sentinel)

        changed_body = copy.deepcopy(self.plan)
        changed_body["runtime_root"] = "/changed/runtime"
        changed_body["plan_digest"] = final_install_plan_digest(changed_body)
        attacks.append(changed_body)

        omitted = copy.deepcopy(self.plan)
        del omitted["rollback_root"]
        omitted["plan_digest"] = final_install_plan_digest(omitted)
        attacks.append(omitted)

        changed_final = copy.deepcopy(self.plan)
        changed_final["operations"] = []
        attacks.append(changed_final)

        for attack in attacks:
            with self.subTest(attack=attack):
                self.assert_rejected_before_mutation(attack)

        other_body = setup_body(runtime_root="/other/runtime")
        other_descriptor = plan_authority_bootstrap(
            other_body.digest, requirements(self.wal)
        )
        cross_linked = copy.deepcopy(self.plan)
        cross_linked["authority_bootstrap"] = other_descriptor.to_document()
        cross_linked["authority_bootstrap_digest"] = other_descriptor.digest
        cross_linked["plan_digest"] = final_install_plan_digest(cross_linked)
        self.assert_rejected_before_mutation(cross_linked, other_descriptor)

    def test_raw_plan_flags_redirected_stdin_or_mcp_origin_cannot_provision(self):
        verified = self.verify()
        for raw in (self.plan, self.descriptor.to_document(), {"interactive": True}):
            with self.subTest(raw=raw):
                with self.assertRaises(TypeError):
                    bootstrap_authority(
                        raw, self.backend, interaction=self.interaction
                    )
        for interaction in (
            protected_interaction_for_test(
                origin="local-cli", stdin_is_tty=False, user_presence=True
            ),
            protected_interaction_for_test(
                origin="mcp", stdin_is_tty=True, user_presence=True
            ),
            protected_interaction_for_test(
                origin="local-cli", stdin_is_tty=True, user_presence=False
            ),
        ):
            with self.subTest(interaction=interaction):
                with self.assertRaisesRegex(CapabilityFailure, "protected local"):
                    bootstrap_authority(
                        self.verify(), self.backend, interaction=interaction
                    )
        self.assertEqual(self.backend.provision_calls, 0)
        self.assertFalse(self.wal.exists())
        self.assertIsNotNone(verified)

    def test_actual_final_plan_is_consumable_by_integrity_verifier(self):
        authority = create_test_integrity_authority(
            b"final-plan-contract-key",
            installation_id=INSTALLATION_ID,
        )
        verified = authority.verify_install_plan(
            self.plan,
            expected_installation_id=INSTALLATION_ID,
            expected_root=RUNTIME_ROOT,
        )
        self.assertEqual(verified.document["plan_digest"], self.plan["plan_digest"])

    def test_fixed_locators_are_add_only_and_foreign_items_collide(self):
        self.backend.items[APPROVAL_KEY_LOCATOR] = {"foreign": True}
        with self.assertRaisesRegex(AuthorityError, "collision"):
            self.verify()
        self.assertEqual(self.backend.items[APPROVAL_KEY_LOCATOR], {"foreign": True})
        self.assertEqual(self.backend.provision_calls, 0)

    def test_every_bootstrap_boundary_recovers_without_real_keychain_access(self):
        for crash_point in AUTHORITY_BOOTSTRAP_CRASH_POINTS:
            with self.subTest(crash_point=crash_point):
                case_root = self.root / crash_point
                case_root.mkdir()
                wal = case_root / "authority-bootstrap.wal"
                backend = MemoryAuthorityBackend(code_identity=BROKER_CODE_IDENTITY)
                _, descriptor, plan = complete_plan(wal)
                verified = verify_authority_bootstrap(
                    plan,
                    descriptor.to_document(),
                    expected_installation_id=INSTALLATION_ID,
                    observations=backend.observe(descriptor.locators),
                )
                with self.assertRaises(InjectedAuthorityCrash):
                    bootstrap_authority(
                        verified,
                        backend,
                        interaction=self.interaction,
                        fail_at=crash_point,
                    )
                recovered = recover_authority_bootstrap(
                    verify_authority_bootstrap(
                        plan,
                        descriptor.to_document(),
                        expected_installation_id=INSTALLATION_ID,
                        observations=backend.observe(descriptor.locators),
                        recovery=True,
                    ),
                    backend,
                    interaction=self.interaction,
                )
                self.assertEqual(recovered["bootstrap_digest"], descriptor.digest)
                self.assertEqual(
                    backend.read_item(APPROVAL_KEY_LOCATOR)["installation_id"],
                    INSTALLATION_ID,
                )

    def test_two_concurrent_provisioners_never_upsert_or_replace(self):
        first = self.verify()
        second = self.verify()

        def provision(capability):
            return bootstrap_authority(
                capability, self.backend, interaction=self.interaction
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.exception()
                for future in (
                    executor.submit(provision, first),
                    executor.submit(provision, second),
                )
            ]
        self.assertEqual(sum(error is None for error in results), 1)
        self.assertEqual(self.backend.provision_calls, 1)

    def test_code_identity_drift_and_copied_wal_are_rejected(self):
        verified = self.verify()
        self.backend.code_identity = "changed-broker-code"
        with self.assertRaisesRegex(CapabilityFailure, "code identity"):
            bootstrap_authority(
                verified, self.backend, interaction=self.interaction
            )
        self.assertFalse(self.wal.exists())

        self.backend.code_identity = BROKER_CODE_IDENTITY
        with self.assertRaises(InjectedAuthorityCrash):
            bootstrap_authority(
                self.verify(),
                self.backend,
                interaction=self.interaction,
                fail_at="after_wal_fsync",
            )
        copied = self.root / "copied.wal"
        shutil.copy2(self.wal, copied)
        with self.assertRaisesRegex(AuthorityError, "WAL locator"):
            recover_authority_bootstrap(
                self.verify(),
                self.backend,
                interaction=self.interaction,
                wal_path=copied,
            )
        self.assertEqual(self.backend.provision_calls, 0)

    @unittest.skipUnless(sys.platform == "darwin", "macOS native broker")
    def test_native_broker_compiles_and_self_tests_without_authority_mutation(self):
        root = Path(__file__).parents[2]
        fake_home = self.root / "fake-home"
        fake_home.mkdir()
        before = list(fake_home.iterdir())
        result = subprocess.run(
            [root / "runtime/bin/ah-authority", "--self-test"],
            cwd=root,
            env={
                **os.environ,
                "HOME": str(fake_home),
                "AGENT_HARNESS_AUTHORITY_SELF_TEST": "1",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"keychain_mutated":false', result.stdout)
        self.assertIn('"manifest_contract_valid":true', result.stdout)
        self.assertIn('"user_presence_requested":false', result.stdout)
        self.assertEqual(list(fake_home.iterdir()), before)

    def test_native_surface_attests_itself_and_exposes_only_narrow_commands(self):
        root = Path(__file__).parents[2]
        source = (root / "runtime/authority/macos-broker.swift").read_text()
        wrapper = (root / "runtime/bin/ah-authority").read_text()

        bootstrap_request = source.split("struct BootstrapRequest", 1)[1].split(
            "}", 1
        )[0]
        self.assertNotIn("brokerCodeIdentity", bootstrap_request)
        self.assertNotIn("brokerContentDigest", bootstrap_request)
        for command in (
            "--attest",
            "bootstrap",
            "bootstrap-recover",
            "health",
            "anchor-read",
            "anchor-compare-and-advance",
            "receipt-verify",
            "approval-sign",
            "approval-verify",
        ):
            with self.subTest(command=command):
                self.assertIn(f'case "{command}"', source)
        self.assertNotIn("AGENT_HARNESS_AUTHORITY_BINARY", wrapper)
        self.assertIn(
            'CACHE_ROOT="$ROOT/runtime/authority/.ah-authority-cache"',
            wrapper,
        )
        self.assertIn("BUILD_IDENTITY", wrapper)
        self.assertIn("cache_is_valid", wrapper)
        self.assertIn("func currentExecutableURL() throws -> URL", source)
        current_access = source.split(
            "func currentApplicationAccess()", 1
        )[1].split("func addSecureEnclaveKey", 1)[0]
        self.assertIn(
            "let executable = try currentExecutableURL()",
            current_access,
        )
        self.assertIn(
            "SecTrustedApplicationCreateFromPath($0, &trustedApplication)",
            current_access,
        )
        self.assertNotIn("nil, &trustedApplication", current_access)
        anchor_request = source.split("struct AnchorCASRequest", 1)[1].split(
            "}", 1
        )[0]
        self.assertIn("authorizationMac", anchor_request)
        self.assertIn("requireTransitionAuthorization(request)", source)
        self.assertIn("HMAC<SHA256>.isValidAuthenticationCode", source)
        self.assertIn("agent-harness.signing-key.v1", source)
        self.assertIn("requireApprovalEnvelope(envelope)", source)

    def test_fake_native_executable_exercises_restart_safe_protocol(self):
        factory = getattr(
            authorities_module, "open_test_native_authority_backend", None
        )
        self.assertIsNotNone(factory, "test native protocol factory is missing")
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        state = self.root / "fake-native-state.json"
        backend = factory(fake, state_path=state)
        self.assertFalse(backend.qualifying)
        self.assertTrue(backend.health()["healthy"])

        request = {
            "created_at": CREATED_AT,
            "installation_id": INSTALLATION_ID,
            "creator_id": CREATOR_ID,
            "descriptor_digest": "d" * 64,
            "final_plan_digest": "e" * 64,
            "wal_digest": "f" * 64,
            "anchor_namespace": NAMESPACE,
            "initial_anchor_generation": 0,
            "initial_anchor_commitment": ANCHOR_COMMITMENT,
        }
        manifest = backend.bootstrap(request)
        self.assertEqual(manifest["bootstrap_digest"], "d" * 64)
        restarted = factory(fake, state_path=state)
        self.assertEqual(
            restarted.recover_bootstrap(request)["broker_signature"],
            manifest["broker_signature"],
        )
        self.assertEqual(
            restarted.anchor_read(NAMESPACE),
            (0, ANCHOR_COMMITMENT),
        )
        with self.assertRaises(CapabilityFailure):
            restarted.approve(
                canonical_json_bytes({"intent": "native-test"}),
                b"native summary",
                protected_user_presence=True,
            )
        expires_at = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 300)
        )
        envelope = canonical_json_bytes(
            {
                "schema": "agent-harness/external-write-envelope",
                "schema_version": 1,
                "installation_id": INSTALLATION_ID,
                "intent_digest": "7" * 64,
                "predecessor_task_event_hash": "8" * 64,
                "expires_at": expires_at,
            }
        )
        summary = b"native summary"
        approval = restarted.approve(
            envelope, summary, protected_user_presence=True
        )
        self.assertTrue(restarted.verify_approval(envelope, summary, approval))
        self.assertFalse(
            restarted.verify_approval(envelope + b"x", summary, approval)
        )

        production_factory = getattr(
            authorities_module, "open_live_anchor_broker", None
        )
        self.assertIsNotNone(production_factory)
        with self.assertRaises(TypeError):
            production_factory(
                restarted,
                namespace=NAMESPACE,
                installation_id=INSTALLATION_ID,
                caller_code_identity=CALLER_CODE_IDENTITY,
                broker_code_identity=BROKER_CODE_IDENTITY,
            )

    def test_fake_native_rejects_unauthenticated_correct_old_arbitrary_new(self):
        factory = authorities_module.open_test_native_authority_backend
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        state = self.root / "fake-native-raw-cas.json"
        backend = factory(fake, state_path=state)
        backend.bootstrap(
            {
                "created_at": CREATED_AT,
                "installation_id": INSTALLATION_ID,
                "creator_id": CREATOR_ID,
                "descriptor_digest": "d" * 64,
                "final_plan_digest": "e" * 64,
                "wal_digest": "f" * 64,
                "anchor_namespace": NAMESPACE,
                "initial_anchor_generation": 0,
                "initial_anchor_commitment": ANCHOR_COMMITMENT,
            }
        )
        raw_transition = {
            "domain": "installation-transaction",
            "transition_domain": "installation-transaction",
            "transition_digest": "6" * 64,
            "namespace": NAMESPACE,
            "installation_id": INSTALLATION_ID,
            "subject_kind": "task",
            "subject_id": "task-1",
            "operation_kind": "publish-installation",
            "old_generation": 0,
            "old_commitment": ANCHOR_COMMITMENT,
            "new_generation": 1,
            "new_commitment": "9" * 64,
            "plan_digest": "1" * 64,
            "wal_digest": "2" * 64,
            "event_digest": "3" * 64,
            "check_digest": "4" * 64,
            "record_digest": "5" * 64,
            "authorization_epoch": 7,
            "caller_code_identity": CALLER_CODE_IDENTITY,
            "broker_code_identity": BROKER_CODE_IDENTITY,
            "nonce": "raw-native-cas",
            "expires_at": int(time.time()) + 300,
        }
        with self.assertRaises(TypeError):
            backend.compare_and_advance(raw_transition)
        result = subprocess.run(
            [fake, "anchor-compare-and-advance"],
            input=canonical_json_bytes(raw_transition),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "AGENT_HARNESS_FAKE_NATIVE_STATE": str(state),
            },
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(backend.anchor_read(NAMESPACE), (0, ANCHOR_COMMITMENT))
        transition_secret = b"fake-native-transition-key"
        unsigned = {
            key: value
            for key, value in {
                **raw_transition,
                "new_commitment": OTHER_ANCHOR_COMMITMENT,
            }.items()
            if key not in {"transition_domain", "transition_digest"}
        }
        encoded = canonical_json_bytes(unsigned)
        authorized = {
            **unsigned,
            "transition_domain": unsigned["domain"],
            "transition_digest": hashlib.sha256(
                b"agent-harness/verified-anchor-transition/v1\0" + encoded
            ).hexdigest(),
            "authorization_mac": hmac.new(
                transition_secret,
                b"agent-harness/mac/anchor-transition-request/v1\0" + encoded,
                hashlib.sha256,
            ).hexdigest(),
        }
        forged = {**authorized, "new_commitment": "9" * 64}
        result = subprocess.run(
            [fake, "anchor-compare-and-advance"],
            input=canonical_json_bytes(forged),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "AGENT_HARNESS_FAKE_NATIVE_STATE": str(state),
                "AGENT_HARNESS_FAKE_TRANSITION_KEY": transition_secret.hex(),
            },
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(backend.anchor_read(NAMESPACE), (0, ANCHOR_COMMITMENT))
        result = subprocess.run(
            [fake, "anchor-compare-and-advance"],
            input=canonical_json_bytes(authorized),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "AGENT_HARNESS_FAKE_NATIVE_STATE": str(state),
                "AGENT_HARNESS_FAKE_TRANSITION_KEY": transition_secret.hex(),
            },
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            backend.anchor_read(NAMESPACE), (1, OTHER_ANCHOR_COMMITMENT)
        )

    def test_fake_native_recovers_each_partial_add_and_rejects_replay(self):
        factory = authorities_module.open_test_native_authority_backend
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        request = {
            "created_at": CREATED_AT,
            "installation_id": INSTALLATION_ID,
            "creator_id": CREATOR_ID,
            "descriptor_digest": "d" * 64,
            "final_plan_digest": "e" * 64,
            "wal_digest": "f" * 64,
            "anchor_namespace": NAMESPACE,
            "initial_anchor_generation": 0,
            "initial_anchor_commitment": ANCHOR_COMMITMENT,
        }
        for stage in (
            "approval_key",
            "receipt_key",
            "anchor",
            "bootstrap_record",
        ):
            with self.subTest(stage=stage):
                state = self.root / f"fake-native-crash-{stage}.json"
                backend = factory(fake, state_path=state)
                with self.assertRaises(CapabilityFailure):
                    backend.bootstrap({**request, "test_crash_after": stage})
                recovered = factory(fake, state_path=state).recover_bootstrap(
                    request
                )
                self.assertEqual(
                    recovered["pending_plan_commitment"], "e" * 64
                )
                with self.assertRaisesRegex(
                    CapabilityFailure, "foreign fixed-locator collision"
                ):
                    factory(fake, state_path=state).recover_bootstrap(
                        {**request, "final_plan_digest": "0" * 64}
                    )

    def test_fake_native_process_concurrency_has_exactly_one_provisioner(self):
        factory = authorities_module.open_test_native_authority_backend
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        state = self.root / "fake-native-concurrent.json"
        backend = factory(fake, state_path=state)
        request = {
            "created_at": CREATED_AT,
            "installation_id": INSTALLATION_ID,
            "creator_id": CREATOR_ID,
            "descriptor_digest": "d" * 64,
            "final_plan_digest": "e" * 64,
            "wal_digest": "f" * 64,
            "anchor_namespace": NAMESPACE,
            "initial_anchor_generation": 0,
            "initial_anchor_commitment": ANCHOR_COMMITMENT,
        }

        def provision() -> str:
            try:
                backend.bootstrap(request)
            except CapabilityFailure:
                return "collision"
            return "provisioned"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: provision(), range(2)))
        self.assertCountEqual(outcomes, ["provisioned", "collision"])
        recovered = factory(fake, state_path=state).recover_bootstrap(request)
        self.assertEqual(recovered["bootstrap_digest"], "d" * 64)

    def test_verified_bootstrap_dispatches_to_native_protocol(self):
        factory = authorities_module.open_test_native_authority_backend
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        state = self.root / "fake-native-plan.json"
        backend = factory(fake, state_path=state)
        body = setup_body()
        descriptor = plan_authority_bootstrap(
            body.digest,
            requirements(
                self.root / "fake-native-plan.wal",
                launcher_code_identity=backend.code_identity,
                launcher_content_digest=hashlib.sha256(
                    fake.read_bytes()
                ).hexdigest(),
                native_broker_code_identity=backend.code_identity,
                native_broker_content_digest=hashlib.sha256(
                    fake.read_bytes()
                ).hexdigest(),
            ),
        )
        plan = build_final_install_plan(
            body, descriptor, created_at=CREATED_AT
        )
        observations = {
            locator: {"state": "absent"} for locator in descriptor.locators
        }
        verified = verify_authority_bootstrap(
            plan,
            descriptor.to_document(),
            expected_installation_id=INSTALLATION_ID,
            observations=observations,
        )
        manifest = bootstrap_authority(
            verified,
            backend,
            interaction=self.interaction,
        )
        self.assertEqual(manifest["schema"], "agent-harness/authority-manifest")
        self.assertEqual(manifest["bootstrap_digest"], descriptor.digest)
        self.assertIsInstance(manifest["broker_signature"], str)
        self.assertTrue(backend.verify_bootstrap_manifest(manifest))
        self.assertEqual(
            backend.anchor_read(NAMESPACE), (0, ANCHOR_COMMITMENT)
        )

    def test_retirement_boundary_rejects_raw_or_unsigned_requests(self):
        factory = authorities_module.open_test_native_authority_backend
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        state = self.root / "fake-native-retirement.json"
        backend = factory(fake, state_path=state)
        method = getattr(backend, "add_retirement_pin", None)
        self.assertIsNotNone(
            method, "sealed retirement-capability method is missing"
        )
        with self.assertRaises(TypeError):
            method(
                {
                    "installation_id": INSTALLATION_ID,
                    "authority_era": "v1",
                }
            )

        request = {
            "installation_id": INSTALLATION_ID,
            "authority_era": "v1",
            "attestation_digest": "1" * 64,
            "receipt_public_key_digest": "2" * 64,
            "helper_object_identity": "helper-v1",
            "helper_finalizer_digest": "3" * 64,
        }
        result = subprocess.run(
            [fake, "retirement-pin"],
            input=canonical_json_bytes(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "AGENT_HARNESS_FAKE_NATIVE_STATE": str(state),
            },
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            b"authenticated retirement capability required", result.stderr
        )


class AnchorAndApprovalAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.backend = MemoryAuthorityBackend(code_identity=BROKER_CODE_IDENTITY)
        self.integrity = create_test_integrity_authority(
            b"anchor-request-key",
            installation_id=INSTALLATION_ID,
            key_id="anchor-key",
        )
        self.broker = create_test_live_anchor_broker(
            self.backend,
            namespace=NAMESPACE,
            installation_id=INSTALLATION_ID,
            caller_code_identity=CALLER_CODE_IDENTITY,
            broker_code_identity=BROKER_CODE_IDENTITY,
            initial_generation=0,
            initial_commitment=ANCHOR_COMMITMENT,
        )

    def verified_transition_state(self, **binding_changes: object):
        binding = {
            "old_commitment": ANCHOR_COMMITMENT,
            "new_commitment": OTHER_ANCHOR_COMMITMENT,
            "wal_digest": "2" * 64,
            "event_digest": "3" * 64,
            "check_digest": "4" * 64,
            "record_digest": "5" * 64,
            "authorization_epoch": 7,
        }
        binding.update(binding_changes)
        receipt = new_document(
            "adapter-receipt",
            INSTALLATION_ID,
            created_at=CREATED_AT,
            host="codex",
            receipt_id="receipt-codex",
            applied_transaction="task-1",
            targets=[".codex/AGENTS.md"],
            before_metadata_digest="a" * 64,
            after_metadata_digest="b" * 64,
            plan_digest="1" * 64,
            generation=1,
            root=RUNTIME_ROOT,
            anchor_commitment=OTHER_ANCHOR_COMMITMENT,
        )
        receipt["mac"] = self.integrity.mac_adapter_receipt(receipt)
        receipt_digest = hashlib.sha256(
            canonical_json_bytes(receipt)
        ).hexdigest()
        index = new_document(
            "installation-index",
            INSTALLATION_ID,
            created_at=CREATED_AT,
            generation=1,
            lifecycle_state="INSTALLED",
            publication_transaction="task-1",
            predecessor_digest="0" * 64,
            runtime_root=RUNTIME_ROOT,
            rollback_root=ROLLBACK_ROOT,
            receipts=[
                {
                    "receipt_id": "receipt-codex",
                    "path": "receipts/codex.json",
                    "digest": receipt_digest,
                }
            ],
            receipt_count=1,
            anchor_commitment=OTHER_ANCHOR_COMMITMENT,
            anchor_transition=binding,
        )
        index["mac"] = self.integrity.mac_installation_index(index)
        verified_index = self.integrity.verify_installation_index(
            index,
            expected_installation_id=INSTALLATION_ID,
            expected_generation=1,
            expected_root=RUNTIME_ROOT,
            expected_anchor_commitment=OTHER_ANCHOR_COMMITMENT,
        )
        return index, load_installation_state(
            verified_index,
            {"receipts/codex.json": receipt},
            authority=self.integrity,
        )

    def transition(
        self, *, now: int | None = None, **binding_changes: object
    ) -> VerifiedAnchorTransition:
        _, phase = self.verified_transition_state(**binding_changes)
        return issue_installation_anchor_transition(
            phase, self.broker, authority=self.integrity, now=now
        )

    def approval_envelope(self) -> dict[str, object]:
        return {
            "schema": "agent-harness/external-write-envelope",
            "schema_version": 1,
            "installation_id": INSTALLATION_ID,
            "intent_digest": "7" * 64,
            "predecessor_task_event_hash": "8" * 64,
            "expires_at": "2026-07-29T12:44:56Z",
        }

    def test_installation_transition_is_derived_from_verified_phase_state(self):
        issuer = getattr(
            authorities_module, "issue_installation_anchor_transition", None
        )
        self.assertIsNotNone(issuer, "domain-specific transition issuer is missing")
        raw, verified_state = self.verified_transition_state()

        try:
            transition = issuer(
                verified_state,
                self.broker,
                authority=self.integrity,
                now=1_000,
            )
        except TypeError as error:
            self.fail(f"issuer rejected verified installation state: {error}")
        document = transition.document
        self.assertEqual(document["domain"], "installation-transaction")
        self.assertEqual(document["namespace"], NAMESPACE)
        self.assertEqual(document["installation_id"], INSTALLATION_ID)
        self.assertEqual(document["subject_kind"], "task")
        self.assertEqual(document["subject_id"], "task-1")
        self.assertEqual(document["operation_kind"], "publish-installation")
        self.assertEqual(document["old_generation"], 0)
        self.assertEqual(document["old_commitment"], ANCHOR_COMMITMENT)
        self.assertEqual(document["new_generation"], 1)
        self.assertEqual(document["new_commitment"], OTHER_ANCHOR_COMMITMENT)
        self.assertEqual(document["expires_at"], 1_300)
        self.assertRegex(document["authorization_mac"], r"^[0-9a-f]{64}$")

        raw["anchor_transition"]["new_commitment"] = "9" * 64
        self.assertEqual(
            transition.document["new_commitment"], OTHER_ANCHOR_COMMITMENT
        )
        with self.assertRaises(TypeError):
            issuer(
                verified_state,
                self.broker,
                authority=self.integrity,
                now=1_000,
                new_commitment="9" * 64,
            )
        self.assertFalse(
            hasattr(authorities_module, "verify_anchor_transition_request")
        )
        self.assertFalse(
            hasattr(auth_module, "authorize_anchor_transition_request_for_test")
        )
        wrong_authority = create_test_integrity_authority(
            b"wrong-transition-key",
            installation_id=INSTALLATION_ID,
        )
        with self.assertRaisesRegex(IntegrityError, "MAC verification"):
            issuer(
                verified_state,
                self.broker,
                authority=wrong_authority,
                now=1_000,
            )

    def test_raw_or_forged_transition_cannot_advance(self):
        raw, _ = self.verified_transition_state()
        with self.assertRaises(TypeError):
            self.broker.compare_and_advance(raw)
        with self.assertRaises(TypeError):
            VerifiedAnchorTransition(object(), raw)
        with self.assertRaises(TypeError):
            issue_installation_anchor_transition(
                raw, self.broker, authority=self.integrity
            )
        self.assertEqual(self.broker.current_state(), (0, ANCHOR_COMMITMENT))

    def test_expired_stale_and_malformed_phase_bindings_are_rejected(self):
        mutations = {
            "wal": {"wal_digest": "9" * 63},
            "event": {"event_digest": "not-hex"},
            "check": {"check_digest": None},
            "record": {"record_digest": "9" * 65},
            "new": {"new_commitment": "g" * 64},
            "epoch": {"authorization_epoch": True},
        }
        for label, changes in mutations.items():
            with self.subTest(label=label):
                _, phase = self.verified_transition_state(**changes)
                with self.assertRaises(AuthorityError):
                    issue_installation_anchor_transition(
                        phase, self.broker, authority=self.integrity
                    )
                self.assertEqual(
                    self.broker.current_state(), (0, ANCHOR_COMMITMENT)
                )
        expired = self.transition(now=int(time.time()) - 301)
        with self.assertRaisesRegex(AuthorityError, "expired"):
            self.broker.compare_and_advance(expired)
        self.backend.anchors[NAMESPACE] = (1, OTHER_ANCHOR_COMMITMENT)
        with self.assertRaises(ValueError):
            self.transition()

    def test_compare_and_advance_is_one_use_exact_cas_with_signed_receipt(self):
        transition = self.transition()
        receipt = self.broker.compare_and_advance(transition)
        self.assertEqual(
            self.broker.current_state(), (1, OTHER_ANCHOR_COMMITMENT)
        )
        self.assertTrue(self.broker.verify_receipt(receipt))
        tampered = dict(receipt)
        tampered["new_commitment"] = "9" * 64
        self.assertFalse(self.broker.verify_receipt(tampered))
        with self.assertRaisesRegex(AuthorityError, "consumed"):
            self.broker.compare_and_advance(transition)

    def test_actual_anchor_receipt_is_schema_and_mac_consumable(self):
        receipt = self.broker.compare_and_advance(self.transition())
        authenticated = require_document(receipt, "state-anchor-receipt")
        authenticated["mac"] = self.integrity.mac_state_anchor_receipt(
            authenticated
        )
        verified = self.integrity.verify_state_anchor_receipt(
            authenticated,
            expected_installation_id=INSTALLATION_ID,
            expected_generation=1,
            expected_anchor_commitment=OTHER_ANCHOR_COMMITMENT,
        )
        self.assertEqual(verified.document["operation_id"], receipt["operation_id"])

    def test_stale_and_concurrent_compare_and_advance_has_one_winner(self):
        first = self.transition()
        second = self.transition()
        with ThreadPoolExecutor(max_workers=2) as executor:
            errors = [
                future.exception()
                for future in (
                    executor.submit(self.broker.compare_and_advance, first),
                    executor.submit(self.broker.compare_and_advance, second),
                )
            ]
        self.assertEqual(sum(error is None for error in errors), 1)
        self.assertEqual(
            self.broker.current_state(), (1, OTHER_ANCHOR_COMMITMENT)
        )
        restarted = create_test_live_anchor_broker(
            self.backend,
            namespace=NAMESPACE,
            installation_id=INSTALLATION_ID,
            caller_code_identity=CALLER_CODE_IDENTITY,
            broker_code_identity=BROKER_CODE_IDENTITY,
            initial_generation=1,
            initial_commitment=OTHER_ANCHOR_COMMITMENT,
        )
        self.assertEqual(
            restarted.current_state(), (1, OTHER_ANCHOR_COMMITMENT)
        )

    def test_approval_authority_requires_pinned_key_and_protected_presence(self):
        approval = create_test_approval_authority(
            self.backend,
            expected_public_key_digest=self.backend.approval_public_key_digest,
            broker_code_identity=BROKER_CODE_IDENTITY,
            current_time=APPROVAL_NOW,
        )
        healthy = approval.health()
        self.assertTrue(healthy["healthy"])
        envelope = self.approval_envelope()
        summary = "Provider: example; operation: update; target: page"
        signature = approval.approve_external_write(
            envelope,
            summary,
            interaction=protected_interaction_for_test(
                origin="local-cli", stdin_is_tty=True, user_presence=True
            ),
        )
        self.assertIsInstance(signature, dict)
        self.assertEqual(signature["algorithm"], "p256-sha256")
        restarted = create_test_approval_authority(
            self.backend,
            expected_public_key_digest=self.backend.approval_public_key_digest,
            broker_code_identity=BROKER_CODE_IDENTITY,
            current_time=APPROVAL_NOW,
        )
        self.assertTrue(
            restarted.verify_public_key(envelope, summary, signature)
        )
        self.assertFalse(
            restarted.verify_public_key(
                {**envelope, "intent_digest": "9" * 64},
                summary,
                signature,
            )
        )
        self.assertFalse(
            restarted.verify_public_key(envelope, summary + " changed", signature)
        )
        self.assertFalse(
            restarted.verify_public_key(envelope, summary, {"signature": "bad"})
        )

        with self.assertRaisesRegex(CapabilityFailure, "user presence"):
            approval.approve_external_write(
                self.approval_envelope(),
                "summary",
                interaction=protected_interaction_for_test(
                    origin="local-cli", stdin_is_tty=True, user_presence=False
                ),
            )
        self.backend.approval_public_key_digest = "9" * 64
        with self.assertRaisesRegex(CapabilityFailure, "approval key"):
            approval.health()
        for forbidden in ("sign", "sign_bytes", "private_key", "key_bytes"):
            self.assertFalse(hasattr(approval, forbidden), forbidden)

    def test_approval_rejects_unversioned_or_incomplete_envelopes(self):
        approval = create_test_approval_authority(
            self.backend,
            expected_public_key_digest=self.backend.approval_public_key_digest,
            broker_code_identity=BROKER_CODE_IDENTITY,
            current_time=APPROVAL_NOW,
        )
        interaction = protected_interaction_for_test(
            origin="local-cli", stdin_is_tty=True, user_presence=True
        )
        for envelope in (
            {"intent_digest": "7" * 64},
            {**self.approval_envelope(), "schema_version": 2},
            {
                key: value
                for key, value in self.approval_envelope().items()
                if key != "predecessor_task_event_hash"
            },
        ):
            with self.subTest(envelope=envelope):
                with self.assertRaises(AuthorityError):
                    approval.approve_external_write(
                        envelope, "canonical summary", interaction=interaction
                    )

    def test_file_and_mock_backends_are_explicitly_nonqualifying(self):
        self.assertFalse(self.backend.qualifying)
        self.assertFalse(self.broker.qualifying)
        approval = create_test_approval_authority(
            self.backend,
            expected_public_key_digest=self.backend.approval_public_key_digest,
            broker_code_identity=BROKER_CODE_IDENTITY,
            current_time=APPROVAL_NOW,
        )
        self.assertFalse(approval.qualifying)

    def test_approval_rejects_expired_boundary_and_excessive_horizon(self):
        approval = create_test_approval_authority(
            self.backend,
            expected_public_key_digest=self.backend.approval_public_key_digest,
            broker_code_identity=BROKER_CODE_IDENTITY,
            current_time=APPROVAL_NOW,
        )
        interaction = protected_interaction_for_test(
            origin="local-cli", stdin_is_tty=True, user_presence=True
        )
        cases = {
            "expired": ("2026-07-29T12:34:55Z", "expired"),
            "boundary": ("2026-07-29T12:34:56Z", "expired"),
            "excessive horizon": (
                "2026-07-29T12:49:57Z",
                "excessive horizon",
            ),
        }
        for label, (expires_at, error) in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(AuthorityError, error):
                    approval.approve_external_write(
                        {
                            **self.approval_envelope(),
                            "expires_at": expires_at,
                        },
                        "Provider: example; operation: update; target: page",
                        interaction=interaction,
                    )

    def test_asserted_backend_qualification_cannot_build_production_authority(self):
        self.backend.qualifying = True
        with self.assertRaises(TypeError):
            LiveAnchorBroker(
                self.backend,
                namespace=NAMESPACE,
                installation_id=INSTALLATION_ID,
                caller_code_identity=CALLER_CODE_IDENTITY,
                broker_code_identity=BROKER_CODE_IDENTITY,
            )


if __name__ == "__main__":
    unittest.main()
