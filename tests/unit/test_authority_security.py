from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import harness_core.authorities as authorities_module
from harness_core.auth import create_test_integrity_authority
from harness_core.authorities import (
    ANCHOR_ITEM_LOCATOR,
    CapabilityFailure,
    TERMINAL_PIN_LOCATOR,
    bootstrap_authority,
    build_final_install_plan,
    create_test_approval_authority,
    create_test_live_anchor_broker,
    open_native_authority_backend,
    open_test_native_authority_backend,
    plan_authority_bootstrap,
    prepare_native_authority_roles,
    protected_interaction_for_test,
    verify_authority_bootstrap,
)
from harness_core.contracts import canonical_json_bytes, new_document
from tests.unit.support import (
    ANCHOR_COMMITMENT,
    CREATED_AT,
    INSTALLATION_ID,
    MemoryAuthorityBackend,
)
from tests.unit.test_authorities import requirements, setup_body


CREATOR_ID = "creator-123"
NAMESPACE = "agent-harness.installation-anchor.v1"
CONTROL_LOCATOR = "agent-harness.signing-key.v1"
BOOTSTRAP_CAPABILITY_DOMAIN = (
    b"agent-harness/native-bootstrap-capability/v1\0"
)


class NativeQualificationTests(unittest.TestCase):
    def test_caller_selected_fake_cannot_become_qualifying(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory).resolve() / "self-attesting-helper"
            fake.write_text(
                f"""#!{sys.executable}
import hashlib
import json
from pathlib import Path

path = Path(__file__).resolve()
print(json.dumps({{
    "protocol_version": 1,
    "code_identity": "caller-selected-helper",
    "content_digest": hashlib.sha256(path.read_bytes()).hexdigest(),
}}))
"""
            )
            fake.chmod(0o700)

            with self.assertRaisesRegex(
                CapabilityFailure,
                "trusted bootstrap plan",
            ):
                open_native_authority_backend(
                    fake,
                    expected_content_digest=hashlib.sha256(
                        fake.read_bytes()
                    ).hexdigest(),
                    expected_code_identity="caller-selected-helper",
                )

    def test_native_backend_revalidates_helper_before_each_call(self):
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory).resolve() / "native-helper"
            helper.write_bytes(fake.read_bytes())
            helper.chmod(0o700)
            state = Path(directory) / "state.json"
            wal = Path(directory) / "authority-bootstrap.wal"
            body = setup_body()
            descriptor = plan_authority_bootstrap(
                body.digest,
                requirements(
                    wal,
                    broker_locator=str(helper),
                    launcher_content_digest=hashlib.sha256(
                        helper.read_bytes()
                    ).hexdigest(),
                    launcher_code_identity="test-native-code-v1",
                    native_broker_content_digest=hashlib.sha256(
                        helper.read_bytes()
                    ).hexdigest(),
                    native_broker_code_identity="test-native-code-v1",
                ),
            )
            plan = build_final_install_plan(
                body,
                descriptor,
                created_at=CREATED_AT,
            )
            observations = MemoryAuthorityBackend(
                code_identity="test-native-code-v1"
            ).observe(descriptor.locators)
            verified = verify_authority_bootstrap(
                plan,
                descriptor.to_document(),
                expected_installation_id=INSTALLATION_ID,
                observations=observations,
            )
            backend = open_test_native_authority_backend(
                helper,
                state_path=state,
                transition_secret=b"qualified-native-transition-key",
            )
            bootstrap_authority(
                verified,
                backend,
                interaction=protected_interaction_for_test(
                    origin="local-cli",
                    stdin_is_tty=True,
                    user_presence=True,
                ),
            )
            self.assertFalse(backend.qualifying)

            replacement = Path(directory) / "replacement"
            marker = Path(directory) / "replacement-ran"
            replacement.write_text(
                "#!/bin/sh\n"
                f": > {marker}\n"
                "printf '{\"healthy\":true}\\n'\n"
            )
            replacement.chmod(0o700)
            os.replace(replacement, helper)

            with self.assertRaisesRegex(
                CapabilityFailure,
                "native authority changed after attestation",
            ):
                try:
                    backend.health()
                finally:
                    self.assertFalse(
                        marker.exists(),
                        "replacement helper executed before revalidation",
                    )

    @unittest.skipUnless(sys.platform == "darwin", "macOS native broker")
    def test_authority_wrapper_never_executes_poisoned_cached_binary(self):
        root = Path(__file__).parents[2]
        with tempfile.TemporaryDirectory() as directory:
            case_root = Path(directory).resolve()
            wrapper = case_root / "runtime/bin/ah-authority"
            source = case_root / "runtime/authority/macos-broker.swift"
            wrapper.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            wrapper.write_bytes(
                (root / "runtime/bin/ah-authority").read_bytes()
            )
            wrapper.chmod(0o700)
            source.write_bytes(
                (root / "runtime/authority/macos-broker.swift").read_bytes()
            )

            cache = source.parent / ".ah-authority-cache"
            cache.mkdir(mode=0o700)
            cached_binary = cache / "macos-broker"
            poison = (
                "#!/bin/sh\n"
                "echo CACHED_AUTHORITY_POISON_RAN >&2\n"
                "digest=$(/usr/bin/shasum -a 256 \"$0\" | "
                "/usr/bin/awk '{print $1}')\n"
                "printf '{\"protocol_version\":1,"
                "\"code_identity\":\"cache-poison\","
                "\"content_digest\":\"%s\"}\\n' \"$digest\"\n"
            )
            cached_binary.write_text(poison)
            cached_binary.chmod(0o500)
            poison_digest = hashlib.sha256(
                cached_binary.read_bytes()
            ).hexdigest()
            environment = {
                **os.environ,
                "AGENT_HARNESS_AUTHORITY_BINARY": str(cached_binary),
                "AGENT_HARNESS_AUTHORITY_CONTENT_DIGEST": poison_digest,
                "AGENT_HARNESS_AUTHORITY_CODE_IDENTITY": "cache-poison",
            }

            first = subprocess.run(
                [wrapper, "--attest"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
                timeout=60,
            )
            replacement = cache / "replacement"
            replacement.write_text(poison)
            replacement.chmod(0o500)
            os.replace(replacement, cached_binary)
            second = subprocess.run(
                [wrapper, "--attest"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
                timeout=60,
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            combined_stderr = first.stderr + second.stderr
            self.assertNotIn(
                "CACHED_AUTHORITY_POISON_RAN",
                combined_stderr,
                "wrapper executed a preseeded or replaced cached binary",
            )
            for result in (first, second):
                attestation = json.loads(result.stdout)
                self.assertNotEqual(
                    attestation["native_broker_code_identity"],
                    "cache-poison",
                )

    @unittest.skipUnless(sys.platform == "darwin", "macOS native broker")
    def test_authority_wrapper_never_executes_caller_path_tools(self):
        root = Path(__file__).parents[2]
        with tempfile.TemporaryDirectory() as directory:
            case_root = Path(directory).resolve()
            wrapper = case_root / "runtime/bin/ah-authority"
            source = case_root / "runtime/authority/macos-broker.swift"
            wrapper.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            wrapper.write_bytes(
                (root / "runtime/bin/ah-authority").read_bytes()
            )
            wrapper.chmod(0o700)
            source.write_bytes(
                (root / "runtime/authority/macos-broker.swift").read_bytes()
            )

            prewarm = subprocess.run(
                [wrapper, "--attest"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ,
                timeout=180,
            )
            self.assertEqual(prewarm.returncode, 0, prewarm.stderr)

            poison_path = case_root / "caller-path"
            poison_path.mkdir()
            marker = case_root / "caller-path-ran"
            for name in (
                "bash",
                "dirname",
                "readlink",
                "basename",
                "xcrun",
                "shasum",
                "stat",
                "awk",
            ):
                tool = poison_path / name
                tool.write_text(
                    "#!/bin/sh\n"
                    f"/usr/bin/printf '%s\\n' '{name}' >> '{marker}'\n"
                    "exit 97\n"
                )
                tool.chmod(0o700)

            result = subprocess.run(
                [wrapper, "--attest"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PATH": str(poison_path)},
                timeout=60,
            )

            self.assertFalse(
                marker.exists(),
                "wrapper executed caller PATH tool: "
                + (marker.read_text() if marker.exists() else ""),
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(sys.platform == "darwin", "macOS native broker")
    def test_real_wrapper_attestation_separates_launcher_and_native_broker(
        self,
    ):
        root = Path(__file__).parents[2]
        with tempfile.TemporaryDirectory() as directory:
            case_root = Path(directory).resolve()
            wrapper = case_root / "runtime/bin/ah-authority"
            source = case_root / "runtime/authority/macos-broker.swift"
            wrapper.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            wrapper.write_bytes(
                (root / "runtime/bin/ah-authority").read_bytes()
            )
            wrapper.chmod(0o700)
            source.write_bytes(
                (root / "runtime/authority/macos-broker.swift").read_bytes()
            )

            prepared = prepare_native_authority_roles(
                wrapper,
                case_root / "production-roles",
            )
            attestation = prepared.attestation
            wrapper_digest = hashlib.sha256(wrapper.read_bytes()).hexdigest()
            verifier_binary = prepared.verifier_path
            native_binary = case_root / "production-roles/macos-broker-internal"
            verifier_digest = hashlib.sha256(
                verifier_binary.read_bytes()
            ).hexdigest()
            native_digest = hashlib.sha256(
                native_binary.read_bytes()
            ).hexdigest()
            self.assertEqual(
                attestation["launcher_content_digest"],
                verifier_digest,
            )
            self.assertEqual(
                attestation["native_broker_content_digest"],
                native_digest,
            )
            self.assertNotEqual(wrapper_digest, verifier_digest)
            self.assertNotEqual(wrapper_digest, native_digest)
            self.assertNotEqual(verifier_digest, native_digest)
            self.assertNotEqual(
                attestation["launcher_code_identity"],
                attestation["native_broker_code_identity"],
            )
            self.assertIsInstance(
                attestation["native_broker_code_identity"],
                str,
            )

            body = setup_body()
            wal = case_root / "authority-bootstrap.wal"
            descriptor = plan_authority_bootstrap(
                body.digest,
                requirements(
                    wal,
                    broker_locator=str(verifier_binary),
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
            plan = build_final_install_plan(
                body,
                descriptor,
                created_at=CREATED_AT,
            )
            observations = MemoryAuthorityBackend(
                code_identity=attestation["native_broker_code_identity"]
            ).observe(descriptor.locators)
            verified = verify_authority_bootstrap(
                plan,
                descriptor.to_document(),
                expected_installation_id=INSTALLATION_ID,
                observations=observations,
                prepared_roles=prepared,
            )
            backend = open_native_authority_backend(verified)
            self.assertEqual(
                backend.code_identity,
                attestation["native_broker_code_identity"],
            )

            self_test = subprocess.run(
                [wrapper, "--self-test"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ,
                timeout=180,
            )
            self.assertEqual(self_test.returncode, 0, self_test.stderr)
            evidence = json.loads(self_test.stdout)
            self.assertTrue(evidence["launcher_native_binding_valid"])
            self.assertFalse(evidence["keychain_mutated"])
            self.assertFalse(evidence["user_presence_requested"])

    @unittest.skipUnless(sys.platform == "darwin", "macOS native broker")
    def test_authority_wrapper_recovers_stale_lock_and_preserves_live_lock(
        self,
    ):
        root = Path(__file__).parents[2]
        with tempfile.TemporaryDirectory() as directory:
            case_root = Path(directory).resolve()
            wrapper = case_root / "runtime/bin/ah-authority"
            source = case_root / "runtime/authority/macos-broker.swift"
            wrapper.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            wrapper.write_bytes(
                (root / "runtime/bin/ah-authority").read_bytes()
            )
            wrapper.chmod(0o700)
            source.write_bytes(
                (root / "runtime/authority/macos-broker.swift").read_bytes()
            )

            prewarm = subprocess.run(
                [wrapper, "--attest"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ,
                timeout=180,
            )
            self.assertEqual(prewarm.returncode, 0, prewarm.stderr)
            lock = source.parent / ".ah-authority-cache/.build-lock"
            lock.write_text("999999\n")
            lock.chmod(0o600)

            recovered = subprocess.run(
                [wrapper, "--attest"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ,
                timeout=60,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertFalse(lock.exists())

            owner = subprocess.Popen(["/bin/sleep", "30"])
            try:
                lock.write_text(f"{owner.pid}\n")
                lock.chmod(0o600)
                live_result = subprocess.run(
                    [wrapper, "--attest"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=os.environ,
                    timeout=60,
                )
                self.assertNotEqual(live_result.returncode, 0)
                self.assertIn("locked", live_result.stderr)
                self.assertEqual(lock.read_text(), f"{owner.pid}\n")
                self.assertIsNone(owner.poll())
            finally:
                owner.terminate()
                owner.wait(timeout=10)

    def test_direct_raw_native_bootstrap_cannot_provision(self):
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
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

            result = subprocess.run(
                [fake, "bootstrap"],
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
            self.assertFalse(state.exists())

    def test_custom_launcher_capability_cannot_bypass_user_presence(self):
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
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
            secret = b"custom-launcher-capability-key!!"
            request["bootstrap_authorization"] = hmac.new(
                secret,
                BOOTSTRAP_CAPABILITY_DOMAIN + canonical_json_bytes(request),
                hashlib.sha256,
            ).hexdigest()
            reader, writer = os.pipe()
            try:
                os.write(writer, secret)
            finally:
                os.close(writer)
            try:
                result = subprocess.run(
                    [fake, "bootstrap"],
                    input=canonical_json_bytes(request),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env={
                        **os.environ,
                        "AGENT_HARNESS_FAKE_NATIVE_STATE": str(state),
                        "AGENT_HARNESS_FAKE_USER_PRESENCE": "denied",
                        "AGENT_HARNESS_BOOTSTRAP_CAPABILITY_FD": str(reader),
                    },
                    pass_fds=(reader,),
                    timeout=30,
                )
            finally:
                os.close(reader)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(state.exists())

    def test_native_cas_crash_after_update_recovers_exact_receipt(self):
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            backend = open_test_native_authority_backend(
                fake,
                state_path=state,
            )
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
            unsigned = {
                "domain": "installation-transaction",
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
                "caller_code_identity": "caller-code-v1",
                "broker_code_identity": "broker-code-v1",
                "nonce": "crash-after-anchor-update",
                "expires_at": int(time.time()) + 300,
                "test_crash_after_update": True,
            }
            transition_key = b"fake-native-transition-key"
            encoded = canonical_json_bytes(unsigned)
            request = {
                **unsigned,
                "transition_domain": unsigned["domain"],
                "transition_digest": hashlib.sha256(
                    b"agent-harness/verified-anchor-transition/v1\0"
                    + encoded
                ).hexdigest(),
                "authorization_mac": hmac.new(
                    transition_key,
                    b"agent-harness/mac/anchor-transition-request/v1\0"
                    + encoded,
                    hashlib.sha256,
                ).hexdigest(),
            }
            environment = {
                **os.environ,
                "AGENT_HARNESS_FAKE_NATIVE_STATE": str(state),
                "AGENT_HARNESS_FAKE_TRANSITION_KEY":
                    transition_key.hex(),
            }
            first = subprocess.run(
                [fake, "anchor-compare-and-advance"],
                input=canonical_json_bytes(request),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                timeout=30,
            )
            self.assertNotEqual(first.returncode, 0)
            self.assertEqual(
                backend.anchor_read(NAMESPACE),
                (1, "9" * 64),
            )
            recovered = subprocess.run(
                [fake, "anchor-compare-and-advance"],
                input=canonical_json_bytes(request),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                timeout=30,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            receipt = json.loads(recovered.stdout)
            self.assertEqual(
                receipt["operation_id"],
                "crash-after-anchor-update",
            )
            self.assertEqual(
                receipt["transition_digest"],
                request["transition_digest"],
            )

    def test_direct_native_approval_rejects_semantic_drift_and_long_horizon(
        self,
    ):
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            backend = open_test_native_authority_backend(
                fake,
                state_path=state,
            )
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
            now = int(time.time())
            valid = {
                "schema": "agent-harness/external-write-envelope",
                "schema_version": 1,
                "installation_id": INSTALLATION_ID,
                "intent_digest": "1" * 64,
                "predecessor_task_event_hash": "2" * 64,
                "expires_at": datetime.fromtimestamp(
                    now + 300,
                    timezone.utc,
                ).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            invalid = (
                {**valid, "unreviewed_semantics": "write-anywhere"},
                {
                    **valid,
                    "expires_at": datetime.fromtimestamp(
                        now + 3_600,
                        timezone.utc,
                    ).isoformat(timespec="seconds").replace(
                        "+00:00",
                        "Z",
                    ),
                },
            )
            for envelope in invalid:
                with self.subTest(envelope=envelope):
                    request = {
                        "envelope_base64": base64.b64encode(
                            canonical_json_bytes(envelope)
                        ).decode(),
                        "summary": (
                            "Provider: example; operation: update; "
                            "target: page"
                        ),
                    }
                    result = subprocess.run(
                        [fake, "approval-sign"],
                        input=canonical_json_bytes(request),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env={
                            **os.environ,
                            "AGENT_HARNESS_FAKE_NATIVE_STATE":
                                str(state),
                        },
                        timeout=30,
                    )
                    self.assertNotEqual(result.returncode, 0)

    def test_verified_retirement_capability_is_single_use(self):
        issuer = getattr(
            authorities_module,
            "issue_authority_retirement",
            None,
        )
        self.assertIsNotNone(
            issuer,
            "verified retirement-capability issuer is missing",
        )
        fake = Path(__file__).with_name("fake_native_broker.py").resolve()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state = Path(directory) / "state.json"
            backend = open_test_native_authority_backend(
                fake,
                state_path=state,
            )
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
            memory = MemoryAuthorityBackend(
                code_identity=backend.code_identity
            )
            live_anchor = create_test_live_anchor_broker(
                memory,
                namespace=NAMESPACE,
                installation_id=INSTALLATION_ID,
                caller_code_identity="caller-code-v1",
                broker_code_identity=backend.code_identity,
                initial_generation=1,
                initial_commitment=ANCHOR_COMMITMENT,
            )
            integrity = create_test_integrity_authority(
                b"retirement-integrity-key",
                installation_id=INSTALLATION_ID,
            )
            anchor_receipt = new_document(
                "state-anchor-receipt",
                INSTALLATION_ID,
                created_at=CREATED_AT,
                anchor_namespace=NAMESPACE,
                anchor_backend_id="native-keychain-anchor-v1",
                receipt_key_id=f"broker-receipt:{INSTALLATION_ID}",
                transition_domain="installation-transaction",
                transition_digest="4" * 64,
                old_generation=0,
                old_commitment="0" * 64,
                new_generation=1,
                new_commitment=ANCHOR_COMMITMENT,
                operation_id="retirement-anchor-readback",
            )
            anchor_receipt["broker_receipt"] = memory.sign_receipt(
                canonical_json_bytes(anchor_receipt)
            )
            anchor_receipt["mac"] = integrity.mac_state_anchor_receipt(
                anchor_receipt
            )
            verified_anchor_receipt = (
                integrity.verify_state_anchor_receipt(
                    anchor_receipt,
                    expected_installation_id=INSTALLATION_ID,
                    expected_generation=1,
                    expected_anchor_commitment=ANCHOR_COMMITMENT,
                )
            )
            anchor_receipt_digest = hashlib.sha256(
                canonical_json_bytes(verified_anchor_receipt.document)
            ).hexdigest()
            attestation_core = {
                "installation_id": INSTALLATION_ID,
                "authority_era": "v1",
                "receipt_public_key_digest": "2" * 64,
                "helper_object_identity": "helper-v1",
                "helper_finalizer_digest": "3" * 64,
                "broker_code_identity": backend.code_identity,
                "anchor_namespace": NAMESPACE,
                "anchor_generation": 1,
                "anchor_commitment": ANCHOR_COMMITMENT,
                "terminal_pin_locator": TERMINAL_PIN_LOCATOR,
            }
            attestation_digest = hashlib.sha256(
                b"agent-harness/terminal-retirement-attestation/v1\0"
                + canonical_json_bytes(attestation_core)
            ).hexdigest()
            pin = {
                "installation_id": INSTALLATION_ID,
                "authority_era": "v1",
                "attestation_digest": attestation_digest,
                "receipt_public_key_digest": "2" * 64,
                "helper_object_identity": "helper-v1",
                "helper_finalizer_digest": "3" * 64,
            }
            terminal_attestation = {
                **attestation_core,
                "attestation_digest": attestation_digest,
                "broker_signature": hmac.new(
                    b"fake-native-receipt-key",
                    canonical_json_bytes(pin),
                    hashlib.sha256,
                ).hexdigest(),
            }
            finalizer = {
                "kind": "authority-retirement",
                "attestation_digest": attestation_digest,
                "receipt_public_key_digest": "2" * 64,
                "helper_object_identity": "helper-v1",
                "helper_finalizer_digest": "3" * 64,
                "authority_era": "v1",
                "terminal_pin_locator": TERMINAL_PIN_LOCATOR,
                "broker_code_identity": backend.code_identity,
                "anchor_namespace": NAMESPACE,
                "anchor_generation": 1,
                "anchor_commitment": ANCHOR_COMMITMENT,
                "anchor_receipt_digest": anchor_receipt_digest,
            }
            finalization = new_document(
                "finalization-plan",
                INSTALLATION_ID,
                created_at=CREATED_AT,
                generation=1,
                root=str(root),
                anchor_commitment=ANCHOR_COMMITMENT,
                lifecycle_phase="UNINSTALLED_PUBLISHED",
                owned_object_identities=["helper-v1"],
                containment_proof_digests=["3" * 64],
                finalizers=[finalizer],
                predecessor_generation=1,
            )
            finalization["plan_digest"] = hashlib.sha256(
                b"agent-harness/finalization-plan/v1\0"
                + canonical_json_bytes(finalization)
            ).hexdigest()
            verified_finalization = integrity.verify_finalization_plan(
                finalization,
                expected_installation_id=INSTALLATION_ID,
                expected_generation=1,
                expected_root=str(root),
                expected_anchor_commitment=ANCHOR_COMMITMENT,
            )
            summary_document = {
                **pin,
                "finalization_plan_digest":
                    finalization["plan_digest"],
                "anchor_receipt_digest": anchor_receipt_digest,
                "terminal_pin_locator": TERMINAL_PIN_LOCATOR,
            }
            summary = canonical_json_bytes(summary_document).decode()
            now = int(time.time())
            envelope = {
                "schema": "agent-harness/external-write-envelope",
                "schema_version": 1,
                "installation_id": INSTALLATION_ID,
                "intent_digest": hashlib.sha256(
                    summary.encode()
                ).hexdigest(),
                "predecessor_task_event_hash":
                    anchor_receipt_digest,
                "expires_at": datetime.fromtimestamp(
                    now + 300,
                    timezone.utc,
                ).isoformat(timespec="seconds").replace("+00:00", "Z"),
            }
            approval_authority = create_test_approval_authority(
                backend,
                expected_public_key_digest=
                    backend.approval_public_key_digest,
                broker_code_identity=backend.code_identity,
                current_time=now,
            )
            signature = approval_authority.approve_external_write(
                envelope,
                summary,
                interaction=protected_interaction_for_test(
                    origin="local-cli",
                    stdin_is_tty=True,
                    user_presence=True,
                ),
            )
            approval = {
                "envelope": envelope,
                "summary": summary,
                "signature": signature,
            }
            with self.assertRaises(TypeError):
                issuer(
                    {**pin, "broker_signature":
                        terminal_attestation["broker_signature"]},
                    live_anchor,
                    verified_anchor_receipt,
                    approval,
                    terminal_attestation,
                    terminal_attestation,
                    approval_authority=approval_authority,
                    backend=backend,
                    now=now,
                )
            capability = issuer(
                verified_finalization,
                live_anchor,
                verified_anchor_receipt,
                approval,
                terminal_attestation,
                json.loads(canonical_json_bytes(terminal_attestation)),
                approval_authority=approval_authority,
                backend=backend,
                now=now,
            )
            backend.add_retirement_pin(capability)
            with self.assertRaisesRegex(
                authorities_module.AuthorityError,
                "already consumed",
            ):
                backend.add_retirement_pin(capability)
            self.assertEqual(
                json.loads(state.read_text())["terminal_pin"],
                pin,
            )

    def test_native_core_bootstrap_installs_fixed_control_authority(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [root / "runtime/bin/ah-authority", "--self-test"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["raw_bootstrap_rejected"])
        self.assertTrue(evidence["control_authority_provisioned"])
        self.assertEqual(evidence["control_locator"], CONTROL_LOCATOR)
        self.assertEqual(evidence["anchor_locator"], ANCHOR_ITEM_LOCATOR)
        self.assertTrue(evidence["phase_mac_round_trip"])
        self.assertFalse(evidence["keychain_mutated"])


if __name__ == "__main__":
    unittest.main()
