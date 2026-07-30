from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from harness_core.auth import (
    authorize_anchor_transition_request_for_test,
    create_test_integrity_authority,
)
from harness_core.authorities import (
    AUTHORITY_BOOTSTRAP_CRASH_POINTS,
    APPROVAL_KEY_LOCATOR,
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
    plan_authority_bootstrap,
    protected_interaction_for_test,
    recover_authority_bootstrap,
    verify_anchor_transition_request,
    verify_authority_bootstrap,
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
        "broker_code_identity": BROKER_CODE_IDENTITY,
        "broker_content_digest": BROKER_CONTENT_DIGEST,
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


def transition_request(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "domain": "installation-transaction",
        "namespace": NAMESPACE,
        "installation_id": INSTALLATION_ID,
        "subject_kind": "task",
        "subject_id": "task-1",
        "operation_kind": "publish-installation",
        "old_generation": 0,
        "old_commitment": ANCHOR_COMMITMENT,
        "new_generation": 1,
        "new_commitment": OTHER_ANCHOR_COMMITMENT,
        "plan_digest": "1" * 64,
        "wal_digest": "2" * 64,
        "event_digest": "3" * 64,
        "check_digest": "4" * 64,
        "record_digest": "5" * 64,
        "authorization_epoch": 7,
        "caller_code_identity": CALLER_CODE_IDENTITY,
        "broker_code_identity": BROKER_CODE_IDENTITY,
        "nonce": "nonce-1",
        "expires_at": int(time.time()) + 300,
    }
    value.update(changes)
    return value


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
        self.assertIn('"user_presence_requested":false', result.stdout)
        self.assertEqual(list(fake_home.iterdir()), before)


class AnchorAndApprovalAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.backend = MemoryAuthorityBackend(code_identity=BROKER_CODE_IDENTITY)
        self.integrity = create_test_integrity_authority(
            b"anchor-request-key", key_id="anchor-key"
        )
        self.expected = transition_request()
        self.broker = create_test_live_anchor_broker(
            self.backend,
            namespace=NAMESPACE,
            installation_id=INSTALLATION_ID,
            caller_code_identity=CALLER_CODE_IDENTITY,
            broker_code_identity=BROKER_CODE_IDENTITY,
            initial_generation=0,
            initial_commitment=ANCHOR_COMMITMENT,
        )

    def signed_request(self, **changes: object) -> dict[str, object]:
        request = transition_request(**changes)
        return authorize_anchor_transition_request_for_test(
            self.integrity, request
        )

    def verify_transition(
        self, request: dict[str, object] | None = None, expected=None
    ) -> VerifiedAnchorTransition:
        return verify_anchor_transition_request(
            request or self.signed_request(),
            expected or self.expected,
            authority=self.integrity,
            now=int(time.time()),
        )

    def approval_envelope(self) -> dict[str, object]:
        return {
            "schema": "agent-harness/external-write-envelope",
            "schema_version": 1,
            "installation_id": INSTALLATION_ID,
            "intent_digest": "7" * 64,
            "predecessor_task_event_hash": "8" * 64,
            "expires_at": "2026-07-29T13:34:56Z",
        }

    def test_raw_or_forged_transition_cannot_advance(self):
        with self.assertRaises(TypeError):
            self.broker.compare_and_advance(self.signed_request())
        with self.assertRaises(TypeError):
            VerifiedAnchorTransition(self.signed_request())
        forged = self.signed_request()
        forged["authorization_mac"] = "0" * 64
        with self.assertRaisesRegex(AuthorityError, "authorization"):
            self.verify_transition(forged)
        self.assertEqual(self.broker.current_state(), (0, ANCHOR_COMMITMENT))

    def test_expired_cross_domain_and_wrong_bound_fields_are_rejected(self):
        mutations = {
            "expired": {"expires_at": int(time.time()) - 1},
            "domain": {"domain": "qualification"},
            "namespace": {"namespace": "other"},
            "installation": {"installation_id": OTHER_INSTALLATION_ID},
            "subject": {"subject_id": "task-2"},
            "operation": {"operation_kind": "arbitrary"},
            "wal": {"wal_digest": "9" * 64},
            "event": {"event_digest": "9" * 64},
            "check": {"check_digest": "9" * 64},
            "record": {"record_digest": "9" * 64},
            "caller": {"caller_code_identity": "changed-caller"},
            "broker": {"broker_code_identity": "changed-broker"},
            "new": {"new_commitment": "9" * 64},
        }
        for label, changes in mutations.items():
            with self.subTest(label=label):
                request = self.signed_request(**changes)
                with self.assertRaises(AuthorityError):
                    self.verify_transition(request)
                self.assertEqual(
                    self.broker.current_state(), (0, ANCHOR_COMMITMENT)
                )

    def test_compare_and_advance_is_one_use_exact_cas_with_signed_receipt(self):
        transition = self.verify_transition()
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

    def test_stale_and_concurrent_compare_and_advance_has_one_winner(self):
        first = self.verify_transition(
            self.signed_request(nonce="nonce-a"),
            {**self.expected, "nonce": "nonce-a"},
        )
        second = self.verify_transition(
            self.signed_request(nonce="nonce-b"),
            {**self.expected, "nonce": "nonce-b"},
        )
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
        restarted = LiveAnchorBroker(
            self.backend,
            namespace=NAMESPACE,
            installation_id=INSTALLATION_ID,
            caller_code_identity=CALLER_CODE_IDENTITY,
            broker_code_identity=BROKER_CODE_IDENTITY,
        )
        self.assertEqual(
            restarted.current_state(), (1, OTHER_ANCHOR_COMMITMENT)
        )

    def test_approval_authority_requires_pinned_key_and_protected_presence(self):
        approval = create_test_approval_authority(
            self.backend,
            expected_public_key_digest=self.backend.approval_public_key_digest,
            broker_code_identity=BROKER_CODE_IDENTITY,
        )
        healthy = approval.health()
        self.assertTrue(healthy["healthy"])
        signature = approval.approve_external_write(
            self.approval_envelope(),
            "Provider: example; operation: update; target: page",
            interaction=protected_interaction_for_test(
                origin="local-cli", stdin_is_tty=True, user_presence=True
            ),
        )
        self.assertTrue(approval.verify_public_key(signature))

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
        )
        self.assertFalse(approval.qualifying)


if __name__ == "__main__":
    unittest.main()
