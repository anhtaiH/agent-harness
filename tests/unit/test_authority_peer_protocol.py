from __future__ import annotations

import base64
import copy
from contextlib import contextmanager
import gc
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import warnings

import harness_core.authorities as authorities_module
from harness_core.authorities import (
    BOOTSTRAP_RECORD_LOCATOR,
    AuthorityBootstrapDescriptor,
    CapabilityFailure,
    NativeAuthorityBackend,
    bootstrap_local_authorities,
    build_final_install_plan,
    open_native_authority_backend,
    plan_authority_bootstrap,
    prepare_native_protocol_roles_for_test,
    verify_authority_bootstrap,
)
from harness_core.contracts import canonical_json_bytes
from tests.unit.support import CREATED_AT, INSTALLATION_ID, MemoryAuthorityBackend
from tests.unit.test_authorities import requirements, setup_body


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "runtime/bin/ah-authority"


@contextmanager
def reject_openssl_child():
    real_run = subprocess.run
    real_popen = subprocess.Popen

    def reject_run(*args, **kwargs):
        command = args[0] if args else kwargs["args"]
        if Path(command[0]).name == "openssl":
            raise AssertionError(
                "controller private capability reached an OpenSSL child"
            )
        return real_run(*args, **kwargs)

    def reject_popen(*args, **kwargs):
        command = args[0] if args else kwargs["args"]
        if Path(command[0]).name == "openssl":
            raise AssertionError(
                "controller private capability reached an OpenSSL child"
            )
        return real_popen(*args, **kwargs)

    with (
        mock.patch.object(
            authorities_module.subprocess,
            "run",
            side_effect=reject_run,
        ),
        mock.patch.object(
            authorities_module.subprocess,
            "Popen",
            side_effect=reject_popen,
        ),
    ):
        yield


def load_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"dispatch_count": 0, "mutation_count": 0}
    return json.loads(path.read_text())


def run_controller_owner_until_killed(directory: str) -> None:
    test_case = NativePeerCompositionTests()
    roles, _ = test_case.build_roles(directory)
    plan = test_case.verified_plan(
        roles,
        directory,
        variant="controller-parent-death",
    )
    Path(directory, "recovery-fixture.json").write_bytes(
        canonical_json_bytes(
            {
                "descriptor": plan.descriptor.to_document(),
                "final_plan": plan.final_plan,
            }
        )
    )
    backend = authorities_module.open_native_protocol_core_for_test(plan)
    Path(directory, "stall-before-mutation").write_text("1")
    bootstrap_local_authorities(plan, backend)


