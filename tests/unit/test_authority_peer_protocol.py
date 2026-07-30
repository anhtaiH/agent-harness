from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from harness_core.authorities import (
    CapabilityFailure,
    NativeAuthorityBackend,
    bootstrap_local_authorities,
    build_final_install_plan,
    open_native_authority_backend,
    plan_authority_bootstrap,
    verify_authority_bootstrap,
)
from tests.unit.support import CREATED_AT, INSTALLATION_ID, MemoryAuthorityBackend
from tests.unit.test_authorities import requirements, setup_body


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "runtime/bin/ah-authority"


def load_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"dispatch_count": 0, "mutation_count": 0}
    return json.loads(path.read_text())


@unittest.skipUnless(sys.platform == "darwin", "macOS native authority")
class NativePeerCompositionTests(unittest.TestCase):
    def run_protocol_case(
        self,
        case: str,
        directory: str,
        *,
        timeout: int = 120,
    ) -> tuple[dict[str, object], dict[str, object]]:
        case_root = Path(directory).resolve()
        result = subprocess.run(
            [WRAPPER, "--protocol-test", case, case_root],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout), load_state(
            case_root / "state.json"
        )

    def build_roles(
        self,
        directory: str,
    ) -> tuple[dict[str, object], Path]:
        root = Path(directory).resolve()
        result = subprocess.run(
            [WRAPPER, "--build-test-roles", root],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout), root / "state.json"

    def verified_plan(
        self,
        roles: dict[str, object],
        directory: str,
        *,
        variant: str,
    ):
        root = Path(directory).resolve()
        body = setup_body(
            operations=(
                {
                    "kind": "write-file",
                    "target": f".codex/{variant}.md",
                    "digest": "1" * 64,
                },
            )
        )
        attestation = roles["attestation"]
        descriptor = plan_authority_bootstrap(
            body.digest,
            requirements(
                root / f"{variant}.authority-bootstrap.wal",
                broker_locator=roles["verifier_path"],
                launcher_code_identity=attestation[
                    "launcher_code_identity"
                ],
                launcher_content_digest=attestation[
                    "launcher_content_digest"
                ],
                native_broker_code_identity=attestation[
                    "native_broker_code_identity"
                ],
                native_broker_content_digest=attestation[
                    "native_broker_content_digest"
                ],
            ),
        )
        final_plan = build_final_install_plan(
            body,
            descriptor,
            created_at=CREATED_AT,
        )
        observations = MemoryAuthorityBackend(
            code_identity=attestation["native_broker_code_identity"]
        ).observe(descriptor.locators)
        return verify_authority_bootstrap(
            final_plan,
            descriptor.to_document(),
            expected_installation_id=INSTALLATION_ID,
            observations=observations,
        )

    def test_valid_raw_request_with_caller_owned_fds_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome, state = self.run_protocol_case(
                "raw-caller-fds",
                directory,
            )
            self.assertEqual(outcome["result"], "denied")
            self.assertEqual(state["mutation_count"], 0)

    def test_genuinely_different_signed_live_peer_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome, state = self.run_protocol_case(
                "different-signed-peer",
                directory,
            )
            self.assertEqual(outcome["result"], "denied")
            self.assertNotEqual(
                outcome["trusted_requirement"],
                outcome["peer_requirement"],
            )
            self.assertNotEqual(
                outcome["trusted_content_digest"],
                outcome["peer_content_digest"],
            )
            self.assertEqual(state["mutation_count"], 0)

    def test_plan_b_cannot_dispatch_through_backend_opened_for_plan_a(self):
        self.assertFalse(
            hasattr(NativeAuthorityBackend, "bootstrap"),
            "production backend still exposes raw bootstrap dispatch",
        )
        self.assertFalse(
            hasattr(NativeAuthorityBackend, "recover_bootstrap"),
            "production backend still exposes raw recovery dispatch",
        )
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            plan_a = self.verified_plan(
                roles, directory, variant="plan-a"
            )
            plan_b = self.verified_plan(
                roles, directory, variant="plan-b"
            )
            backend = open_native_authority_backend(plan_a)
            with self.assertRaises(CapabilityFailure):
                bootstrap_local_authorities(plan_b, backend)
            state = load_state(state_path)
            self.assertEqual(state["dispatch_count"], 0)
            self.assertEqual(state["mutation_count"], 0)

    def test_second_dispatch_is_denied_after_failed_first_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            plan = self.verified_plan(
                roles, directory, variant="one-use"
            )
            backend = open_native_authority_backend(plan)
            Path(directory, "fail-before-mutation").write_text("1")
            with self.assertRaises(CapabilityFailure):
                bootstrap_local_authorities(plan, backend)
            with self.assertRaisesRegex(
                (CapabilityFailure, ValueError),
                "consumed|already attempted",
            ):
                bootstrap_local_authorities(plan, backend)
            state = load_state(state_path)
            self.assertEqual(state["dispatch_count"], 1)
            self.assertEqual(state["mutation_count"], 0)

    def test_child_cannot_mutate_after_parent_death_or_timeout(self):
        for case in ("parent-death", "parent-timeout"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                outcome, state = self.run_protocol_case(case, directory)
                self.assertEqual(outcome["result"], "denied")
                self.assertTrue(outcome["broker_reaped"])
                self.assertEqual(state["mutation_count"], 0)

    def test_oversized_request_cannot_block_before_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            started = time.monotonic()
            outcome, state = self.run_protocol_case(
                "oversized-request",
                directory,
                timeout=10,
            )
            elapsed = time.monotonic() - started
            self.assertEqual(outcome["result"], "denied")
            self.assertLess(elapsed, 5)
            self.assertEqual(state["dispatch_count"], 0)
            self.assertEqual(state["mutation_count"], 0)

    def test_response_binds_operation_recovery_nonce_and_exact_plan(self):
        cases = (
            "response-operation",
            "response-recovery",
            "response-nonce",
            "response-request-digest",
            "response-plan-digest",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                outcome, state = self.run_protocol_case(case, directory)
                self.assertEqual(outcome["result"], "denied")
                self.assertEqual(state["accepted_response_count"], 0)

    def test_production_composition_runs_swift_core_with_test_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            plan = self.verified_plan(
                roles, directory, variant="composition"
            )
            backend = open_native_authority_backend(plan)
            manifest = bootstrap_local_authorities(plan, backend)
            state = load_state(state_path)
            self.assertEqual(manifest["bootstrap_digest"], plan.descriptor_digest)
            self.assertEqual(state["provider"], "signed-memory")
            self.assertEqual(state["dispatch_count"], 1)
            self.assertEqual(state["mutation_count"], 1)
            self.assertFalse(state["keychain_mutated"])
            self.assertFalse(state["user_presence_requested"])

    def test_approved_custom_launcher_cannot_supply_test_sentinels(self):
        with tempfile.TemporaryDirectory() as directory:
            outcome, state = self.run_protocol_case(
                "custom-launcher-test-sentinels",
                directory,
            )
            self.assertEqual(outcome["result"], "denied")
            self.assertFalse(outcome["test_provider_selected"])
            self.assertEqual(state["mutation_count"], 0)


if __name__ == "__main__":
    unittest.main()
