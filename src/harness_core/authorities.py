from __future__ import annotations

import base64
import copy
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import threading
import time
from typing import Callable, Mapping
import uuid

from .auth import (
    IntegrityAuthority,
    VerifiedFinalizationPlan,
    VerifiedInstallationState,
    VerifiedStateAnchorReceipt,
)
from .contracts import (
    FINAL_INSTALL_PLAN_DOMAIN,
    canonical_json_bytes,
    new_document,
    require_document,
    require_rfc3339_utc,
)


APPROVAL_KEY_LOCATOR = "agent-harness.authority.approval-key.v1"
ANCHOR_ITEM_LOCATOR = "agent-harness.authority.anchor.v1"
RECEIPT_KEY_LOCATOR = "agent-harness.authority.broker-receipt-key.v1"
BOOTSTRAP_RECORD_LOCATOR = "agent-harness.authority.bootstrap-record.v1"
TERMINAL_PIN_LOCATOR = "agent-harness.authority.terminal-pin.v1"
INTEGRITY_KEY_LOCATOR = "agent-harness.signing-key.v1"

_BOOTSTRAP_CAPABILITY_DOMAIN = (
    b"agent-harness/native-bootstrap-capability/v1\0"
)

AUTHORITY_BOOTSTRAP_CRASH_POINTS = (
    "before_wal_write",
    "after_wal_fsync",
    "before_broker_dispatch",
    "before_approval_add",
    "after_approval_add",
    "before_anchor_add",
    "after_anchor_add",
    "before_receipt_key_add",
    "after_receipt_key_add",
    "before_bootstrap_record_add",
    "after_bootstrap_record_add",
    "after_broker_dispatch",
    "before_manifest_readback",
    "after_manifest_readback",
    "before_wal_complete",
    "after_wal_complete",
)

_SETUP_DOMAIN = b"agent-harness/setup-body/v1\0"
_BOOTSTRAP_DOMAIN = b"agent-harness/authority-bootstrap-descriptor/v1\0"
_BOOTSTRAP_WAL_DOMAIN = b"agent-harness/authority-bootstrap-wal/v1\0"
_BOOTSTRAP_TOKEN = object()
_TRANSITION_TOKEN = object()
_RETIREMENT_TOKEN = object()
_INTERACTION_TOKEN = object()
_TEST_AUTHORITY_TOKEN = object()
_LOCK_GUARD = threading.Lock()
_BOOTSTRAP_LOCKS: dict[str, threading.Lock] = {}
_ANCHOR_LOCKS: dict[tuple[int, str], threading.Lock] = {}


class AuthorityError(ValueError):
    pass


class CapabilityFailure(AuthorityError):
    pass


class InjectedAuthorityCrash(RuntimeError):
    pass


class VerifiedAuthorityRetirementPlan:
    __slots__ = ("__document", "__consumed")

    def __init__(self, token: object, document: Mapping[str, object]) -> None:
        if token is not _RETIREMENT_TOKEN:
            raise TypeError(
                "VerifiedAuthorityRetirementPlan cannot be constructed directly"
            )
        self.__document = canonical_json_bytes(document)
        self.__consumed = False

    def consume(self) -> dict[str, object]:
        if self.__consumed:
            raise AuthorityError("authority retirement plan already consumed")
        self.__consumed = True
        return json.loads(self.__document)

    def __reduce__(self):
        raise TypeError("VerifiedAuthorityRetirementPlan is non-serializable")


_NATIVE_BACKEND_TOKEN = object()


