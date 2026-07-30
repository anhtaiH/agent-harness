from __future__ import annotations

import copy
import hashlib
import hmac
import pickle
import unittest

from harness_core.auth import (
    IntegrityError,
    VerifiedAdapterReceipt,
    VerifiedBootstrapPlan,
    VerifiedFinalizationPlan,
    VerifiedInstallPlan,
    VerifiedInstallationIndex,
    VerifiedInstallationState,
    VerifiedRollbackPlan,
    VerifiedStateAnchorReceipt,
    create_test_integrity_authority,
    issue_rollback_plan_for_test,
    load_installation_state,
)
from harness_core.contracts import (
    FINAL_INSTALL_PLAN_DOMAIN,
    SchemaError,
    canonical_json_bytes,
    new_document,
)
from tests.unit.support import (
    ANCHOR_COMMITMENT,
    CREATED_AT,
    INSTALLATION_ID,
    OTHER_ANCHOR_COMMITMENT,
    OTHER_INSTALLATION_ID,
    ROLLBACK_ROOT,
    RUNTIME_ROOT,
    canonical_digest,
)


GENERATION = 4


def unsigned_receipt(**changes: object) -> dict[str, object]:
    value = new_document(
        "adapter-receipt",
        INSTALLATION_ID,
        created_at=CREATED_AT,
        host="codex",
        receipt_id="receipt-codex",
        applied_transaction="transaction-1",
        targets=[".codex/AGENTS.md"],
        before_metadata_digest="a" * 64,
        after_metadata_digest="b" * 64,
        plan_digest="c" * 64,
        generation=GENERATION,
        root=RUNTIME_ROOT,
        anchor_commitment=ANCHOR_COMMITMENT,
    )
    value.update(changes)
    return value


def signed_receipt(authority, **changes: object) -> dict[str, object]:
    value = unsigned_receipt(**changes)
    value["mac"] = authority.mac_adapter_receipt(value)
    return value


def unsigned_index(receipt: dict[str, object], **changes: object) -> dict[str, object]:
    receipt_digest = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
    value = new_document(
        "installation-index",
        INSTALLATION_ID,
        created_at=CREATED_AT,
        generation=GENERATION,
        lifecycle_state="INSTALLED",
        publication_transaction="transaction-1",
        predecessor_digest="0" * 64,
        runtime_root=RUNTIME_ROOT,
        rollback_root=ROLLBACK_ROOT,
        anchor_commitment=ANCHOR_COMMITMENT,
        receipts=[
            {
                "receipt_id": "receipt-codex",
                "path": "receipt-codex.json",
                "digest": receipt_digest,
            }
        ],
        receipt_count=1,
    )
    value.update(changes)
    return value


class IntegrityAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.secret = b"unit-test-integrity-key"
        self.authority = create_test_integrity_authority(
            self.secret,
            installation_id=INSTALLATION_ID,
            key_id="test-key-v1",
        )

    def verify_receipt(self, value: dict[str, object]) -> VerifiedAdapterReceipt:
        return self.authority.verify_adapter_receipt(
            value,
            expected_installation_id=INSTALLATION_ID,
            expected_generation=GENERATION,
            expected_root=RUNTIME_ROOT,
            expected_anchor_commitment=ANCHOR_COMMITMENT,
        )

    def test_valid_receipt_returns_bound_nonserializable_verified_type(self):
        verified = self.verify_receipt(signed_receipt(self.authority))
        self.assertIsInstance(verified, VerifiedAdapterReceipt)
        self.assertEqual(verified.installation_id, INSTALLATION_ID)
        self.assertEqual(verified.generation, GENERATION)
        self.assertEqual(verified.root, RUNTIME_ROOT)
        self.assertEqual(verified.anchor_commitment, ANCHOR_COMMITMENT)
        with self.assertRaises(TypeError):
            pickle.dumps(verified)

    def test_edited_payload_wrong_installation_or_wrong_key_is_rejected(self):
        signed = signed_receipt(self.authority)
        edited = copy.deepcopy(signed)
        edited["targets"] = [".codex/config.toml"]
        with self.assertRaisesRegex(IntegrityError, "MAC"):
            self.verify_receipt(edited)
        with self.assertRaisesRegex(IntegrityError, "installation"):
            self.authority.verify_adapter_receipt(
                signed,
                expected_installation_id=OTHER_INSTALLATION_ID,
                expected_generation=GENERATION,
                expected_root=RUNTIME_ROOT,
                expected_anchor_commitment=ANCHOR_COMMITMENT,
            )
        other = create_test_integrity_authority(
            b"another-integrity-key",
            installation_id=INSTALLATION_ID,
            key_id="other-key",
        )
        with self.assertRaisesRegex(IntegrityError, "MAC"):
            other.verify_adapter_receipt(
                signed,
                expected_installation_id=INSTALLATION_ID,
                expected_generation=GENERATION,
                expected_root=RUNTIME_ROOT,
                expected_anchor_commitment=ANCHOR_COMMITMENT,
            )

    def test_missing_or_malformed_mac_is_rejected(self):
        with self.assertRaisesRegex(IntegrityError, "missing MAC"):
            self.verify_receipt(unsigned_receipt())
        for malformed in ("not-hex", "00", 7, None):
            with self.subTest(malformed=malformed):
                value = unsigned_receipt()
                value["mac"] = malformed
                with self.assertRaisesRegex(IntegrityError, "malformed MAC"):
                    self.verify_receipt(value)

    def test_verified_type_cannot_be_forged(self):
        for verified_type in (
            VerifiedAdapterReceipt,
            VerifiedInstallPlan,
            VerifiedInstallationIndex,
            VerifiedInstallationState,
            VerifiedBootstrapPlan,
            VerifiedRollbackPlan,
            VerifiedStateAnchorReceipt,
            VerifiedFinalizationPlan,
        ):
            with self.subTest(verified_type=verified_type.__name__):
                with self.assertRaises(TypeError):
                    verified_type({})

    def test_verified_value_cannot_cross_bindings_or_be_reused(self):
        verified = self.verify_receipt(signed_receipt(self.authority))
        for bindings in (
            {"expected_installation_id": OTHER_INSTALLATION_ID},
            {"expected_generation": GENERATION + 1},
            {"expected_root": ROLLBACK_ROOT},
            {"expected_anchor_commitment": OTHER_ANCHOR_COMMITMENT},
        ):
            with self.subTest(bindings=bindings):
                with self.assertRaisesRegex(IntegrityError, "binding"):
                    verified.consume(**bindings)
        verified.consume(
            expected_installation_id=INSTALLATION_ID,
            expected_generation=GENERATION,
            expected_root=RUNTIME_ROOT,
            expected_anchor_commitment=ANCHOR_COMMITMENT,
        )
        with self.assertRaisesRegex(IntegrityError, "already consumed"):
            verified.consume(expected_installation_id=INSTALLATION_ID)

    def test_mac_domains_are_narrow_and_distinct(self):
        methods = (
            (
                "adapter-receipt",
                "mac_adapter_receipt",
                (
                    "host",
                    "receipt_id",
                    "applied_transaction",
                    "targets",
                    "before_metadata_digest",
                    "after_metadata_digest",
                    "plan_digest",
                    "generation",
                    "root",
                    "anchor_commitment",
                ),
            ),
            (
                "installation-index",
                "mac_installation_index",
                (
                    "generation",
                    "lifecycle_state",
                    "publication_transaction",
                    "predecessor_digest",
                    "runtime_root",
                    "rollback_root",
                    "anchor_commitment",
                    "receipts",
                    "receipt_count",
                ),
            ),
            (
                "installation-publication-wal",
                "mac_installation_publication_wal",
                (
                    "prior_generation",
                    "prior_index_digest",
                    "new_generation",
                    "new_index_digest",
                    "transaction_digest",
                    "plan_digest",
                    "prepared_receipts",
                    "phase",
                ),
            ),
            (
                "authority-bootstrap-wal",
                "mac_authority_bootstrap_wal",
                (
                    "locators",
                    "broker_code_identity",
                    "creator_id",
                    "item_attributes",
                    "conditional_inverses",
                    "phase",
                    "broker_signature",
                ),
            ),
            (
                "signing-key-bootstrap-wal",
                "mac_signing_key_bootstrap_wal",
                (
                    "keychain_locator",
                    "operation_id",
                    "creator_id",
                    "item_attributes",
                    "conditional_inverse",
                    "phase",
                ),
            ),
            (
                "state-anchor-receipt",
                "mac_state_anchor_receipt",
                (
                    "anchor_namespace",
                    "anchor_backend_id",
                    "receipt_key_id",
                    "transition_domain",
                    "transition_digest",
                    "old_generation",
                    "old_commitment",
                    "new_generation",
                    "new_commitment",
                    "operation_id",
                    "broker_receipt",
                ),
            ),
            (
                "check-record",
                "mac_check_record",
                (
                    "sequence",
                    "verifier_digest",
                    "result",
                    "output_digest",
                    "prior_hash",
                    "record_hash",
                ),
            ),
            (
                "check-tail",
                "mac_check_tail",
                (
                    "task_id",
                    "task_version",
                    "expected_sequence",
                    "expected_record_hash",
                    "checkpoint_generation",
                ),
            ),
        )
        documents = {
            "adapter-receipt": unsigned_receipt(),
            "installation-index": unsigned_index(
                signed_receipt(self.authority)
            ),
            "installation-publication-wal": new_document(
                "installation-publication-wal",
                INSTALLATION_ID,
                created_at=CREATED_AT,
                prior_generation=GENERATION - 1,
                prior_index_digest="1" * 64,
                new_generation=GENERATION,
                new_index_digest="2" * 64,
                transaction_digest="3" * 64,
                plan_digest="4" * 64,
                prepared_receipts=[],
                phase="PREPARED",
            ),
            "authority-bootstrap-wal": new_document(
                "authority-bootstrap-wal",
                INSTALLATION_ID,
                created_at=CREATED_AT,
                locators={"anchor": "agent-harness.anchor.v1"},
                broker_code_identity="native-broker-v1",
                creator_id="creator-v1",
                item_attributes={"anchor": {"add_only": True}},
                conditional_inverses=[],
                phase="PREPARED",
                broker_signature=None,
            ),
            "signing-key-bootstrap-wal": new_document(
                "signing-key-bootstrap-wal",
                INSTALLATION_ID,
                created_at=CREATED_AT,
                keychain_locator="agent-harness.signing-key.v1",
                operation_id="signing-key-bootstrap-v1",
                creator_id="creator-v1",
                item_attributes={"non_exportable": True},
                conditional_inverse={"operation": "remove-exact-add-result"},
                phase="PREPARED",
            ),
            "state-anchor-receipt": new_document(
                "state-anchor-receipt",
                INSTALLATION_ID,
                created_at=CREATED_AT,
                anchor_namespace="agent-harness.anchor.v1",
                anchor_backend_id="native-keychain-anchor-v1",
                receipt_key_id="broker-receipt:v1",
                transition_domain="installation-transaction",
                transition_digest="5" * 64,
                old_generation=GENERATION - 1,
                old_commitment="6" * 64,
                new_generation=GENERATION,
                new_commitment=ANCHOR_COMMITMENT,
                operation_id="anchor-cas-v1",
                broker_receipt="signed-receipt-v1",
            ),
            "check-record": new_document(
                "check-record",
                INSTALLATION_ID,
                created_at=CREATED_AT,
                sequence=1,
                verifier_digest="7" * 64,
                result="PASS",
                output_digest="8" * 64,
                prior_hash="9" * 64,
                record_hash="a" * 64,
            ),
            "check-tail": new_document(
                "check-tail",
                INSTALLATION_ID,
                created_at=CREATED_AT,
                task_id="task-v1",
                task_version=1,
                expected_sequence=1,
                expected_record_hash="b" * 64,
                checkpoint_generation=GENERATION,
            ),
        }
        for kind, method, _ in methods:
            with self.subTest(kind=kind):
                value = documents[kind]
                domain = f"agent-harness/mac/{kind}/v1\0".encode()
                expected = hmac.new(
                    self.secret,
                    domain + canonical_json_bytes(value),
                    hashlib.sha256,
                ).hexdigest()
                self.assertEqual(getattr(self.authority, method)(value), expected)
        for forbidden in (
            "mac",
            "mac_anchor_transition_request",
            "sign",
            "sign_bytes",
            "key",
            "key_bytes",
            "secret",
        ):
            self.assertFalse(hasattr(self.authority, forbidden), forbidden)

    def test_mac_issuance_is_installation_bound_and_semantically_validated(self):
        authority = create_test_integrity_authority(
            self.secret,
            key_id="installation-bound-key",
            installation_id=INSTALLATION_ID,
        )
        foreign = unsigned_receipt(installation_id=OTHER_INSTALLATION_ID)
        with self.assertRaisesRegex(IntegrityError, "installation"):
            authority.mac_adapter_receipt(foreign)

        semantically_invalid = unsigned_receipt(generation="4")
        with self.assertRaisesRegex(IntegrityError, "generation"):
            authority.mac_adapter_receipt(semantically_invalid)

    def test_narrow_mac_issuers_reject_arbitrary_payloads(self):
        methods = (
            ("adapter-receipt", "mac_adapter_receipt"),
            ("installation-index", "mac_installation_index"),
            (
                "installation-publication-wal",
                "mac_installation_publication_wal",
            ),
            ("authority-bootstrap-wal", "mac_authority_bootstrap_wal"),
            ("signing-key-bootstrap-wal", "mac_signing_key_bootstrap_wal"),
            ("state-anchor-receipt", "mac_state_anchor_receipt"),
            ("check-record", "mac_check_record"),
            ("check-tail", "mac_check_tail"),
        )
        for kind, method in methods:
            with self.subTest(method=method):
                for arbitrary in (
                    {"installation_id": INSTALLATION_ID, "payload": "arbitrary"},
                    new_document(
                        kind,
                        INSTALLATION_ID,
                        created_at=CREATED_AT,
                        payload="arbitrary",
                    ),
                ):
                    with self.assertRaises((IntegrityError, SchemaError)):
                        getattr(self.authority, method)(arbitrary)

    def test_mac_verifier_rechecks_phase_semantics(self):
        receipt = new_document(
            "state-anchor-receipt",
            INSTALLATION_ID,
            created_at=CREATED_AT,
            anchor_namespace="agent-harness.anchor.v1",
            anchor_backend_id="native-keychain-anchor-v1",
            receipt_key_id="broker-receipt:v1",
            transition_domain="installation-transaction",
            transition_digest="5" * 64,
            old_generation=GENERATION - 1,
            old_commitment="6" * 64,
            new_generation=GENERATION + 1,
            new_commitment=ANCHOR_COMMITMENT,
            operation_id="semantic-gap",
            broker_receipt="signed-receipt-v1",
        )
        receipt["mac"] = hmac.new(
            self.secret,
            b"agent-harness/mac/state-anchor-receipt/v1\0"
            + canonical_json_bytes(receipt),
            hashlib.sha256,
        ).hexdigest()
        with self.assertRaisesRegex(
            IntegrityError,
            "advance by one",
        ):
            self.authority.verify_state_anchor_receipt(
                receipt,
                expected_installation_id=INSTALLATION_ID,
                expected_generation=GENERATION + 1,
                expected_anchor_commitment=ANCHOR_COMMITMENT,
            )

    def test_complete_install_plan_verification_returns_phase_specific_type(self):
        raw = new_document(
            "install-plan",
            INSTALLATION_ID,
            created_at=CREATED_AT,
            generation=GENERATION,
            runtime_root=RUNTIME_ROOT,
            rollback_root=ROLLBACK_ROOT,
            anchor_commitment=ANCHOR_COMMITMENT,
            source_commit="a" * 40,
            source_content_identity="b" * 64,
            setup_body_digest="c" * 64,
            authority_bootstrap={},
            authority_bootstrap_digest="d" * 64,
            adapter_plan_digests=[],
            operations=[],
        )
        raw["plan_digest"] = canonical_digest(
            FINAL_INSTALL_PLAN_DOMAIN, raw
        )
        verified = self.authority.verify_install_plan(
            raw,
            expected_installation_id=INSTALLATION_ID,
            expected_generation=GENERATION,
            expected_root=RUNTIME_ROOT,
            expected_anchor_commitment=ANCHOR_COMMITMENT,
        )
        self.assertIsInstance(verified, VerifiedInstallPlan)
        changed = dict(raw)
        changed["runtime_root"] = ROLLBACK_ROOT
        with self.assertRaisesRegex(IntegrityError, "digest"):
            self.authority.verify_install_plan(
                changed,
                expected_installation_id=INSTALLATION_ID,
                expected_generation=GENERATION,
                expected_root=RUNTIME_ROOT,
                expected_anchor_commitment=ANCHOR_COMMITMENT,
            )

    def test_index_loader_requires_exact_mac_verified_registry_bijection(self):
        receipt = signed_receipt(self.authority)
        index = unsigned_index(receipt)
        index["mac"] = self.authority.mac_installation_index(index)
        verified_index = self.authority.verify_installation_index(
            index,
            expected_installation_id=INSTALLATION_ID,
            expected_generation=GENERATION,
            expected_root=RUNTIME_ROOT,
            expected_anchor_commitment=ANCHOR_COMMITMENT,
        )
        state = load_installation_state(
            verified_index,
            {"receipt-codex.json": receipt},
            authority=self.authority,
        )
        self.assertIsInstance(state, VerifiedInstallationState)
        self.assertEqual(set(state.receipts), {"receipt-codex"})

        for registry in (
            {},
            {
                "receipt-codex.json": receipt,
                "unexpected.json": signed_receipt(
                    self.authority, receipt_id="unexpected"
                ),
            },
        ):
            with self.subTest(registry=registry):
                with self.assertRaisesRegex(IntegrityError, "bijection"):
                    load_installation_state(
                        verified_index, registry, authority=self.authority
                    )
        with self.assertRaises(TypeError):
            load_installation_state(index, {"receipt-codex.json": receipt}, authority=self.authority)

    def test_only_test_issuer_can_create_foundation_rollback_capability(self):
        rollback = issue_rollback_plan_for_test(
            installation_id=INSTALLATION_ID,
            generation=GENERATION,
            root=ROLLBACK_ROOT,
            anchor_commitment=ANCHOR_COMMITMENT,
            document={"transaction_id": "transaction-1"},
        )
        self.assertIsInstance(rollback, VerifiedRollbackPlan)
        self.assertFalse(hasattr(self.authority, "issue_rollback_plan"))


if __name__ == "__main__":
    unittest.main()
