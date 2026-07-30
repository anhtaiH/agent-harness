from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path
import threading
import time
from typing import Mapping
import uuid

from .auth import IntegrityAuthority
from .contracts import (
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
_FINAL_PLAN_DOMAIN = b"agent-harness/final-install-plan/v1\0"
_BOOTSTRAP_WAL_DOMAIN = b"agent-harness/authority-bootstrap-wal/v1\0"
_BOOTSTRAP_TOKEN = object()
_TRANSITION_TOKEN = object()
_INTERACTION_TOKEN = object()
_LOCK_GUARD = threading.Lock()
_BOOTSTRAP_LOCKS: dict[str, threading.Lock] = {}
_ANCHOR_LOCKS: dict[tuple[int, str], threading.Lock] = {}


class AuthorityError(ValueError):
    pass


class CapabilityFailure(AuthorityError):
    pass


class InjectedAuthorityCrash(RuntimeError):
    pass


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
        "algorithm_version",
        "policy_version",
        "ordered_manifest_digest",
        "source_commit",
        "frozen_snapshot_digest",
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
    broker_code_identity: str
    broker_content_digest: str
    wal_locator: str
    initial_anchor_namespace: str
    initial_anchor_generation: int
    initial_anchor_commitment: str
    broker_locator: str = "runtime/bin/ah-authority"
    approval_key_locator: str = APPROVAL_KEY_LOCATOR
    anchor_item_locator: str = ANCHOR_ITEM_LOCATOR
    receipt_key_locator: str = RECEIPT_KEY_LOCATOR
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
    broker_code_identity: str
    broker_content_digest: str
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
            "broker_code_identity": self.broker_code_identity,
            "broker_content_digest": self.broker_content_digest,
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
            "broker_code_identity",
            "broker_content_digest",
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
            broker_code_identity=value["broker_code_identity"],
            broker_content_digest=value["broker_content_digest"],
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
        broker_code_identity=requirements.broker_code_identity,
        broker_content_digest=requirements.broker_content_digest,
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
    return _domain_digest(_FINAL_PLAN_DOMAIN, unsigned)


class VerifiedAuthorityBootstrapPlan:
    __slots__ = (
        "__final_plan",
        "__descriptor",
        "__observations",
        "__consumed",
        "__recovery",
        "installation_id",
        "setup_body_digest",
        "descriptor_digest",
        "pending_plan_commitment",
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
        self.__final_plan = _json_copy(final_plan)
        self.__descriptor = descriptor
        self.__observations = _json_copy(observations)
        self.__consumed = False
        self.__recovery = recovery
        self.installation_id = descriptor.installation_id
        self.setup_body_digest = descriptor.setup_body_digest
        self.descriptor_digest = descriptor.digest
        self.pending_plan_commitment = final_plan["plan_digest"]

    @property
    def descriptor(self) -> AuthorityBootstrapDescriptor:
        return self.__descriptor

    @property
    def final_plan(self) -> dict[str, object]:
        return copy.deepcopy(self.__final_plan)

    @property
    def observations(self) -> dict[str, object]:
        return copy.deepcopy(self.__observations)

    @property
    def recovery(self) -> bool:
        return self.__recovery

    def consume(self) -> None:
        if self.__consumed:
            raise AuthorityError("authority bootstrap plan already consumed")
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
        "broker_code_identity": descriptor.broker_code_identity,
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
        "broker_code_identity": descriptor.broker_code_identity,
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
            "bootstrap_record",
            locators["bootstrap_record"],
            {
                **markers,
                "purpose": "authority-bootstrap-record",
                "attributes": descriptor.item_attributes["bootstrap_record"],
                "broker_content_digest": descriptor.broker_content_digest,
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
        "broker_code_identity": descriptor.broker_code_identity,
        "broker_content_digest": descriptor.broker_content_digest,
        "approval_public_key_digest": backend.approval_public_key_digest,
        "anchor_backend_id": "native-keychain-anchor-v1",
        "anchor_namespace": descriptor.initial_anchor_namespace,
        "receipt_key_id": f"broker-receipt:{descriptor.installation_id}",
        "terminal_pin_locator": descriptor.locator_map["terminal_pin"],
        "terminal_pin_attributes": descriptor.item_attributes["terminal_pin"],
        "capability_state": list(descriptor.capabilities),
        "bootstrap_digest": descriptor.digest,
        "pending_plan_commitment": plan.pending_plan_commitment,
    }


def _bootstrap_lock(path: str) -> threading.Lock:
    with _LOCK_GUARD:
        return _BOOTSTRAP_LOCKS.setdefault(path, threading.Lock())


def _provision_locked(
    plan: VerifiedAuthorityBootstrapPlan,
    backend,
    *,
    fail_at: str | None,
    allow_existing: bool,
) -> dict[str, object]:
    descriptor = plan.descriptor
    wal_path = Path(descriptor.wal_locator)
    if backend.code_identity != descriptor.broker_code_identity:
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
            "broker_code_identity": descriptor.broker_code_identity,
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
        return manifest

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
    return manifest


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
        return copy.deepcopy(self.__document)

    def consume(self) -> dict[str, object]:
        if self.__consumed:
            raise AuthorityError("anchor transition already consumed")
        self.__consumed = True
        return self.document

    def __reduce__(self):
        raise TypeError("VerifiedAnchorTransition is non-serializable")


def verify_anchor_transition_request(
    request: object,
    expected: Mapping[str, object],
    *,
    authority: IntegrityAuthority,
    now: int | None = None,
) -> VerifiedAnchorTransition:
    if not isinstance(request, Mapping):
        raise AuthorityError("anchor transition request must be an object")
    if not isinstance(expected, Mapping):
        raise AuthorityError("expected transition binding must be an object")
    document = _json_copy(request)
    for name, wanted in expected.items():
        if document.get(name) != wanted:
            raise AuthorityError(f"anchor transition {name} binding mismatch")
    if set(document) != set(expected) | {"authorization_mac"}:
        raise AuthorityError("anchor transition fields mismatch")
    old_generation = document.get("old_generation")
    new_generation = document.get("new_generation")
    if (
        isinstance(old_generation, bool)
        or not isinstance(old_generation, int)
        or isinstance(new_generation, bool)
        or not isinstance(new_generation, int)
        or new_generation != old_generation + 1
    ):
        raise AuthorityError("anchor transition must advance exactly one generation")
    current_time = int(time.time()) if now is None else now
    expires_at = document.get("expires_at")
    if (
        isinstance(expires_at, bool)
        or not isinstance(expires_at, int)
        or expires_at <= current_time
    ):
        raise AuthorityError("anchor transition expired")
    given = document.get("authorization_mac")
    if not isinstance(given, str) or len(given) != 64:
        raise AuthorityError("anchor transition authorization malformed")
    calculated = authority._mac_anchor_transition_request(document)
    if not hmac.compare_digest(given, calculated):
        raise AuthorityError("anchor transition authorization failed")
    return VerifiedAnchorTransition(_TRANSITION_TOKEN, document)


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
        backend,
        *,
        namespace: str,
        installation_id: str,
        caller_code_identity: str,
        broker_code_identity: str,
    ) -> None:
        self.__backend = backend
        self.__namespace = namespace
        self.__installation_id = installation_id
        self.__caller_code_identity = caller_code_identity
        self.__broker_code_identity = broker_code_identity
        self.__lock = _anchor_lock(backend, namespace)
        self.qualifying = bool(getattr(backend, "qualifying", False))

    def current_state(self) -> tuple[int, str]:
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
            document = transition.consume()
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
            self.__backend.anchors[self.__namespace] = new_state
            if self.current_state() != new_state:
                raise CapabilityFailure("anchor durable readback failed")
            receipt = {
                "installation_id": self.__installation_id,
                "anchor_namespace": self.__namespace,
                "anchor_backend_id": "native-keychain-anchor-v1",
                "receipt_key_id": f"broker-receipt:{self.__installation_id}",
                "transition_domain": document["domain"],
                "transition_digest": _domain_digest(
                    b"agent-harness/verified-anchor-transition/v1\0",
                    {
                        key: item
                        for key, item in document.items()
                        if key != "authorization_mac"
                    },
                ),
                "old_generation": document["old_generation"],
                "old_commitment": document["old_commitment"],
                "new_generation": document["new_generation"],
                "new_commitment": document["new_commitment"],
                "operation_id": document["nonce"],
            }
            receipt["broker_receipt"] = self.__backend.sign_receipt(
                canonical_json_bytes(receipt)
            )
            return receipt

    def verify_receipt(self, receipt: object) -> bool:
        if not isinstance(receipt, Mapping):
            return False
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
        "__issued",
        "qualifying",
    )

    def __init__(
        self,
        token: object,
        backend,
        *,
        expected_public_key_digest: str,
        broker_code_identity: str,
    ) -> None:
        if token is not _AUTHORITY_TOKEN:
            raise TypeError("ApprovalAuthority requires a protected backend")
        self.__backend = backend
        self.__expected_public_key_digest = expected_public_key_digest
        self.__broker_code_identity = broker_code_identity
        self.__issued: set[str] = set()
        self.qualifying = bool(getattr(backend, "qualifying", False))

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
    ) -> str:
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
        signature = self.__backend.approve(
            canonical_json_bytes(envelope),
            display_summary.encode(),
            protected_user_presence=True,
        )
        self.__issued.add(signature)
        return signature

    def verify_public_key(self, signature: str) -> bool:
        self.health()
        return signature in self.__issued


_AUTHORITY_TOKEN = object()


def create_test_approval_authority(
    backend,
    *,
    expected_public_key_digest: str,
    broker_code_identity: str,
) -> ApprovalAuthority:
    return ApprovalAuthority(
        _AUTHORITY_TOKEN,
        backend,
        expected_public_key_digest=expected_public_key_digest,
        broker_code_identity=broker_code_identity,
    )
