from __future__ import annotations

import json
from pathlib import Path
import unittest

from harness_core.contracts import (
    SchemaError,
    canonical_json_bytes,
    new_document,
    require_document,
)
from tests.unit.support import (
    CREATED_AT,
    INSTALLATION_ID,
    valid_workspace_manifest,
)


SCHEMA_REQUIRED_FIELDS = {
    "source-content-identity": {
        "algorithm_version",
        "policy_version",
        "ordered_manifest_digest",
        "source_commit",
        "frozen_snapshot_digest",
        "digest",
        "entries",
    },
    "workspace-manifest": {
        "workspace",
        "source_commit",
        "source_content_identity",
        "runtime_root",
        "rollback_root",
        "generation",
    },
    "install-plan": {
        "runtime_root",
        "rollback_root",
        "source_commit",
        "source_content_identity",
        "setup_body_digest",
        "authority_bootstrap",
        "authority_bootstrap_digest",
        "adapter_plan_digests",
        "operations",
        "plan_digest",
    },
    "installation-index": {
        "generation",
        "lifecycle_state",
        "publication_transaction",
        "predecessor_digest",
        "runtime_root",
        "rollback_root",
        "anchor_commitment",
        "receipts",
        "receipt_count",
        "mac",
    },
    "installation-publication-wal": {
        "prior_generation",
        "prior_index_digest",
        "new_generation",
        "new_index_digest",
        "transaction_digest",
        "plan_digest",
        "prepared_receipts",
        "phase",
        "mac",
    },
    "authority-bootstrap-wal": {
        "locators",
        "broker_code_identity",
        "creator_id",
        "item_attributes",
        "conditional_inverses",
        "bootstrap_digest",
        "pending_plan_commitment",
        "wal_locator",
        "wal_digest",
        "phase",
        "broker_signature",
    },
    "authority-manifest": {
        "broker_code_identity",
        "broker_content_digest",
        "approval_public_key_digest",
        "approval_persistent_reference",
        "anchor_backend_id",
        "anchor_namespace",
        "receipt_key_id",
        "receipt_public_key_digest",
        "receipt_persistent_reference",
        "terminal_pin_locator",
        "terminal_pin_attributes",
        "capability_state",
        "bootstrap_digest",
        "pending_plan_commitment",
        "broker_signature",
    },
    "signing-key-bootstrap-wal": {
        "keychain_locator",
        "operation_id",
        "creator_id",
        "item_attributes",
        "conditional_inverse",
        "phase",
        "mac",
    },
    "enrollment": {
        "repo_path",
        "root_object_id",
        "git_dir",
        "git_dir_object_id",
        "common_dir",
        "common_dir_object_id",
        "root_commit",
        "remote_fingerprint",
        "trusted_at",
    },
    "worktree-identity": {
        "parent_enrollment_id",
        "path",
        "root_object_id",
        "git_dir",
        "git_dir_object_id",
        "common_dir",
        "common_dir_object_id",
        "root_commit",
        "remote_fingerprint",
        "enrollment_nonce",
    },
    "adapter-plan": {
        "host",
        "plan_id",
        "source_commit",
        "operations",
        "collision_decisions",
        "plan_digest",
    },
    "adapter-receipt": {
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
        "mac",
    },
    "host-report": {
        "host",
        "executable",
        "version",
        "auth_state",
        "capabilities",
        "adapter_receipt",
        "health_failures",
        "health_warnings",
    },
    "verifier-spec": {
        "verifier_id",
        "task_id",
        "risk_tier",
        "surface",
        "argv",
        "artifacts",
        "timeout",
        "pass_criteria",
    },
    "check-record": {
        "sequence",
        "verifier_digest",
        "result",
        "output_digest",
        "prior_hash",
        "record_hash",
        "mac",
    },
    "check-tail": {
        "task_id",
        "task_version",
        "expected_sequence",
        "expected_record_hash",
        "checkpoint_generation",
        "mac",
    },
    "state-anchor-receipt": {
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
    },
    "write-intent": {
        "task_id",
        "authorization_epoch",
        "provider",
        "operation",
        "target",
        "content_digest",
        "precondition",
        "expires_at",
        "reservation_id",
        "idempotency_key",
        "provider_operation_id",
        "status",
    },
    "finalization-plan": {
        "lifecycle_phase",
        "owned_object_identities",
        "containment_proof_digests",
        "finalizers",
        "predecessor_generation",
        "plan_digest",
    },
    "migration": {
        "from_version",
        "to_version",
        "source_digest",
        "result_digest",
        "rollback_transaction",
    },
}