@unittest.skipUnless(sys.platform == "darwin", "macOS native authority")
class NativePeerCompositionTests(unittest.TestCase):
    def build_roles(
        self,
        directory: str,
    ) -> tuple[dict[str, object], Path]:
        root = Path(directory).resolve()
        with reject_openssl_child():
            prepared = prepare_native_protocol_roles_for_test(
                WRAPPER,
                root,
            )
        return {
            "attestation": prepared.attestation,
            "verifier_path": str(prepared.verifier_path),
            "broker_path": str(root / "macos-broker-internal"),
            "state_path": str(prepared.state_path),
            "prepared": prepared,
        }, prepared.state_path

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
                launcher_code_directory_hash=attestation[
                    "launcher_code_directory_hash"
                ],
                native_broker_code_directory_hash=attestation[
                    "native_broker_code_directory_hash"
                ],
                controller_public_key_digest=attestation[
                    "controller_public_key_digest"
                ],
                authority_provider=attestation["authority_provider"],
                verifier_mode=attestation["verifier_mode"],
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
            prepared_roles=roles["prepared"],
        )

    def run_direct_verifier(
        self,
        roles: dict[str, object],
        request_bytes: bytes,
        *,
        extra_environment: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[bytes]:
        with tempfile.TemporaryFile() as request_file:
            request_file.write(request_bytes)
            request_file.flush()
            request_file.seek(0)
            descriptor = request_file.fileno()
            return subprocess.run(
                [roles["verifier_path"], "bootstrap"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "AGENT_HARNESS_BOOTSTRAP_REQUEST_FD": str(
                        descriptor
                    ),
                    **(extra_environment or {}),
                },
                pass_fds=(descriptor,),
                timeout=timeout,
            )

    def kill_controller_after_reservation(
        self,
        directory: str,
    ) -> tuple[Path, dict[str, object], int]:
        state_path = Path(directory, "state.json")
        controller = multiprocessing.get_context("spawn").Process(
            target=run_controller_owner_until_killed,
            args=(directory,),
        )
        controller.start()
        broker_pid: int | None = None
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                state = load_state(state_path)
                if state.get("reservation_count") == 1:
                    broker_pid = state.get("broker_pid")
                    break
                if not controller.is_alive():
                    self.fail(
                        "controller owner exited before broker reservation"
                    )
                time.sleep(0.05)
            self.assertIsInstance(broker_pid, int)
            controller.kill()
            controller.join(timeout=10)
            self.assertFalse(controller.is_alive())
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    os.kill(broker_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            with self.assertRaises(ProcessLookupError):
                os.kill(broker_pid, 0)
            fixture = json.loads(
                Path(directory, "recovery-fixture.json").read_text()
            )
            return state_path, fixture, broker_pid
        finally:
            if controller.is_alive():
                controller.kill()
                controller.join(timeout=10)
            if isinstance(broker_pid, int):
                try:
                    os.kill(broker_pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    os.kill(broker_pid, 9)

    def test_valid_raw_request_with_caller_owned_fds_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            plan = self.verified_plan(
                roles,
                directory,
                variant="raw-caller-fds",
            )
            request = authorities_module._native_bootstrap_request(
                plan,
                {"wal_digest": "3" * 64},
            )
            result = self.run_direct_verifier(
                roles,
                canonical_json_bytes(request),
            )
            self.assertNotEqual(
                result.returncode,
                0,
                "genuine verifier accepted a caller-owned valid request FD",
            )
            state = load_state(state_path)
            self.assertEqual(state["dispatch_count"], 0)
            self.assertEqual(state["mutation_count"], 0)

    def test_genuinely_different_signed_live_peer_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            trusted, trusted_state_path = self.build_roles(
                str(Path(directory) / "trusted")
            )
            alternate, alternate_state_path = self.build_roles(
                str(Path(directory) / "alternate")
            )
            plan = self.verified_plan(
                trusted,
                directory,
                variant="different-signed-peer",
            )
            backend = authorities_module.open_native_protocol_core_for_test(
                plan
            )
            Path(
                trusted["state_path"]
            ).parent.joinpath("alternate-broker-path").write_text(
                alternate["broker_path"]
            )
            with self.assertRaises(CapabilityFailure):
                bootstrap_local_authorities(plan, backend)
            self.assertNotEqual(
                trusted["attestation"][
                    "native_broker_code_directory_hash"
                ],
                alternate["attestation"][
                    "native_broker_code_directory_hash"
                ],
            )
            self.assertNotEqual(
                trusted["attestation"]["native_broker_content_digest"],
                alternate["attestation"]["native_broker_content_digest"],
            )
            self.assertEqual(
                load_state(trusted_state_path)["mutation_count"],
                0,
            )
            self.assertEqual(
                load_state(alternate_state_path)["mutation_count"],
                0,
            )

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
            roles_a, state_path = self.build_roles(
                str(Path(directory) / "roles-a")
            )
            roles_b, _ = self.build_roles(
                str(Path(directory) / "roles-b")
            )
            plan_a = self.verified_plan(
                roles_a, directory, variant="plan-a"
            )
            plan_b = self.verified_plan(
                roles_b, directory, variant="plan-b"
            )
            backend = authorities_module.open_native_protocol_core_for_test(
                plan_a
            )
            with self.assertRaises(CapabilityFailure):
                bootstrap_local_authorities(plan_b, backend)
            state = load_state(state_path)
            self.assertEqual(state["dispatch_count"], 0)
            self.assertEqual(state["mutation_count"], 0)

    def test_second_dispatch_is_denied_after_failed_first_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            preparation = roles["prepared"]
            for operation in (
                copy.copy,
                copy.deepcopy,
                pickle.dumps,
                json.dumps,
            ):
                with self.subTest(operation=operation.__name__):
                    with self.assertRaises(TypeError):
                        operation(preparation)
            plan = self.verified_plan(
                roles, directory, variant="one-use"
            )
            backend = authorities_module.open_native_protocol_core_for_test(
                plan
            )
            Path(directory, "fail-before-mutation").write_text("1")
            with reject_openssl_child():
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

    def test_timeout_after_real_reservation_reaps_broker_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            plan = self.verified_plan(
                roles,
                directory,
                variant="timeout-after-reservation",
            )
            backend = authorities_module.open_native_protocol_core_for_test(
                plan
            )
            Path(directory, "stall-before-mutation").write_text("1")
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ResourceWarning)
                with self.assertRaisesRegex(
                    CapabilityFailure,
                    "timed out|session|parent",
                ):
                    bootstrap_local_authorities(plan, backend)
                gc.collect()
            self.assertFalse(
                [
                    warning
                    for warning in caught
                    if issubclass(warning.category, ResourceWarning)
                ],
                "timeout leaked verifier subprocess pipes",
            )
            state = load_state(state_path)
            self.assertEqual(state["dispatch_count"], 1)
            self.assertEqual(state["reservation_count"], 1)
            self.assertEqual(state["mutation_count"], 0)
            broker_pid = state.get("broker_pid")
            self.assertIsInstance(broker_pid, int)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    os.kill(broker_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            with self.assertRaises(ProcessLookupError):
                os.kill(broker_pid, 0)
            with self.assertRaisesRegex(
                (CapabilityFailure, ValueError),
                "consumed|already attempted|trusted plan",
            ):
                bootstrap_local_authorities(plan, backend)
            self.assertEqual(load_state(state_path)["mutation_count"], 0)

    def test_broker_cannot_mutate_after_controller_owner_death(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path, _, _ = self.kill_controller_after_reservation(
                directory
            )
            state = load_state(state_path)
            self.assertEqual(state["reservation_count"], 1)
            self.assertEqual(state["mutation_count"], 0)

    def test_exact_reservation_recovers_without_private_controller_key(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path, fixture, _ = (
                self.kill_controller_after_reservation(directory)
            )
            self.assertEqual(load_state(state_path)["mutation_count"], 0)
            Path(directory, "stall-before-mutation").unlink()
            descriptor = AuthorityBootstrapDescriptor.from_document(
                fixture["descriptor"]
            )
            observations = {
                locator: {
                    "state": (
                        "present"
                        if locator == BOOTSTRAP_RECORD_LOCATOR
                        else "absent"
                    )
                }
                for locator in descriptor.locators
            }
            recovery_plan = verify_authority_bootstrap(
                fixture["final_plan"],
                fixture["descriptor"],
                expected_installation_id=INSTALLATION_ID,
                observations=observations,
                recovery=True,
            )
            backend = (
                authorities_module.open_native_protocol_core_for_test(
                    recovery_plan
                )
            )
            manifest = bootstrap_local_authorities(
                recovery_plan,
                backend,
            )
            state = load_state(state_path)
            self.assertEqual(
                manifest["pending_plan_commitment"],
                recovery_plan.pending_plan_commitment,
            )
            self.assertEqual(state["reservation_count"], 1)
            self.assertEqual(state["mutation_count"], 1)

    def test_recovery_rejects_every_changed_reservation_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path, fixture, _ = (
                self.kill_controller_after_reservation(directory)
            )
            Path(directory, "stall-before-mutation").unlink()
            descriptor = AuthorityBootstrapDescriptor.from_document(
                fixture["descriptor"]
            )
            observations = {
                locator: {
                    "state": (
                        "present"
                        if locator == BOOTSTRAP_RECORD_LOCATOR
                        else "absent"
                    )
                }
                for locator in descriptor.locators
            }
            pristine_state = load_state(state_path)
            wal_path = Path(descriptor.wal_locator)
            pristine_wal = wal_path.read_bytes()
            state_changes = {
                "reserved-request": (
                    "reserved_request_digest",
                    "0" * 64,
                ),
                "reserved-plan": (
                    "reserved_final_plan_digest",
                    "0" * 64,
                ),
                "reserved-operation": (
                    "reserved_operation",
                    "bootstrap-recover",
                ),
                "reserved-recovery": ("reserved_recovery", True),
                "reservation-state": (
                    "reservation_state",
                    "COMPLETE",
                ),
                "partial-item": ("mutation_count", 1),
            }
            authorization_changes = {
                "authorization-operation": (
                    "operation",
                    "bootstrap-recover",
                ),
                "recovery-policy": (
                    "recovery_policy",
                    "replace-or-resume",
                ),
                "wal": ("wal_digest", "0" * 64),
                "request": ("request_digest", "0" * 64),
                "final-plan": ("final_plan_digest", "0" * 64),
                "controller-key": (
                    "controller_public_key_digest",
                    "0" * 64,
                ),
                "verifier-pin": (
                    "verifier_code_directory_hash",
                    "0" * 40,
                ),
                "broker-pin": (
                    "broker_code_directory_hash",
                    "0" * 40,
                ),
                "provider": ("provider_kind", "macos-security"),
                "profile": ("build_profile", "production"),
                "signature": (
                    "signature",
                    base64.b64encode(b"invalid").decode(),
                ),
            }
            cases = {**state_changes, **authorization_changes}
            for case, (field, changed) in cases.items():
                with self.subTest(case=case):
                    state = json.loads(json.dumps(pristine_state))
                    if case in state_changes:
                        state[field] = changed
                        if case == "partial-item":
                            state["mutated_request_digest"] = "0" * 64
                    else:
                        authorization_data = base64.b64decode(
                            state[
                                "reserved_controller_authorization_base64"
                            ]
                        )
                        authorization = json.loads(authorization_data)
                        authorization[field] = changed
                        authorization_data = canonical_json_bytes(
                            authorization
                        )
                        encoded = base64.b64encode(
                            authorization_data
                        ).decode()
                        state[
                            "reserved_controller_authorization_base64"
                        ] = encoded
                        state[
                            "reserved_controller_authorization_digest"
                        ] = hashlib.sha256(
                            authorization_data
                        ).hexdigest()
                        state[
                            "reserved_controller_public_key_digest"
                        ] = authorization[
                            "controller_public_key_digest"
                        ]
                        state[
                            "reserved_controller_signature_digest"
                        ] = hashlib.sha256(
                            authorization["signature"].encode()
                        ).hexdigest()
                    state_path.write_bytes(canonical_json_bytes(state))
                    wal_path.write_bytes(pristine_wal)
                    recovery_plan = verify_authority_bootstrap(
                        fixture["final_plan"],
                        fixture["descriptor"],
                        expected_installation_id=INSTALLATION_ID,
                        observations=observations,
                        recovery=True,
                    )
                    backend = (
                        authorities_module.open_native_protocol_core_for_test(
                            recovery_plan
                        )
                    )
                    with self.assertRaises(CapabilityFailure):
                        bootstrap_local_authorities(
                            recovery_plan,
                            backend,
                        )
                    self.assertEqual(
                        load_state(state_path)["mutation_count"],
                        state["mutation_count"],
                    )

    def test_absent_reservation_cannot_start_native_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            original = self.verified_plan(
                roles,
                directory,
                variant="absent-recovery-reservation",
            )
            descriptor = original.descriptor
            absent = {
                locator: {"state": "absent"}
                for locator in descriptor.locators
            }
            recovery_plan = verify_authority_bootstrap(
                original.final_plan,
                descriptor.to_document(),
                expected_installation_id=INSTALLATION_ID,
                observations=absent,
                recovery=True,
            )
            with self.assertRaisesRegex(
                CapabilityFailure,
                "reservation",
            ):
                authorities_module.open_native_protocol_core_for_test(
                    recovery_plan
                )

            claimed_present = {
                **absent,
                BOOTSTRAP_RECORD_LOCATOR: {"state": "present"},
            }
            recovery_plan = verify_authority_bootstrap(
                original.final_plan,
                descriptor.to_document(),
                expected_installation_id=INSTALLATION_ID,
                observations=claimed_present,
                recovery=True,
            )
            backend = authorities_module.open_native_protocol_core_for_test(
                recovery_plan
            )
            with self.assertRaisesRegex(
                CapabilityFailure,
                "reservation|bootstrap",
            ):
                bootstrap_local_authorities(recovery_plan, backend)
            state = load_state(state_path)
            self.assertEqual(state["reservation_count"], 0)
            self.assertEqual(state["mutation_count"], 0)

    def test_oversized_request_cannot_block_before_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            started = time.monotonic()
            result = self.run_direct_verifier(
                roles,
                b"x" * 1_048_577,
                timeout=10,
            )
            elapsed = time.monotonic() - started
            self.assertNotEqual(result.returncode, 0)
            self.assertLess(elapsed, 5)
            state = load_state(state_path)
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
                roles, state_path = self.build_roles(directory)
                plan = self.verified_plan(
                    roles,
                    directory,
                    variant=case,
                )
                backend = (
                    authorities_module.open_native_protocol_core_for_test(
                        plan
                    )
                )
                Path(directory, "response-mutation").write_text(case)
                with self.assertRaises(CapabilityFailure):
                    bootstrap_local_authorities(plan, backend)
                state = load_state(state_path)
                self.assertEqual(state["accepted_response_count"], 0)
                self.assertEqual(state["reservation_count"], 1)
                self.assertEqual(state["mutation_count"], 1)

    def test_production_opener_rejects_signed_memory_test_roles_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            plan = self.verified_plan(
                roles, directory, variant="composition"
            )
            with self.assertRaisesRegex(
                CapabilityFailure,
                "production.*provider|test.*role",
            ):
                open_native_authority_backend(plan)
            state = load_state(state_path)
            self.assertEqual(state["dispatch_count"], 0)
            self.assertEqual(state["mutation_count"], 0)

    def test_real_swift_test_core_cannot_be_promoted_after_valid_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            plan = self.verified_plan(
                roles, directory, variant="non-qualifying-core"
            )
            opener = getattr(
                authorities_module,
                "open_native_protocol_core_for_test",
                None,
            )
            self.assertTrue(
                callable(opener),
                "explicit non-qualifying real Swift-core opener is missing",
            )
            backend = opener(plan)
            manifest = bootstrap_local_authorities(plan, backend)
            state = load_state(state_path)
            self.assertEqual(
                manifest["bootstrap_digest"],
                plan.descriptor_digest,
            )
            self.assertEqual(state["provider"], "signed-memory")
            self.assertEqual(state["dispatch_count"], 1)
            self.assertEqual(state["mutation_count"], 1)
            self.assertFalse(state["keychain_mutated"])
            self.assertFalse(state["user_presence_requested"])
            self.assertFalse(
                backend.qualifying,
                "deterministic Swift provider was promoted to qualifying",
            )

    def test_approved_custom_launcher_cannot_supply_test_sentinels(self):
        with tempfile.TemporaryDirectory() as directory:
            roles, state_path = self.build_roles(directory)
            plan = self.verified_plan(
                roles,
                directory,
                variant="custom-launcher-sentinels",
            )
            request = authorities_module._native_bootstrap_request(
                plan,
                {"wal_digest": "3" * 64},
            )
            result = self.run_direct_verifier(
                roles,
                canonical_json_bytes(request),
                extra_environment={
                    "AGENT_HARNESS_PROVIDER": "signed-memory",
                    "AGENT_HARNESS_FAKE_USER_PRESENCE": "approved",
                    "AGENT_HARNESS_FAKE_NATIVE_STATE": str(
                        Path(directory) / "foreign-state.json"
                    ),
                    "AGENT_HARNESS_TEST_BOOTSTRAP_CAPABILITY_FD": "99",
                    "AGENT_HARNESS_BOOTSTRAP_CONTROLLER_FD": "98",
                },
            )
            self.assertNotEqual(result.returncode, 0)
            state = load_state(state_path)
            self.assertEqual(state["dispatch_count"], 0)
            self.assertEqual(state["mutation_count"], 0)


if __name__ == "__main__":
    unittest.main()