class NativeAuthorityBackend:
    __slots__ = (
        "__executable",
        "__environment",
        "__attestation",
        "__qualifying",
        "__bootstrap_capability",
        "__trusted_plan_digest",
        "__test_backend",
        "__verified_manifest",
        "__executable_device",
        "__executable_inode",
        "__launcher_content_digest",
        "__launcher_code_identity",
        "__native_broker_content_digest",
        "__native_broker_code_identity",
    )

    def __init__(
        self,
        token: object,
        executable: Path,
        environment: Mapping[str, str],
        attestation: Mapping[str, object],
        *,
        qualifying: bool,
        bootstrap_capability: bytes,
        trusted_plan_digest: str | None,
        test_backend: bool,
    ) -> None:
        if token is not _NATIVE_BACKEND_TOKEN:
            raise TypeError("NativeAuthorityBackend requires verified attestation")
        self.__executable = executable
        self.__environment = dict(environment)
        self.__attestation = _json_copy(attestation)
        self.__qualifying = qualifying
        self.__bootstrap_capability = bytes(bootstrap_capability)
        self.__trusted_plan_digest = trusted_plan_digest
        self.__test_backend = test_backend
        self.__verified_manifest: bytes | None = None
        (
            self.__executable_device,
            self.__executable_inode,
            self.__launcher_content_digest,
        ) = self.__read_executable_witness()
        self.__launcher_code_identity = str(
            attestation["launcher_code_identity"]
        )
        self.__native_broker_content_digest = str(
            attestation["native_broker_content_digest"]
        )
        self.__native_broker_code_identity = str(
            attestation["native_broker_code_identity"]
        )
        if not hmac.compare_digest(
            self.__launcher_content_digest,
            str(attestation["launcher_content_digest"]),
        ):
            raise CapabilityFailure("native authority changed after attestation")

    @property
    def qualifying(self) -> bool:
        return self.__qualifying

    @property
    def code_identity(self) -> str:
        return self.__native_broker_code_identity

    @property
    def approval_public_key_digest(self) -> str:
        value = self.health().get("approval_public_key_digest")
        if not isinstance(value, str):
            raise CapabilityFailure("native approval public key is unavailable")
        return value

    @property
    def user_presence_available(self) -> bool:
        return bool(self.health().get("user_presence_available", True))

    def __read_executable_witness(self) -> tuple[int, int, str]:
        try:
            descriptor = os.open(
                self.__executable,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
        except OSError as error:
            raise CapabilityFailure(
                "native authority changed after attestation"
            ) from error
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_mode & 0o111 == 0
            ):
                raise CapabilityFailure(
                    "native authority changed after attestation"
                )
            with os.fdopen(os.dup(descriptor), "rb") as source:
                digest = hashlib.sha256(source.read()).hexdigest()
            return metadata.st_dev, metadata.st_ino, digest
        finally:
            os.close(descriptor)

    def __revalidate_executable(self) -> None:
        device, inode, digest = self.__read_executable_witness()
        if (
            device != self.__executable_device
            or inode != self.__executable_inode
            or not hmac.compare_digest(
                digest, self.__launcher_content_digest
            )
        ):
            raise CapabilityFailure("native authority changed after attestation")

    def __verify_current_attestation(
        self,
        environment: Mapping[str, str],
    ) -> None:
        self.__revalidate_executable()
        probe = subprocess.run(
            [str(self.__executable), "--attest"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=30,
        )
        if probe.returncode != 0:
            raise CapabilityFailure("native authority attestation failed")
        try:
            attestation = json.loads(probe.stdout)
        except json.JSONDecodeError as error:
            raise CapabilityFailure(
                "native authority attestation is malformed"
            ) from error
        if (
            not isinstance(attestation, dict)
            or attestation.get("protocol_version") != 1
            or not hmac.compare_digest(
                str(attestation.get("launcher_content_digest")),
                self.__launcher_content_digest,
            )
            or attestation.get("launcher_code_identity")
            != self.__launcher_code_identity
            or not hmac.compare_digest(
                str(attestation.get("native_broker_content_digest")),
                self.__native_broker_content_digest,
            )
            or attestation.get("native_broker_code_identity")
            != self.__native_broker_code_identity
        ):
            raise CapabilityFailure("native authority attestation mismatch")

    def _request(
        self,
        command: str,
        value: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        request_value = None if value is None else _json_copy(value)
        environment = dict(self.__environment)
        self.__verify_current_attestation(environment)
        self.__revalidate_executable()
        inherited: tuple[int, ...] = ()
        capability_fd: int | None = None
        if command in {"bootstrap", "bootstrap-recover"}:
            if request_value is None:
                raise CapabilityFailure("native bootstrap request is required")
            unsigned = {
                key: item
                for key, item in request_value.items()
                if key != "bootstrap_authorization"
            }
            request_value["bootstrap_authorization"] = hmac.new(
                self.__bootstrap_capability,
                _BOOTSTRAP_CAPABILITY_DOMAIN + canonical_json_bytes(unsigned),
                hashlib.sha256,
            ).hexdigest()
            capability_fd, writer = os.pipe()
            try:
                os.write(writer, self.__bootstrap_capability)
            finally:
                os.close(writer)
            environment["AGENT_HARNESS_BOOTSTRAP_CAPABILITY_FD"] = str(
                capability_fd
            )
            inherited = (capability_fd,)
        try:
            result = subprocess.run(
                [str(self.__executable), command],
                input=(
                    None
                    if request_value is None
                    else canonical_json_bytes(request_value)
                ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                pass_fds=inherited,
                timeout=30,
            )
        finally:
            if capability_fd is not None:
                os.close(capability_fd)
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise CapabilityFailure(
                f"native authority {command} failed: {detail}"
            )
        if len(result.stdout) > 1_048_576:
            raise CapabilityFailure("native authority response exceeds size limit")
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise CapabilityFailure(
                f"native authority {command} returned malformed JSON"
            ) from error
        if not isinstance(response, dict):
            raise CapabilityFailure(
                f"native authority {command} response must be an object"
            )
        return response

    def health(self) -> dict[str, object]:
        response = self._request("health")
        if response.get("code_identity") != self.code_identity:
            raise CapabilityFailure("native authority code identity drift")
        return response

    def bootstrap(self, request: Mapping[str, object]) -> dict[str, object]:
        return self._request("bootstrap", request)

    def recover_bootstrap(
        self, request: Mapping[str, object]
    ) -> dict[str, object]:
        return self._request("bootstrap-recover", request)

    def add_retirement_pin(
        self, plan: VerifiedAuthorityRetirementPlan
    ) -> None:
        if not isinstance(plan, VerifiedAuthorityRetirementPlan):
            raise TypeError("VerifiedAuthorityRetirementPlan required")
        response = self._request("retirement-pin", plan.consume())
        if response.get("ok") is not True:
            raise CapabilityFailure("native retirement pin readback failed")

    def verify_bootstrap_manifest(self, manifest: object) -> bool:
        if not isinstance(manifest, Mapping):
            return False
        signature = manifest.get("broker_signature")
        if not isinstance(signature, str):
            return False
        unsigned = {
            key: item
            for key, item in manifest.items()
            if key != "broker_signature"
        }
        try:
            response = self._request(
                "receipt-verify",
                {
                    "payload_base64": base64.b64encode(
                        canonical_json_bytes(unsigned)
                    ).decode(),
                    "signature": signature,
                },
            )
        except CapabilityFailure:
            return False
        return response.get("valid") is True

    def _accept_verified_manifest(
        self,
        plan: VerifiedAuthorityBootstrapPlan,
        manifest: Mapping[str, object],
    ) -> None:
        if self.__test_backend:
            return
        if self.__trusted_plan_digest != plan.descriptor_digest:
            raise CapabilityFailure("native authority trusted plan mismatch")
        self.__verified_manifest = canonical_json_bytes(manifest)
        self.__qualifying = True

    def anchor_read(self, namespace: str) -> tuple[int, str]:
        response = self._request("anchor-read", {"namespace": namespace})
        if response.get("namespace") != namespace:
            raise CapabilityFailure("native anchor namespace mismatch")
        generation = response.get("generation")
        commitment = response.get("commitment")
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or not isinstance(commitment, str)
        ):
            raise CapabilityFailure("native anchor response is malformed")
        return generation, commitment

    def compare_and_advance(
        self, transition: VerifiedAnchorTransition
    ) -> dict[str, object]:
        if not isinstance(transition, VerifiedAnchorTransition):
            raise TypeError("VerifiedAnchorTransition required")
        document = transition.consume()
        request = _json_copy(document)
        request["transition_domain"] = request.get(
            "domain", "installation-transaction"
        )
        request["transition_digest"] = _domain_digest(
            b"agent-harness/verified-anchor-transition/v1\0",
            {
                key: item
                for key, item in document.items()
                if key != "authorization_mac"
            },
        )
        return self._request("anchor-compare-and-advance", request)

    def verify_receipt(self, receipt: object) -> bool:
        if not isinstance(receipt, Mapping):
            return False
        signature = receipt.get("broker_receipt")
        if not isinstance(signature, str):
            return False
        unsigned = {
            key: item for key, item in receipt.items() if key != "broker_receipt"
        }
        try:
            response = self._request(
                "receipt-verify",
                {
                    "payload_base64": base64.b64encode(
                        canonical_json_bytes(unsigned)
                    ).decode(),
                    "signature": signature,
                },
            )
        except CapabilityFailure:
            return False
        return response.get("valid") is True

    def approve(
        self,
        envelope: bytes,
        summary: bytes,
        *,
        protected_user_presence: bool,
    ) -> dict[str, object]:
        if not protected_user_presence:
            raise CapabilityFailure("protected user presence is required")
        return self._request(
            "approval-sign",
            {
                "envelope_base64": base64.b64encode(envelope).decode(),
                "summary": summary.decode(),
            },
        )

    def verify_approval(
        self,
        envelope: bytes,
        summary: bytes,
        signature: object,
    ) -> bool:
        if not isinstance(signature, Mapping):
            return False
        try:
            response = self._request(
                "approval-verify",
                {
                    "envelope_base64": base64.b64encode(envelope).decode(),
                    "summary": summary.decode(),
                    "approval": signature,
                },
            )
        except CapabilityFailure:
            return False
        return response.get("valid") is True


def _attest_native_executable(
    executable: Path | str,
    *,
    environment: Mapping[str, str],
) -> tuple[Path, str, dict[str, object]]:
    requested = Path(executable)
    if not requested.is_absolute():
        raise CapabilityFailure("native authority path must be absolute")
    resolved = requested.resolve(strict=True)
    if resolved != requested or requested.is_symlink():
        raise CapabilityFailure("native authority path must be canonical")
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
            raise CapabilityFailure(
                "native authority must be a regular executable"
            )
        with os.fdopen(os.dup(descriptor), "rb") as source:
            content_digest = hashlib.sha256(source.read()).hexdigest()
    finally:
        os.close(descriptor)
    probe = subprocess.run(
        [str(resolved), "--attest"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        timeout=30,
    )
    if probe.returncode != 0:
        raise CapabilityFailure(
            "native authority attestation failed: "
            + probe.stderr.decode("utf-8", "replace").strip()
        )
    try:
        attestation = json.loads(probe.stdout)
    except json.JSONDecodeError as error:
        raise CapabilityFailure("native authority attestation is malformed") from error
    if (
        not isinstance(attestation, dict)
        or attestation.get("protocol_version") != 1
        or attestation.get("launcher_content_digest") != content_digest
        or not isinstance(attestation.get("launcher_code_identity"), str)
        or not isinstance(
            attestation.get("native_broker_content_digest"), str
        )
        or not isinstance(attestation.get("native_broker_code_identity"), str)
    ):
        raise CapabilityFailure("native authority attestation mismatch")
    if hashlib.sha256(resolved.read_bytes()).hexdigest() != content_digest:
        raise CapabilityFailure("native authority changed after attestation")
    return resolved, content_digest, attestation


def open_test_native_authority_backend(
    executable: Path | str,
    *,
    state_path: Path | str,
    transition_secret: bytes = b"fake-native-transition-key",
) -> NativeAuthorityBackend:
    if not isinstance(transition_secret, bytes) or not transition_secret:
        raise ValueError("test transition secret must be non-empty bytes")
    environment = {
        **os.environ,
        "AGENT_HARNESS_FAKE_NATIVE_STATE": str(Path(state_path).resolve()),
        "AGENT_HARNESS_FAKE_TRANSITION_KEY": transition_secret.hex(),
        "AGENT_HARNESS_FAKE_USER_PRESENCE": "approved",
    }
    resolved, _, attestation = _attest_native_executable(
        executable, environment=environment
    )
    return NativeAuthorityBackend(
        _NATIVE_BACKEND_TOKEN,
        resolved,
        environment,
        attestation,
        qualifying=False,
        bootstrap_capability=hashlib.sha256(transition_secret).digest(),
        trusted_plan_digest=None,
        test_backend=True,
    )


def open_native_authority_backend(
    plan: object,
    **caller_assertions: object,
) -> NativeAuthorityBackend:
    if (
        caller_assertions
        or not isinstance(plan, VerifiedAuthorityBootstrapPlan)
    ):
        raise CapabilityFailure(
            "qualifying native authority requires a trusted bootstrap plan"
        )
    descriptor = plan.descriptor
    executable = Path(descriptor.broker_locator)
    if not executable.is_absolute():
        raise CapabilityFailure(
            "trusted bootstrap helper locator must be absolute"
        )
    environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    resolved, content_digest, attestation = _attest_native_executable(
        executable, environment=environment
    )
    if (
        not hmac.compare_digest(
            content_digest, descriptor.launcher_content_digest
        )
        or attestation["launcher_code_identity"]
        != descriptor.launcher_code_identity
        or not hmac.compare_digest(
            attestation["native_broker_content_digest"],
            descriptor.native_broker_content_digest,
        )
        or attestation["native_broker_code_identity"]
        != descriptor.native_broker_code_identity
    ):
        raise CapabilityFailure("native authority pinned identity mismatch")
    return NativeAuthorityBackend(
        _NATIVE_BACKEND_TOKEN,
        resolved,
        environment,
        attestation,
        qualifying=False,
        bootstrap_capability=plan._native_bootstrap_secret(),
        trusted_plan_digest=plan.descriptor_digest,
        test_backend=False,
    )


def _domain_digest(domain: bytes, value: object) -> str:
    return hashlib.sha256(domain + canonical_json_bytes(value)).hexdigest()


def _json_copy(value: object):
    return json.loads(canonical_json_bytes(value))


def _source_document(value: object) -> dict[str, object]:
    if hasattr(value, "to_document"):
        value = value.to_document()
    if not isinstance(value, Mapping):
        raise AuthorityError("source identity must be a mapping")
    document = _json_copy(value)
    required = {
        "algorithm",
        "algorithm_version",
        "inclusion_policy",
        "policy_version",
        "ordered_manifest_digest",
        "source_commit",
        "frozen_snapshot_digest",
        "digest",
        "entries",
    }
    if not required <= set(document):
        raise AuthorityError("source identity is incomplete")
    return document


@dataclass(frozen=True)
class SetupBodyV1:
    installation_id: str
    runtime_root: str
    rollback_root: str
    source_identity: object
    adapter_plan_digests: tuple[str, ...]
    operations: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        try:
            uuid.UUID(self.installation_id)
        except (AttributeError, TypeError, ValueError) as error:
            raise AuthorityError("installation_id must be a UUID") from error
        if not Path(self.runtime_root).is_absolute() or not Path(
            self.rollback_root
        ).is_absolute():
            raise AuthorityError("setup roots must be absolute")
        if isinstance(self.adapter_plan_digests, list):
            object.__setattr__(
                self, "adapter_plan_digests", tuple(self.adapter_plan_digests)
            )
        if isinstance(self.operations, list):
            object.__setattr__(self, "operations", tuple(self.operations))
        if any(not isinstance(value, str) for value in self.adapter_plan_digests):
            raise AuthorityError("adapter plan digests must be strings")

    def to_document(self) -> dict[str, object]:
        return {
            "installation_id": self.installation_id,
            "runtime_root": self.runtime_root,
            "rollback_root": self.rollback_root,
            "source_identity": _source_document(self.source_identity),
            "adapter_plan_digests": list(self.adapter_plan_digests),
            "operations": [_json_copy(value) for value in self.operations],
        }

    @property
    def digest(self) -> str:
        return _domain_digest(_SETUP_DOMAIN, self.to_document())

    @classmethod
    def from_final_plan(cls, document: Mapping[str, object]) -> SetupBodyV1:
        required = (
            "installation_id",
            "runtime_root",
            "rollback_root",
            "source_content_identity",
            "adapter_plan_digests",
            "operations",
        )
        if any(name not in document for name in required):
            raise AuthorityError("final plan omits setup-body field")
        source = document["source_content_identity"]
        if (
            not isinstance(source, Mapping)
            or document.get("source_commit") != source.get("source_commit")
        ):
            raise AuthorityError("source commit/content identity mismatch")
        adapter_digests = document["adapter_plan_digests"]
        operations = document["operations"]
        if not isinstance(adapter_digests, list) or not isinstance(operations, list):
            raise AuthorityError("setup-body collections are malformed")
        return cls(
            installation_id=document["installation_id"],
            runtime_root=document["runtime_root"],
            rollback_root=document["rollback_root"],
            source_identity=source,
            adapter_plan_digests=tuple(adapter_digests),
            operations=tuple(operations),
        )


def _default_item_attributes() -> dict[str, object]:
    return {
        "approval_key": {
            "key_type": "SecureEnclaveP256",
            "non_exportable": True,
            "synchronizable": False,
            "accessibility": "WhenUnlockedThisDeviceOnly",
            "access_control": ["privateKeyUsage", "userPresence"],
        },
        "anchor": {
            "non_exportable": True,
            "synchronizable": False,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
            "code_identity_restricted": True,
        },
        "receipt_key": {
            "key_type": "P256",
            "non_exportable": True,
            "synchronizable": False,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
            "code_identity_restricted": True,
        },
        "integrity_key": {
            "key_type": "HMAC-SHA256",
            "non_exportable": True,
            "synchronizable": False,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
            "code_identity_restricted": True,
        },
        "bootstrap_record": {
            "add_only": True,
            "contains_key_material": False,
            "synchronizable": False,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
        },
        "terminal_pin": {
            "add_only": True,
            "contains_key_material": False,
            "synchronizable": False,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
        },
    }


@dataclass(frozen=True)
class AuthorityBootstrapRequirements:
    installation_id: str
    creator_id: str
    launcher_code_identity: str
    launcher_content_digest: str
    native_broker_code_identity: str
    native_broker_content_digest: str
    wal_locator: str
    initial_anchor_namespace: str
    initial_anchor_generation: int
    initial_anchor_commitment: str
    broker_locator: str = "runtime/bin/ah-authority"
    approval_key_locator: str = APPROVAL_KEY_LOCATOR
    anchor_item_locator: str = ANCHOR_ITEM_LOCATOR
    receipt_key_locator: str = RECEIPT_KEY_LOCATOR
    integrity_key_locator: str = INTEGRITY_KEY_LOCATOR
    bootstrap_record_locator: str = BOOTSTRAP_RECORD_LOCATOR
    terminal_pin_locator: str = TERMINAL_PIN_LOCATOR
    item_attributes: Mapping[str, object] = field(
        default_factory=_default_item_attributes
    )
    capabilities: tuple[str, ...] = (
        "protected-user-presence-approval",
        "installation-anchor-cas",
        "broker-signed-receipts",
        "retirement-terminal-pin-add",
    )

    def __post_init__(self) -> None:
        try:
            uuid.UUID(self.installation_id)
        except (AttributeError, TypeError, ValueError) as error:
            raise AuthorityError("installation_id must be a UUID") from error
        if not Path(self.wal_locator).is_absolute():
            raise AuthorityError("authority WAL locator must be absolute")
        if (
            isinstance(self.initial_anchor_generation, bool)
            or not isinstance(self.initial_anchor_generation, int)
            or self.initial_anchor_generation != 0
        ):
            raise AuthorityError("initial anchor generation must be zero")


@dataclass(frozen=True)
class AuthorityBootstrapDescriptor:
    setup_body_digest: str
    installation_id: str
    creator_id: str
    broker_locator: str
    launcher_code_identity: str
    launcher_content_digest: str
    native_broker_code_identity: str
    native_broker_content_digest: str
    wal_locator: str
    locator_map: Mapping[str, str]
    item_attributes: Mapping[str, object]
    capabilities: tuple[str, ...]
    conditional_inverses: tuple[Mapping[str, object], ...]
    initial_anchor_namespace: str
    initial_anchor_generation: int
    initial_anchor_commitment: str

    @property
    def locators(self) -> tuple[str, ...]:
        return tuple(self.locator_map.values())

    def to_document(self) -> dict[str, object]:
        return {
            "setup_body_digest": self.setup_body_digest,
            "installation_id": self.installation_id,
            "creator_id": self.creator_id,
            "broker_locator": self.broker_locator,
            "launcher_code_identity": self.launcher_code_identity,
            "launcher_content_digest": self.launcher_content_digest,
            "native_broker_code_identity": self.native_broker_code_identity,
            "native_broker_content_digest":
                self.native_broker_content_digest,
            "wal_locator": self.wal_locator,
            "locators": _json_copy(self.locator_map),
            "item_attributes": _json_copy(self.item_attributes),
            "capabilities": list(self.capabilities),
            "conditional_inverses": _json_copy(self.conditional_inverses),
            "initial_anchor": {
                "namespace": self.initial_anchor_namespace,
                "generation": self.initial_anchor_generation,
                "commitment": self.initial_anchor_commitment,
            },
        }

    @property
    def digest(self) -> str:
        return _domain_digest(_BOOTSTRAP_DOMAIN, self.to_document())

    @classmethod
    def from_document(
        cls, value: Mapping[str, object]
    ) -> AuthorityBootstrapDescriptor:
        required = {
            "setup_body_digest",
            "installation_id",
            "creator_id",
            "broker_locator",
            "launcher_code_identity",
            "launcher_content_digest",
            "native_broker_code_identity",
            "native_broker_content_digest",
            "wal_locator",
            "locators",
            "item_attributes",
            "capabilities",
            "conditional_inverses",
            "initial_anchor",
        }
        if set(value) != required:
            raise AuthorityError("authority bootstrap descriptor fields mismatch")
        locators = value["locators"]
        anchor = value["initial_anchor"]
        if not isinstance(locators, Mapping) or not isinstance(anchor, Mapping):
            raise AuthorityError("authority bootstrap descriptor is malformed")
        expected_locator_names = {
            "approval_key",
            "anchor",
            "receipt_key",
            "integrity_key",
            "bootstrap_record",
            "terminal_pin",
        }
        if set(locators) != expected_locator_names:
            raise AuthorityError("authority bootstrap fixed locators mismatch")
        return cls(
            setup_body_digest=value["setup_body_digest"],
            installation_id=value["installation_id"],
            creator_id=value["creator_id"],
            broker_locator=value["broker_locator"],
            launcher_code_identity=value["launcher_code_identity"],
            launcher_content_digest=value["launcher_content_digest"],
            native_broker_code_identity=value["native_broker_code_identity"],
            native_broker_content_digest=value[
                "native_broker_content_digest"
            ],
            wal_locator=value["wal_locator"],
            locator_map=dict(locators),
            item_attributes=value["item_attributes"],
            capabilities=tuple(value["capabilities"]),
            conditional_inverses=tuple(value["conditional_inverses"]),
            initial_anchor_namespace=anchor.get("namespace"),
            initial_anchor_generation=anchor.get("generation"),
            initial_anchor_commitment=anchor.get("commitment"),
        )


def plan_authority_bootstrap(
    setup_body_digest: str,
    requirements: AuthorityBootstrapRequirements,
) -> AuthorityBootstrapDescriptor:
    if not isinstance(setup_body_digest, str) or len(setup_body_digest) != 64:
        raise AuthorityError("setup-body digest must be SHA-256")
    locator_map = {
        "approval_key": requirements.approval_key_locator,
        "anchor": requirements.anchor_item_locator,
        "receipt_key": requirements.receipt_key_locator,
        "integrity_key": requirements.integrity_key_locator,
        "bootstrap_record": requirements.bootstrap_record_locator,
        "terminal_pin": requirements.terminal_pin_locator,
    }
    inverses = tuple(
        {
            "operation": "remove-exact-add-result",
            "locator": locator,
            "requires_markers": [
                "installation_id",
                "creator_id",
                "broker_code_identity",
                "bootstrap_digest",
                "wal_digest",
            ],
        }
        for name, locator in locator_map.items()
        if name != "terminal_pin"
    )
    return AuthorityBootstrapDescriptor(
        setup_body_digest=setup_body_digest,
        installation_id=requirements.installation_id,
        creator_id=requirements.creator_id,
        broker_locator=requirements.broker_locator,
        launcher_code_identity=requirements.launcher_code_identity,
        launcher_content_digest=requirements.launcher_content_digest,
        native_broker_code_identity=requirements.native_broker_code_identity,
        native_broker_content_digest=
            requirements.native_broker_content_digest,
        wal_locator=requirements.wal_locator,
        locator_map=locator_map,
        item_attributes=_json_copy(requirements.item_attributes),
        capabilities=tuple(requirements.capabilities),
        conditional_inverses=inverses,
        initial_anchor_namespace=requirements.initial_anchor_namespace,
        initial_anchor_generation=requirements.initial_anchor_generation,
        initial_anchor_commitment=requirements.initial_anchor_commitment,
    )


def build_final_install_plan(
    body: SetupBodyV1,
    descriptor: AuthorityBootstrapDescriptor,
    *,
    created_at: str,
) -> dict[str, object]:
    if descriptor.setup_body_digest != body.digest:
        raise AuthorityError("descriptor is not linked to setup body")
    source = _source_document(body.source_identity)
    plan = new_document(
        "install-plan",
        body.installation_id,
        created_at=created_at,
        runtime_root=body.runtime_root,
        rollback_root=body.rollback_root,
        source_commit=source["source_commit"],
        source_content_identity=source,
        setup_body_digest=body.digest,
        authority_bootstrap=descriptor.to_document(),
        authority_bootstrap_digest=descriptor.digest,
        adapter_plan_digests=list(body.adapter_plan_digests),
        operations=[_json_copy(value) for value in body.operations],
    )
    plan["plan_digest"] = final_install_plan_digest(plan)
    return plan


def final_install_plan_digest(value: Mapping[str, object]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "plan_digest"}
    return _domain_digest(FINAL_INSTALL_PLAN_DOMAIN, unsigned)


class VerifiedAuthorityBootstrapPlan:
    __slots__ = (
        "__final_plan",
        "__descriptor",
        "__observations",
        "__consumed",
        "__recovery",
        "__installation_id",
        "__setup_body_digest",
        "__descriptor_digest",
        "__pending_plan_commitment",
        "__native_capability",
    )

    def __init__(
        self,
        token: object,
        final_plan: Mapping[str, object],
        descriptor: AuthorityBootstrapDescriptor,
        observations: Mapping[str, object],
        *,
        recovery: bool,
    ) -> None:
        if token is not _BOOTSTRAP_TOKEN:
            raise TypeError(
                "VerifiedAuthorityBootstrapPlan cannot be constructed directly"
            )
        self.__final_plan = canonical_json_bytes(final_plan)
        self.__descriptor = canonical_json_bytes(descriptor.to_document())
        self.__observations = canonical_json_bytes(observations)
        self.__consumed = False
        self.__recovery = recovery
        self.__installation_id = descriptor.installation_id
        self.__setup_body_digest = bytes.fromhex(descriptor.setup_body_digest)
        self.__descriptor_digest = bytes.fromhex(descriptor.digest)
        self.__pending_plan_commitment = bytes.fromhex(final_plan["plan_digest"])
        self.__native_capability = secrets.token_bytes(32)

    @property
    def descriptor(self) -> AuthorityBootstrapDescriptor:
        return AuthorityBootstrapDescriptor.from_document(json.loads(self.__descriptor))

    @property
    def final_plan(self) -> dict[str, object]:
        return json.loads(self.__final_plan)

    @property
    def observations(self) -> dict[str, object]:
        return json.loads(self.__observations)

    @property
    def recovery(self) -> bool:
        return self.__recovery

    @property
    def installation_id(self) -> str:
        return self.__installation_id

    @property
    def setup_body_digest(self) -> str:
        return self.__setup_body_digest.hex()

    @property
    def descriptor_digest(self) -> str:
        return self.__descriptor_digest.hex()

    @property
    def pending_plan_commitment(self) -> str:
        return self.__pending_plan_commitment.hex()

    def _native_bootstrap_secret(self) -> bytes:
        if self.__consumed:
            raise AuthorityError("authority bootstrap plan already consumed")
        return bytes(self.__native_capability)

    def consume(self) -> None:
        if self.__consumed:
            raise AuthorityError("authority bootstrap plan already consumed")
        descriptor = self.descriptor
        final_plan = self.final_plan
        if (
            descriptor.installation_id != self.__installation_id
            or not hmac.compare_digest(
                bytes.fromhex(descriptor.setup_body_digest),
                self.__setup_body_digest,
            )
            or not hmac.compare_digest(
                bytes.fromhex(descriptor.digest), self.__descriptor_digest
            )
            or not hmac.compare_digest(
                bytes.fromhex(final_install_plan_digest(final_plan)),
                self.__pending_plan_commitment,
            )
        ):
            raise AuthorityError("authority bootstrap capability snapshot mismatch")
        self.__consumed = True

    def __reduce__(self):
        raise TypeError("VerifiedAuthorityBootstrapPlan is non-serializable")


def verify_authority_bootstrap(
    final_install_plan: object,
    bootstrap_descriptor: object,
    *,
    expected_installation_id: str,
    observations: Mapping[str, object],
    recovery: bool = False,
) -> VerifiedAuthorityBootstrapPlan:
    plan = require_document(final_install_plan, "install-plan")
    if plan.get("installation_id") != expected_installation_id:
        raise AuthorityError("installation mismatch")
    if not isinstance(bootstrap_descriptor, Mapping):
        raise AuthorityError("authority bootstrap descriptor must be an object")
    descriptor = AuthorityBootstrapDescriptor.from_document(
        bootstrap_descriptor
    )
    body = SetupBodyV1.from_final_plan(plan)
    if body.digest != plan.get("setup_body_digest"):
        raise AuthorityError("setup-body digest mismatch")
    if descriptor.setup_body_digest != body.digest:
        raise AuthorityError("descriptor setup-body link mismatch")
    if descriptor.installation_id != expected_installation_id:
        raise AuthorityError("descriptor installation mismatch")
    if descriptor.to_document() != plan.get("authority_bootstrap"):
        raise AuthorityError("final plan descriptor mismatch")
    if descriptor.digest != plan.get("authority_bootstrap_digest"):
        raise AuthorityError("authority bootstrap descriptor digest mismatch")
    if final_install_plan_digest(plan) != plan.get("plan_digest"):
        raise AuthorityError("final install-plan digest mismatch")
    if set(observations) != set(descriptor.locators):
        raise AuthorityError("fixed-locator observations are incomplete")
    for locator, observation in observations.items():
        if not isinstance(observation, Mapping):
            raise AuthorityError(f"invalid observation for {locator}")
        state = observation.get("state")
        if state not in ("absent", "present"):
            raise AuthorityError(f"invalid observation for {locator}")
        if state == "present" and not recovery:
            raise AuthorityError(f"foreign fixed-locator collision at {locator}")
    return VerifiedAuthorityBootstrapPlan(
        _BOOTSTRAP_TOKEN,
        plan,
        descriptor,
        observations,
        recovery=recovery,
    )


class _ProtectedInteraction:
    __slots__ = ("origin", "stdin_is_tty", "user_presence")

    def __init__(
        self,
        token: object,
        *,
        origin: str,
        stdin_is_tty: bool,
        user_presence: bool,
    ) -> None:
        if token is not _INTERACTION_TOKEN:
            raise TypeError("protected interaction cannot be forged")
        self.origin = origin
        self.stdin_is_tty = stdin_is_tty
        self.user_presence = user_presence


def protected_interaction_for_test(
    *, origin: str, stdin_is_tty: bool, user_presence: bool
) -> _ProtectedInteraction:
    return _ProtectedInteraction(
        _INTERACTION_TOKEN,
        origin=origin,
        stdin_is_tty=stdin_is_tty,
        user_presence=user_presence,
    )


def _require_protected_interaction(interaction: object) -> _ProtectedInteraction:
    if (
        not isinstance(interaction, _ProtectedInteraction)
        or interaction.origin != "local-cli"
        or not interaction.stdin_is_tty
        or not interaction.user_presence
    ):
        raise CapabilityFailure(
            "protected local interactive user presence is required"
        )
    return interaction


def _maybe_crash(fail_at: str | None, point: str) -> None:
    if fail_at == point:
        raise InjectedAuthorityCrash(point)


def _wal_digest(value: Mapping[str, object]) -> str:
    return _domain_digest(
        _BOOTSTRAP_WAL_DOMAIN,
        {
            key: item
            for key, item in value.items()
            if key not in ("wal_digest", "phase", "broker_signature")
        },
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_wal(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    try:
        encoded = canonical_json_bytes(value) + b"\n"
        offset = 0
        while offset < len(encoded):
            offset += os.write(descriptor, encoded[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _read_wal(
    path: Path, plan: VerifiedAuthorityBootstrapPlan
) -> dict[str, object]:
    try:
        document = json.loads(path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise AuthorityError("authority bootstrap WAL is missing or malformed") from error
    descriptor = plan.descriptor
    expected = {
        "installation_id": descriptor.installation_id,
        "creator_id": descriptor.creator_id,
        "bootstrap_digest": descriptor.digest,
        "pending_plan_commitment": plan.pending_plan_commitment,
        "wal_locator": descriptor.wal_locator,
        "broker_code_identity": descriptor.native_broker_code_identity,
    }
    if any(document.get(name) != value for name, value in expected.items()):
        raise AuthorityError("authority bootstrap WAL binding mismatch")
    if document.get("wal_digest") != _wal_digest(document):
        raise AuthorityError("authority bootstrap WAL digest mismatch")
    return document


def _markers(
    plan: VerifiedAuthorityBootstrapPlan, wal_digest: str
) -> dict[str, object]:
    descriptor = plan.descriptor
    return {
        "installation_id": descriptor.installation_id,
        "creator_id": descriptor.creator_id,
        "broker_code_identity": descriptor.native_broker_code_identity,
        "bootstrap_digest": descriptor.digest,
        "wal_digest": wal_digest,
    }


def _item_values(
    plan: VerifiedAuthorityBootstrapPlan, wal_digest: str, backend
) -> list[tuple[str, str, dict[str, object]]]:
    descriptor = plan.descriptor
    markers = _markers(plan, wal_digest)
    locators = descriptor.locator_map
    return [
        (
            "approval",
            locators["approval_key"],
            {
                **markers,
                "purpose": "approval-key",
                "attributes": descriptor.item_attributes["approval_key"],
                "public_key_digest": backend.approval_public_key_digest,
                "persistent_reference": "opaque:approval-key",
            },
        ),
        (
            "anchor",
            locators["anchor"],
            {
                **markers,
                "purpose": "anchor",
                "attributes": descriptor.item_attributes["anchor"],
                "namespace": descriptor.initial_anchor_namespace,
                "generation": descriptor.initial_anchor_generation,
                "commitment": descriptor.initial_anchor_commitment,
            },
        ),
        (
            "receipt_key",
            locators["receipt_key"],
            {
                **markers,
                "purpose": "broker-receipt-key",
                "attributes": descriptor.item_attributes["receipt_key"],
                "key_id": f"broker-receipt:{descriptor.installation_id}",
                "persistent_reference": "opaque:broker-receipt-key",
            },
        ),
        (
            "integrity_key",
            locators["integrity_key"],
            {
                **markers,
                "purpose": "integrity-key",
                "attributes": descriptor.item_attributes["integrity_key"],
                "key_id": f"native-integrity:{descriptor.installation_id}",
                "persistent_reference": "opaque:integrity-key",
            },
        ),
        (
            "bootstrap_record",
            locators["bootstrap_record"],
            {
                **markers,
                "purpose": "authority-bootstrap-record",
                "attributes": descriptor.item_attributes["bootstrap_record"],
                "launcher_code_identity": descriptor.launcher_code_identity,
                "launcher_content_digest": descriptor.launcher_content_digest,
                "native_broker_code_identity":
                    descriptor.native_broker_code_identity,
                "native_broker_content_digest":
                    descriptor.native_broker_content_digest,
                "locators": descriptor.to_document()["locators"],
            },
        ),
    ]


def _manifest(
    plan: VerifiedAuthorityBootstrapPlan, backend
) -> dict[str, object]:
    descriptor = plan.descriptor
    return {
        "schema": "agent-harness/authority-manifest",
        "schema_version": 1,
        "created_at": plan.final_plan["created_at"],
        "installation_id": descriptor.installation_id,
        "launcher_code_identity": descriptor.launcher_code_identity,
        "launcher_content_digest": descriptor.launcher_content_digest,
        "native_broker_code_identity":
            descriptor.native_broker_code_identity,
        "native_broker_content_digest":
            descriptor.native_broker_content_digest,
        "approval_public_key_digest": backend.approval_public_key_digest,
        "approval_persistent_reference": "opaque:approval-key",
        "anchor_backend_id": "native-keychain-anchor-v1",
        "anchor_namespace": descriptor.initial_anchor_namespace,
        "receipt_key_id": f"broker-receipt:{descriptor.installation_id}",
        "receipt_public_key_digest": backend.receipt_public_key_digest,
        "receipt_persistent_reference": "opaque:broker-receipt-key",
        "integrity_key_id": f"native-integrity:{descriptor.installation_id}",
        "integrity_key_locator": descriptor.locator_map["integrity_key"],
        "integrity_persistent_reference": "opaque:integrity-key",
        "terminal_pin_locator": descriptor.locator_map["terminal_pin"],
        "terminal_pin_attributes": descriptor.item_attributes["terminal_pin"],
        "capability_state": list(descriptor.capabilities),
        "bootstrap_digest": descriptor.digest,
        "pending_plan_commitment": plan.pending_plan_commitment,
    }


def _bootstrap_lock(path: str) -> threading.Lock:
    with _LOCK_GUARD:
        return _BOOTSTRAP_LOCKS.setdefault(path, threading.Lock())


def _native_bootstrap_request(
    plan: VerifiedAuthorityBootstrapPlan,
    wal: Mapping[str, object],
) -> dict[str, object]:
    descriptor = plan.descriptor
    return {
        "created_at": plan.final_plan["created_at"],
        "installation_id": descriptor.installation_id,
        "creator_id": descriptor.creator_id,
        "descriptor_digest": descriptor.digest,
        "final_plan_digest": plan.pending_plan_commitment,
        "final_plan": plan.final_plan,
        "launcher_code_identity": descriptor.launcher_code_identity,
        "launcher_content_digest": descriptor.launcher_content_digest,
        "wal_digest": wal["wal_digest"],
        "anchor_namespace": descriptor.initial_anchor_namespace,
        "initial_anchor_generation": descriptor.initial_anchor_generation,
        "initial_anchor_commitment": descriptor.initial_anchor_commitment,
    }


def _verified_native_manifest(
    plan: VerifiedAuthorityBootstrapPlan,
    backend: NativeAuthorityBackend,
    manifest: object,
) -> tuple[dict[str, object], str]:
    if not isinstance(manifest, Mapping):
        raise CapabilityFailure("native authority manifest must be an object")
    descriptor = plan.descriptor
    expected = {
        "schema": "agent-harness/authority-manifest",
        "schema_version": 1,
        "created_at": plan.final_plan["created_at"],
        "installation_id": descriptor.installation_id,
        "launcher_code_identity": descriptor.launcher_code_identity,
        "launcher_content_digest": descriptor.launcher_content_digest,
        "native_broker_code_identity":
            descriptor.native_broker_code_identity,
        "native_broker_content_digest":
            descriptor.native_broker_content_digest,
        "anchor_namespace": descriptor.initial_anchor_namespace,
        "integrity_key_locator": descriptor.locator_map["integrity_key"],
        "terminal_pin_locator": descriptor.locator_map["terminal_pin"],
        "terminal_pin_attributes": descriptor.item_attributes["terminal_pin"],
        "capability_state": list(descriptor.capabilities),
        "bootstrap_digest": descriptor.digest,
        "pending_plan_commitment": plan.pending_plan_commitment,
    }
    if any(manifest.get(name) != value for name, value in expected.items()):
        raise CapabilityFailure("native authority manifest binding mismatch")
    for field in (
        "approval_public_key_digest",
        "approval_persistent_reference",
        "anchor_backend_id",
        "receipt_key_id",
        "receipt_public_key_digest",
        "receipt_persistent_reference",
        "integrity_key_id",
        "integrity_persistent_reference",
    ):
        value = manifest.get(field)
        if not isinstance(value, str) or not value:
            raise CapabilityFailure(
                f"native authority manifest {field} is invalid"
            )
    for field in ("approval_public_key_digest", "receipt_public_key_digest"):
        digest = manifest[field]
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise CapabilityFailure(
                f"native authority manifest {field} is invalid"
            )
    signature = manifest.get("broker_signature")
    if not isinstance(signature, str) or not backend.verify_bootstrap_manifest(
        manifest
    ):
        raise CapabilityFailure("native authority manifest signature mismatch")
    backend._accept_verified_manifest(plan, manifest)
    return (
        {key: _json_copy(value) for key, value in manifest.items()},
        signature,
    )


def _provision_native_locked(
    plan: VerifiedAuthorityBootstrapPlan,
    backend: NativeAuthorityBackend,
    wal: dict[str, object],
    *,
    fail_at: str | None,
    allow_existing: bool,
) -> dict[str, object]:
    if wal.get("phase") == "COMPLETE" and not allow_existing:
        raise AuthorityError(
            "authority bootstrap capability has stale absence observations"
        )
    request = _native_bootstrap_request(plan, wal)
    _maybe_crash(fail_at, "before_broker_dispatch")
    if allow_existing or wal.get("phase") == "COMPLETE":
        response = backend.recover_bootstrap(request)
    else:
        response = backend.bootstrap(request)
    _maybe_crash(fail_at, "after_broker_dispatch")
    _maybe_crash(fail_at, "before_manifest_readback")
    manifest, signature = _verified_native_manifest(plan, backend, response)
    _maybe_crash(fail_at, "after_manifest_readback")

    if wal.get("phase") == "COMPLETE":
        stored_signature = wal.get("broker_signature")
        if (
            not isinstance(stored_signature, str)
            or not backend.verify_bootstrap_manifest(
                {**manifest, "broker_signature": stored_signature}
            )
        ):
            raise AuthorityError("completed authority WAL signature mismatch")
        return {**manifest, "broker_signature": stored_signature}

    _maybe_crash(fail_at, "before_wal_complete")
    wal["phase"] = "COMPLETE"
    wal["broker_signature"] = signature
    _write_wal(Path(plan.descriptor.wal_locator), wal)
    _maybe_crash(fail_at, "after_wal_complete")
    return manifest


def _provision_locked(
    plan: VerifiedAuthorityBootstrapPlan,
    backend,
    *,
    fail_at: str | None,
    allow_existing: bool,
) -> dict[str, object]:
    descriptor = plan.descriptor
    wal_path = Path(descriptor.wal_locator)
    if backend.code_identity != descriptor.native_broker_code_identity:
        raise CapabilityFailure("native broker code identity drift")

    if wal_path.exists():
        wal = _read_wal(wal_path, plan)
    else:
        _maybe_crash(fail_at, "before_wal_write")
        wal = {
            "schema": "agent-harness/authority-bootstrap-wal",
            "schema_version": 1,
            "created_at": plan.final_plan["created_at"],
            "installation_id": descriptor.installation_id,
            "creator_id": descriptor.creator_id,
            "bootstrap_digest": descriptor.digest,
            "pending_plan_commitment": plan.pending_plan_commitment,
            "wal_locator": descriptor.wal_locator,
            "broker_code_identity": descriptor.native_broker_code_identity,
            "locators": descriptor.to_document()["locators"],
            "item_attributes": descriptor.to_document()["item_attributes"],
            "conditional_inverses": descriptor.to_document()[
                "conditional_inverses"
            ],
            "phase": "PREPARED",
            "broker_signature": None,
        }
        wal["wal_digest"] = _wal_digest(wal)
        _write_wal(wal_path, wal)
        _maybe_crash(fail_at, "after_wal_fsync")

    if isinstance(backend, NativeAuthorityBackend):
        return _provision_native_locked(
            plan,
            backend,
            wal,
            fail_at=fail_at,
            allow_existing=allow_existing,
        )

    if wal.get("phase") == "COMPLETE":
        if not allow_existing:
            raise AuthorityError(
                "authority bootstrap capability has stale absence observations"
            )
        manifest = _manifest(plan, backend)
        signature = wal.get("broker_signature")
        if not isinstance(signature, str) or not backend.verify_receipt(
            canonical_json_bytes(manifest), signature
        ):
            raise AuthorityError("completed authority WAL signature mismatch")
        return {**manifest, "broker_signature": signature}

    _maybe_crash(fail_at, "before_broker_dispatch")
    items = _item_values(plan, wal["wal_digest"], backend)
    for label, locator, value in items:
        before = f"before_{label}_add"
        after = f"after_{label}_add"
        _maybe_crash(fail_at, before)
        existing = backend.read_item(locator)
        if existing is None:
            backend.add_item(locator, value)
            if label == "anchor":
                backend.anchors[descriptor.initial_anchor_namespace] = (
                    descriptor.initial_anchor_generation,
                    descriptor.initial_anchor_commitment,
                )
        elif not allow_existing or existing != value:
            raise AuthorityError(f"foreign fixed-locator collision at {locator}")
        _maybe_crash(fail_at, after)
    _maybe_crash(fail_at, "after_broker_dispatch")

    _maybe_crash(fail_at, "before_manifest_readback")
    for _, locator, expected in items:
        if backend.read_item(locator) != expected:
            raise CapabilityFailure("authority item readback mismatch")
    manifest = _manifest(plan, backend)
    _maybe_crash(fail_at, "after_manifest_readback")
    _maybe_crash(fail_at, "before_wal_complete")
    wal["phase"] = "COMPLETE"
    wal["broker_signature"] = backend.sign_receipt(
        canonical_json_bytes(manifest)
    )
    _write_wal(wal_path, wal)
    if hasattr(backend, "provision_calls"):
        backend.provision_calls += 1
    _maybe_crash(fail_at, "after_wal_complete")
    return {**manifest, "broker_signature": wal["broker_signature"]}


def bootstrap_authority(
    plan: VerifiedAuthorityBootstrapPlan,
    backend,
    *,
    interaction: object,
    fail_at: str | None = None,
) -> dict[str, object]:
    if not isinstance(plan, VerifiedAuthorityBootstrapPlan):
        raise TypeError("VerifiedAuthorityBootstrapPlan required")
    _require_protected_interaction(interaction)
    if fail_at is not None and fail_at not in AUTHORITY_BOOTSTRAP_CRASH_POINTS:
        raise ValueError("unknown authority crash point")
    plan.consume()
    lock = _bootstrap_lock(plan.descriptor.wal_locator)
    with lock:
        return _provision_locked(
            plan,
            backend,
            fail_at=fail_at,
            allow_existing=plan.recovery,
        )


def recover_authority_bootstrap(
    plan: VerifiedAuthorityBootstrapPlan,
    backend,
    *,
    interaction: object,
    wal_path: Path | str | None = None,
) -> dict[str, object]:
    if not isinstance(plan, VerifiedAuthorityBootstrapPlan):
        raise TypeError("VerifiedAuthorityBootstrapPlan required")
    _require_protected_interaction(interaction)
    requested = Path(wal_path or plan.descriptor.wal_locator)
    if str(requested) != plan.descriptor.wal_locator:
        raise AuthorityError("authority bootstrap WAL locator mismatch")
    plan.consume()
    lock = _bootstrap_lock(plan.descriptor.wal_locator)
    with lock:
        return _provision_locked(
            plan,
            backend,
            fail_at=None,
            allow_existing=True,
        )


class VerifiedAnchorTransition:
    __slots__ = ("__document", "__consumed")

    def __init__(self, token: object, document: Mapping[str, object]) -> None:
        if token is not _TRANSITION_TOKEN:
            raise TypeError("VerifiedAnchorTransition cannot be constructed directly")
        self.__document = _json_copy(document)
        self.__consumed = False

    @property
    def document(self) -> dict[str, object]:
        if self.__consumed:
            raise AuthorityError("anchor transition already consumed")
        return copy.deepcopy(self.__document)

    def consume(self) -> dict[str, object]:
        if self.__consumed:
            raise AuthorityError("anchor transition already consumed")
        document = self.document
        self.__consumed = True
        return document

    def __reduce__(self):
        raise TypeError("VerifiedAnchorTransition is non-serializable")


def _anchor_lock(backend, namespace: str) -> threading.Lock:
    key = (id(backend), namespace)
    with _LOCK_GUARD:
        return _ANCHOR_LOCKS.setdefault(key, threading.Lock())


class LiveAnchorBroker:
    __slots__ = (
        "__backend",
        "__namespace",
        "__installation_id",
        "__caller_code_identity",
        "__broker_code_identity",
        "__lock",
        "qualifying",
    )

    def __init__(
        self,
        token: object,
        backend,
        *,
        namespace: str,
        installation_id: str,
        caller_code_identity: str,
        broker_code_identity: str,
    ) -> None:
        if token not in (_AUTHORITY_TOKEN, _TEST_AUTHORITY_TOKEN):
            raise TypeError("LiveAnchorBroker requires an attested native backend")
        self.__backend = backend
        self.__namespace = namespace
        self.__installation_id = installation_id
        self.__caller_code_identity = caller_code_identity
        self.__broker_code_identity = broker_code_identity
        self.__lock = _anchor_lock(backend, namespace)
        self.qualifying = token is _AUTHORITY_TOKEN

    def current_state(self) -> tuple[int, str]:
        if isinstance(self.__backend, NativeAuthorityBackend):
            return self.__backend.anchor_read(self.__namespace)
        try:
            return self.__backend.anchors[self.__namespace]
        except KeyError as error:
            raise CapabilityFailure("live anchor namespace unavailable") from error

    def compare_and_advance(
        self, transition: VerifiedAnchorTransition
    ) -> dict[str, object]:
        if not isinstance(transition, VerifiedAnchorTransition):
            raise TypeError("VerifiedAnchorTransition required")
        with self.__lock:
            document = transition.document
            expected = {
                "namespace": self.__namespace,
                "installation_id": self.__installation_id,
                "caller_code_identity": self.__caller_code_identity,
                "broker_code_identity": self.__broker_code_identity,
            }
            if any(document.get(name) != value for name, value in expected.items()):
                raise AuthorityError("anchor transition broker binding mismatch")
            if document["expires_at"] <= int(time.time()):
                raise AuthorityError("anchor transition expired")
            current = self.current_state()
            if current != (
                document["old_generation"],
                document["old_commitment"],
            ):
                raise AuthorityError("stale anchor generation or commitment")
            if document["new_generation"] != document["old_generation"] + 1:
                raise AuthorityError("anchor transition generation is not monotonic")
            new_state = (
                document["new_generation"],
                document["new_commitment"],
            )
            if isinstance(self.__backend, NativeAuthorityBackend):
                receipt = self.__backend.compare_and_advance(transition)
                if self.current_state() != new_state:
                    raise CapabilityFailure("anchor durable readback failed")
                if not self.verify_receipt(receipt):
                    raise CapabilityFailure(
                        "native anchor receipt verification failed"
                    )
                return receipt
            transition.consume()
            self.__backend.anchors[self.__namespace] = new_state
            if self.current_state() != new_state:
                raise CapabilityFailure("anchor durable readback failed")
            receipt = new_document(
                "state-anchor-receipt",
                self.__installation_id,
                created_at=time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
                anchor_namespace=self.__namespace,
                anchor_backend_id="native-keychain-anchor-v1",
                receipt_key_id=f"broker-receipt:{self.__installation_id}",
                transition_domain=document["domain"],
                transition_digest=_domain_digest(
                    b"agent-harness/verified-anchor-transition/v1\0",
                    {
                        key: item
                        for key, item in document.items()
                        if key != "authorization_mac"
                    },
                ),
                old_generation=document["old_generation"],
                old_commitment=document["old_commitment"],
                new_generation=document["new_generation"],
                new_commitment=document["new_commitment"],
                operation_id=document["nonce"],
            )
            receipt["broker_receipt"] = self.__backend.sign_receipt(
                canonical_json_bytes(receipt)
            )
            return receipt

    def _transition_context(self) -> dict[str, object]:
        generation, commitment = self.current_state()
        return {
            "namespace": self.__namespace,
            "installation_id": self.__installation_id,
            "caller_code_identity": self.__caller_code_identity,
            "broker_code_identity": self.__broker_code_identity,
            "generation": generation,
            "commitment": commitment,
        }

    def verify_receipt(self, receipt: object) -> bool:
        if not isinstance(receipt, Mapping):
            return False
        if isinstance(self.__backend, NativeAuthorityBackend):
            return (
                receipt.get("installation_id") == self.__installation_id
                and receipt.get("anchor_namespace") == self.__namespace
                and self.__backend.verify_receipt(receipt)
            )
        signature = receipt.get("broker_receipt")
        if not isinstance(signature, str):
            return False
        unsigned = {
            key: item for key, item in receipt.items() if key != "broker_receipt"
        }
        return (
            unsigned.get("installation_id") == self.__installation_id
            and unsigned.get("anchor_namespace") == self.__namespace
            and self.__backend.verify_receipt(
                canonical_json_bytes(unsigned), signature
            )
        )


def open_live_anchor_broker(
    backend: NativeAuthorityBackend,
    *,
    namespace: str,
    installation_id: str,
    caller_code_identity: str,
    broker_code_identity: str,
) -> LiveAnchorBroker:
    if not isinstance(backend, NativeAuthorityBackend) or not backend.qualifying:
        raise TypeError("qualifying NativeAuthorityBackend required")
    health = backend.health()
    if health.get("code_identity") != broker_code_identity:
        raise CapabilityFailure("native anchor broker identity mismatch")
    return LiveAnchorBroker(
        _AUTHORITY_TOKEN,
        backend,
        namespace=namespace,
        installation_id=installation_id,
        caller_code_identity=caller_code_identity,
        broker_code_identity=broker_code_identity,
    )


def issue_installation_anchor_transition(
    phase: VerifiedInstallationState,
    broker: LiveAnchorBroker,
    *,
    authority: IntegrityAuthority,
    now: int | None = None,
) -> VerifiedAnchorTransition:
    if not isinstance(phase, VerifiedInstallationState):
        raise TypeError("VerifiedInstallationState required")
    if not isinstance(broker, LiveAnchorBroker):
        raise TypeError("LiveAnchorBroker required")
    context = broker._transition_context()
    phase_document = phase.document
    binding = phase_document.get("anchor_transition")
    required = {
        "old_commitment",
        "new_commitment",
        "wal_digest",
        "event_digest",
        "check_digest",
        "record_digest",
        "authorization_epoch",
    }
    if not isinstance(binding, Mapping) or set(binding) != required:
        raise AuthorityError(
            "verified installation state transition binding is incomplete"
        )
    for name in (
        "old_commitment",
        "new_commitment",
        "wal_digest",
        "event_digest",
        "check_digest",
        "record_digest",
    ):
        value = binding[name]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise AuthorityError(
                f"verified installation state {name} is invalid"
            )
    if binding["old_commitment"] != context["commitment"]:
        raise AuthorityError("verified installation state old anchor mismatch")
    phase.require_binding(
        expected_installation_id=context["installation_id"],
        expected_generation=context["generation"] + 1,
        expected_anchor_commitment=binding["new_commitment"],
    )
    authorization_epoch = binding["authorization_epoch"]
    if (
        isinstance(authorization_epoch, bool)
        or not isinstance(authorization_epoch, int)
        or authorization_epoch < 0
    ):
        raise AuthorityError(
            "verified installation state authorization_epoch is invalid"
        )
    task_id = phase_document.get("publication_transaction")
    plan_digests = {
        receipt.document.get("plan_digest")
        for receipt in phase.receipts.values()
    }
    plan_digest = next(iter(plan_digests)) if len(plan_digests) == 1 else None
    if not isinstance(task_id, str) or not task_id:
        raise AuthorityError(
            "verified installation state task identity is missing"
        )
    if not isinstance(plan_digest, str) or len(plan_digest) != 64:
        raise AuthorityError(
            "verified installation state plan digest is invalid"
        )
    current_time = int(time.time()) if now is None else now
    if not isinstance(authority, IntegrityAuthority):
        raise TypeError("IntegrityAuthority required")
    document = {
        "domain": "installation-transaction",
        "namespace": context["namespace"],
        "installation_id": context["installation_id"],
        "subject_kind": "task",
        "subject_id": task_id,
        "operation_kind": "publish-installation",
        "old_generation": context["generation"],
        "old_commitment": context["commitment"],
        "new_generation": context["generation"] + 1,
        "new_commitment": binding["new_commitment"],
        "plan_digest": plan_digest,
        "wal_digest": binding["wal_digest"],
        "event_digest": binding["event_digest"],
        "check_digest": binding["check_digest"],
        "record_digest": binding["record_digest"],
        "authorization_epoch": authorization_epoch,
        "caller_code_identity": context["caller_code_identity"],
        "broker_code_identity": context["broker_code_identity"],
        "nonce": secrets.token_hex(16),
        "expires_at": current_time + 300,
    }
    document["authorization_mac"] = (
        authority.authenticate_installation_anchor_transition(phase, document)
    )
    return VerifiedAnchorTransition(_TRANSITION_TOKEN, document)


def create_test_live_anchor_broker(
    backend,
    *,
    namespace: str,
    installation_id: str,
    caller_code_identity: str,
    broker_code_identity: str,
    initial_generation: int,
    initial_commitment: str,
) -> LiveAnchorBroker:
    backend.anchors[namespace] = (initial_generation, initial_commitment)
    return LiveAnchorBroker(
        _TEST_AUTHORITY_TOKEN,
        backend,
        namespace=namespace,
        installation_id=installation_id,
        caller_code_identity=caller_code_identity,
        broker_code_identity=broker_code_identity,
    )


class ApprovalAuthority:
    __slots__ = (
        "__backend",
        "__expected_public_key_digest",
        "__broker_code_identity",
        "__clock",
        "qualifying",
    )

    def __init__(
        self,
        token: object,
        backend,
        *,
        expected_public_key_digest: str,
        broker_code_identity: str,
        clock: Callable[[], float],
    ) -> None:
        if token not in (_AUTHORITY_TOKEN, _TEST_AUTHORITY_TOKEN):
            raise TypeError("ApprovalAuthority requires a protected backend")
        self.__backend = backend
        self.__expected_public_key_digest = expected_public_key_digest
        self.__broker_code_identity = broker_code_identity
        self.__clock = clock
        self.qualifying = token is _AUTHORITY_TOKEN

    def health(self) -> dict[str, object]:
        if self.__backend.code_identity != self.__broker_code_identity:
            raise CapabilityFailure("approval broker code identity drift")
        if (
            self.__backend.approval_public_key_digest
            != self.__expected_public_key_digest
        ):
            raise CapabilityFailure("approval key replacement detected")
        if not self.__backend.user_presence_available:
            raise CapabilityFailure("protected user presence unavailable")
        return {
            "healthy": True,
            "public_key_digest": self.__expected_public_key_digest,
            "qualifying": self.qualifying,
        }

    def approve_external_write(
        self,
        envelope: Mapping[str, object],
        display_summary: str,
        *,
        interaction: object,
    ) -> dict[str, object]:
        self.health()
        protected = _require_protected_interaction(interaction)
        if not protected.user_presence:
            raise CapabilityFailure("protected user presence required")
        if not isinstance(envelope, Mapping) or not isinstance(
            display_summary, str
        ):
            raise AuthorityError("approval envelope and summary are required")
        if (
            envelope.get("schema")
            != "agent-harness/external-write-envelope"
            or envelope.get("schema_version") != 1
        ):
            raise AuthorityError("version-one external-write envelope required")
        required = {
            "installation_id",
            "intent_digest",
            "predecessor_task_event_hash",
            "expires_at",
        }
        if not required <= set(envelope):
            raise AuthorityError("external-write envelope is incomplete")
        try:
            uuid.UUID(envelope["installation_id"])
            require_rfc3339_utc(envelope["expires_at"])
        except (AttributeError, TypeError, ValueError) as error:
            raise AuthorityError("external-write envelope identity is invalid") from error
        for field_name in ("intent_digest", "predecessor_task_event_hash"):
            value = envelope[field_name]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise AuthorityError(
                    f"external-write envelope {field_name} is invalid"
                )
        if not display_summary.strip():
            raise AuthorityError("canonical approval display summary is empty")
        expires_at = datetime.fromisoformat(
            envelope["expires_at"].removesuffix("Z") + "+00:00"
        ).timestamp()
        lifetime = expires_at - float(self.__clock())
        if lifetime <= 0:
            raise AuthorityError("external-write envelope expired")
        if lifetime > 900:
            raise AuthorityError(
                "external-write envelope has excessive horizon"
            )
        signature = self.__backend.approve(
            canonical_json_bytes(envelope),
            display_summary.encode(),
            protected_user_presence=True,
        )
        if not isinstance(signature, Mapping):
            raise CapabilityFailure("approval broker returned malformed signature")
        return _json_copy(signature)

    def verify_public_key(
        self,
        envelope: Mapping[str, object],
        display_summary: str,
        signature: object,
    ) -> bool:
        self.health()
        if not isinstance(envelope, Mapping) or not isinstance(display_summary, str):
            return False
        return bool(
            self.__backend.verify_approval(
                canonical_json_bytes(envelope),
                display_summary.encode(),
                signature,
            )
        )


_AUTHORITY_TOKEN = object()


def open_approval_authority(
    backend: NativeAuthorityBackend,
    *,
    expected_public_key_digest: str,
    broker_code_identity: str,
) -> ApprovalAuthority:
    if not isinstance(backend, NativeAuthorityBackend) or not backend.qualifying:
        raise TypeError("qualifying NativeAuthorityBackend required")
    return ApprovalAuthority(
        _AUTHORITY_TOKEN,
        backend,
        expected_public_key_digest=expected_public_key_digest,
        broker_code_identity=broker_code_identity,
        clock=time.time,
    )


def create_test_approval_authority(
    backend,
    *,
    expected_public_key_digest: str,
    broker_code_identity: str,
    current_time: int | None = None,
) -> ApprovalAuthority:
    return ApprovalAuthority(
        _TEST_AUTHORITY_TOKEN,
        backend,
        expected_public_key_digest=expected_public_key_digest,
        broker_code_identity=broker_code_identity,
        clock=time.time if current_time is None else lambda: current_time,
    )


def issue_authority_retirement(
    finalization: VerifiedFinalizationPlan,
    anchor: LiveAnchorBroker,
    anchor_receipt: VerifiedStateAnchorReceipt,
    approval: Mapping[str, object],
    terminal_attestation: Mapping[str, object],
    attestation_readback: Mapping[str, object],
    *,
    approval_authority: ApprovalAuthority,
    backend: NativeAuthorityBackend,
    now: int | None = None,
) -> VerifiedAuthorityRetirementPlan:
    if not isinstance(finalization, VerifiedFinalizationPlan):
        raise TypeError("VerifiedFinalizationPlan required")
    if not isinstance(anchor, LiveAnchorBroker):
        raise TypeError("LiveAnchorBroker required")
    if not isinstance(anchor_receipt, VerifiedStateAnchorReceipt):
        raise TypeError("VerifiedStateAnchorReceipt required")
    if not isinstance(approval_authority, ApprovalAuthority):
        raise TypeError("ApprovalAuthority required")
    if not isinstance(backend, NativeAuthorityBackend):
        raise TypeError("NativeAuthorityBackend required")
    if not all(
        isinstance(value, Mapping)
        for value in (approval, terminal_attestation, attestation_readback)
    ):
        raise TypeError("structured retirement evidence is required")

    plan = finalization.document
    context = anchor._transition_context()
    installation_id = finalization.installation_id
    generation = finalization.generation
    commitment = finalization.anchor_commitment
    if (
        plan.get("lifecycle_phase") != "UNINSTALLED_PUBLISHED"
        or plan.get("predecessor_generation") != generation
        or context["installation_id"] != installation_id
        or context["generation"] != generation
        or context["commitment"] != commitment
        or context["broker_code_identity"] != backend.code_identity
    ):
        raise AuthorityError(
            "retirement finalization/live-anchor binding mismatch"
        )
    anchor_receipt.require_binding(
        expected_installation_id=installation_id,
        expected_generation=generation,
        expected_anchor_commitment=commitment,
    )
    receipt = anchor_receipt.document
    if (
        receipt.get("anchor_namespace") != context["namespace"]
        or receipt.get("new_generation") != generation
        or receipt.get("new_commitment") != commitment
    ):
        raise AuthorityError("retirement anchor receipt mismatch")
    anchor_receipt_digest = hashlib.sha256(
        canonical_json_bytes(receipt)
    ).hexdigest()

    attestation_fields = {
        "installation_id",
        "authority_era",
        "receipt_public_key_digest",
        "helper_object_identity",
        "helper_finalizer_digest",
        "broker_code_identity",
        "anchor_namespace",
        "anchor_generation",
        "anchor_commitment",
        "terminal_pin_locator",
        "attestation_digest",
        "broker_signature",
    }
    attestation = _json_copy(terminal_attestation)
    if (
        set(attestation) != attestation_fields
        or canonical_json_bytes(attestation)
        != canonical_json_bytes(attestation_readback)
    ):
        raise AuthorityError(
            "terminal retirement attestation readback mismatch"
        )
    attestation_core = {
        key: value
        for key, value in attestation.items()
        if key not in ("attestation_digest", "broker_signature")
    }
    attestation_digest = _domain_digest(
        b"agent-harness/terminal-retirement-attestation/v1\0",
        attestation_core,
    )
    if (
        attestation.get("attestation_digest") != attestation_digest
        or attestation.get("installation_id") != installation_id
        or attestation.get("broker_code_identity") != backend.code_identity
        or attestation.get("anchor_namespace") != context["namespace"]
        or attestation.get("anchor_generation") != generation
        or attestation.get("anchor_commitment") != commitment
        or attestation.get("terminal_pin_locator")
        != TERMINAL_PIN_LOCATOR
    ):
        raise AuthorityError(
            "terminal retirement attestation binding mismatch"
        )
    for field in (
        "attestation_digest",
        "receipt_public_key_digest",
        "helper_finalizer_digest",
    ):
        value = attestation.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise AuthorityError(f"retirement {field} is invalid")
    for field in (
        "authority_era",
        "helper_object_identity",
        "broker_signature",
    ):
        value = attestation.get(field)
        if not isinstance(value, str) or not value:
            raise AuthorityError(f"retirement {field} is invalid")

    pin = {
        "installation_id": installation_id,
        "authority_era": attestation["authority_era"],
        "attestation_digest": attestation_digest,
        "receipt_public_key_digest":
            attestation["receipt_public_key_digest"],
        "helper_object_identity": attestation["helper_object_identity"],
        "helper_finalizer_digest":
            attestation["helper_finalizer_digest"],
    }
    signed_pin = {
        **pin,
        "broker_signature": attestation["broker_signature"],
    }
    if not backend.verify_bootstrap_manifest(signed_pin):
        raise CapabilityFailure(
            "terminal retirement broker signature verification failed"
        )

    finalizers = plan.get("finalizers")
    expected_finalizer = {
        "kind": "authority-retirement",
        "attestation_digest": attestation_digest,
        "receipt_public_key_digest": pin["receipt_public_key_digest"],
        "helper_object_identity": pin["helper_object_identity"],
        "helper_finalizer_digest": pin["helper_finalizer_digest"],
        "authority_era": pin["authority_era"],
        "terminal_pin_locator": TERMINAL_PIN_LOCATOR,
        "broker_code_identity": backend.code_identity,
        "anchor_namespace": context["namespace"],
        "anchor_generation": generation,
        "anchor_commitment": commitment,
        "anchor_receipt_digest": anchor_receipt_digest,
    }
    if (
        not isinstance(finalizers, list)
        or finalizers != [expected_finalizer]
        or plan.get("owned_object_identities")
        != [pin["helper_object_identity"]]
        or plan.get("containment_proof_digests")
        != [pin["helper_finalizer_digest"]]
    ):
        raise AuthorityError("retirement finalizer binding mismatch")

    plan_digest = plan.get("plan_digest")
    summary_document = {
        **pin,
        "finalization_plan_digest": plan_digest,
        "anchor_receipt_digest": anchor_receipt_digest,
        "terminal_pin_locator": TERMINAL_PIN_LOCATOR,
    }
    summary = canonical_json_bytes(summary_document).decode()
    if set(approval) != {"envelope", "summary", "signature"}:
        raise AuthorityError("structured retirement approval is malformed")
    envelope = approval["envelope"]
    if not isinstance(envelope, Mapping) or approval["summary"] != summary:
        raise AuthorityError("retirement approval summary mismatch")
    expected_envelope_fields = {
        "schema",
        "schema_version",
        "installation_id",
        "intent_digest",
        "predecessor_task_event_hash",
        "expires_at",
    }
    if (
        set(envelope) != expected_envelope_fields
        or envelope.get("schema")
        != "agent-harness/external-write-envelope"
        or envelope.get("schema_version") != 1
        or envelope.get("installation_id") != installation_id
        or envelope.get("intent_digest")
        != hashlib.sha256(summary.encode()).hexdigest()
        or envelope.get("predecessor_task_event_hash")
        != anchor_receipt_digest
    ):
        raise AuthorityError("retirement approval envelope mismatch")
    try:
        expires_at = datetime.fromisoformat(
            envelope["expires_at"].removesuffix("Z") + "+00:00"
        ).timestamp()
    except (AttributeError, TypeError, ValueError) as error:
        raise AuthorityError("retirement approval expiry is invalid") from error
    lifetime = expires_at - float(time.time() if now is None else now)
    if lifetime <= 0 or lifetime > 900:
        raise AuthorityError("retirement approval expiry is invalid")
    if not approval_authority.verify_public_key(
        envelope,
        summary,
        approval["signature"],
    ):
        raise CapabilityFailure("retirement native approval verification failed")

    anchor_receipt.consume(
        expected_installation_id=installation_id,
        expected_generation=generation,
        expected_anchor_commitment=commitment,
    )
    finalization.consume(
        expected_installation_id=installation_id,
        expected_generation=generation,
        expected_root=finalization.root,
        expected_anchor_commitment=commitment,
    )
    return VerifiedAuthorityRetirementPlan(
        _RETIREMENT_TOKEN,
        signed_pin,
    )