class ContractTests(unittest.TestCase):
    def test_canonical_json_is_stable(self):
        self.assertEqual(
            canonical_json_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}'
        )

    def test_canonical_json_normalizes_non_finite_number_errors(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    SchemaError, "non-finite JSON number"
                ):
                    canonical_json_bytes({"value": value})

    def test_newer_schema_blocks_mutation(self):
        with self.assertRaisesRegex(SchemaError, "newer schema_version 2"):
            require_document(
                {
                    "schema": "agent-harness/workspace-manifest",
                    "schema_version": 2,
                },
                "workspace-manifest",
            )

    def test_newer_schema_can_be_read_without_mutation_authority(self):
        document = {
            "schema": "agent-harness/workspace-manifest",
            "schema_version": 2,
            "future": True,
        }
        self.assertEqual(
            require_document(document, "workspace-manifest", mutable=False),
            document,
        )

    def test_unknown_fields_survive_validation(self):
        document = valid_workspace_manifest(extra={"future": {"kept": True}})
        self.assertEqual(
            require_document(document, "workspace-manifest")["future"],
            {"kept": True},
        )

    def test_payload_cannot_replace_base_identity(self):
        with self.assertRaisesRegex(SchemaError, "reserved field"):
            new_document(
                "workspace-manifest",
                INSTALLATION_ID,
                created_at=CREATED_AT,
                schema_version=99,
            )

    def test_bool_is_not_a_schema_version(self):
        with self.assertRaisesRegex(SchemaError, "positive integer"):
            require_document(
                {**valid_workspace_manifest(), "schema_version": True},
                "workspace-manifest",
            )

    def test_new_document_rejects_non_uuid_installation(self):
        with self.assertRaisesRegex(SchemaError, "installation_id"):
            new_document(
                "workspace-manifest", "not-a-uuid", created_at=CREATED_AT
            )

    def test_new_document_requires_rfc3339_utc(self):
        for invalid in (
            "2026-07-29 12:34:56Z",
            "2026-07-29T12:34:56",
            "2026-07-29T12:34:56+01:00",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(SchemaError, "RFC3339 UTC"):
                    new_document(
                        "workspace-manifest",
                        INSTALLATION_ID,
                        created_at=invalid,
                    )

    def test_all_version_one_schemas_have_complete_open_contracts(self):
        schema_root = Path(__file__).parents[2] / "runtime" / "schemas"
        base = {"schema", "schema_version", "created_at", "installation_id"}
        found = {
            path.name.removesuffix(".v1.schema.json")
            for path in schema_root.glob("*.v1.schema.json")
        }
        self.assertEqual(found, set(SCHEMA_REQUIRED_FIELDS))
        for kind, payload_fields in SCHEMA_REQUIRED_FIELDS.items():
            with self.subTest(kind=kind):
                document = json.loads(
                    (schema_root / f"{kind}.v1.schema.json").read_text()
                )
                self.assertEqual(
                    document["$id"],
                    f"https://agent-harness.local/schemas/{kind}.v1.schema.json",
                )
                self.assertEqual(document["type"], "object")
                self.assertIs(document["additionalProperties"], True)
                self.assertTrue(base | payload_fields <= set(document["required"]))
                self.assertEqual(
                    document["properties"]["schema"]["const"],
                    f"agent-harness/{kind}",
                )
                self.assertEqual(
                    document["properties"]["schema_version"]["const"], 1
                )


if __name__ == "__main__":
    unittest.main()
