from __future__ import annotations

import copy
import hashlib
import hmac
import json
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping
import uuid

from .contracts import (
    FINAL_INSTALL_PLAN_DOMAIN,
    canonical_json_bytes,
    require_document,
)


class IntegrityError(ValueError):
    pass


_VERIFIED_TOKEN = object()
_AUTHORITY_TOKEN = object()
_MAC_DOMAINS = {
    "adapter_receipt": b"agent-harness/mac/adapter-receipt/v1\0",
    "installation_index": b"agent-harness/mac/installation-index/v1\0",
    "installation_publication_wal": (
        b"agent-harness/mac/installation-publication-wal/v1\0"
    ),
    "authority_bootstrap_wal": (
        b"agent-harness/mac/authority-bootstrap-wal/v1\0"
    ),
    "signing_key_bootstrap_wal": (
        b"agent-harness/mac/signing-key-bootstrap-wal/v1\0"
    ),
    "state_anchor_receipt": b"agent-harness/mac/state-anchor-receipt/v1\0",
    "check_record": b"agent-harness/mac/check-record/v1\0",
    "check_tail": b"agent-harness/mac/check-tail/v1\0",
    "anchor_transition_request": (
        b"agent-harness/mac/anchor-transition-request/v1\0"
    ),
}
_MAC_REQUIRED_FIELDS = {
    "adapter_receipt": (
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
    "installation_index": (
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
    "installation_publication_wal": (
        "prior_generation",
        "prior_index_digest",
        "new_generation",
        "new_index_digest",
        "transaction_digest",
        "plan_digest",
        "prepared_receipts",
        "phase",
    ),
    "authority_bootstrap_wal": (
        "locators",
        "broker_code_identity",
        "creator_id",
        "item_attributes",
        "conditional_inverses",
        "phase",
        "broker_signature",
    ),
    "signing_key_bootstrap_wal": (
        "keychain_locator",
        "operation_id",
        "creator_id",
        "item_attributes",
        "conditional_inverse",
        "phase",
    ),
    "state_anchor_receipt": (
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
    "check_record": (
        "sequence",
        "verifier_digest",
        "result",
        "output_digest",
        "prior_hash",
        "record_hash",
    ),
    "check_tail": (
        "task_id",
        "task_version",
        "expected_sequence",
        "expected_record_hash",
        "checkpoint_generation",
    ),
}


def _require_nonempty_string(
    document: Mapping[str, object], field: str
) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise IntegrityError(f"{field} must be a non-empty string")
    return value


def _require_digest(document: Mapping[str, object], field: str) -> str:
    value = _require_nonempty_string(document, field)
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise IntegrityError(f"{field} must be lowercase SHA-256")
    return value


def _require_generation(document: Mapping[str, object], field: str) -> int:
    value = document.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IntegrityError(f"{field} must be a non-negative integer")
    return value


def _require_absolute_path(
    document: Mapping[str, object], field: str
) -> str:
    value = _require_nonempty_string(document, field)
    if not Path(value).is_absolute():
        raise IntegrityError(f"{field} must be an absolute path")
    return value


def _require_string_list(
    document: Mapping[str, object], field: str
) -> list[str]:
    value = document.get(field)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise IntegrityError(f"{field} must be a string list")
    return value


def _require_phase(
    document: Mapping[str, object], *allowed: str
) -> None:
    if document.get("phase") not in allowed:
        raise IntegrityError("phase is invalid")


def _validate_mac_semantics(
    operation: str, document: Mapping[str, object]
) -> None:
    if operation == "adapter_receipt":
        for field in ("host", "receipt_id", "applied_transaction"):
            _require_nonempty_string(document, field)
        _require_string_list(document, "targets")
        for field in (
            "before_metadata_digest",
            "after_metadata_digest",
            "plan_digest",
            "anchor_commitment",
        ):
            _require_digest(document, field)
        _require_generation(document, "generation")
        _require_absolute_path(document, "root")
    elif operation == "installation_index":
        _require_generation(document, "generation")
        if document.get("lifecycle_state") not in {
            "INSTALLING",
            "INSTALLED",
            "FINALIZING",
            "FINALIZED",
            "ROLLED_BACK",
        }:
            raise IntegrityError("lifecycle_state is invalid")
        _require_nonempty_string(document, "publication_transaction")
        _require_digest(document, "predecessor_digest")
        _require_absolute_path(document, "runtime_root")
        _require_absolute_path(document, "rollback_root")
        _require_digest(document, "anchor_commitment")
        receipts = document.get("receipts")
        count = document.get("receipt_count")
        if (
            not isinstance(receipts, list)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count != len(receipts)
        ):
            raise IntegrityError("receipt_count must match receipts")
        for entry in receipts:
            if not isinstance(entry, Mapping):
                raise IntegrityError("receipt inventory entry is invalid")
            for field in ("receipt_id", "path"):
                _require_nonempty_string(entry, field)
            _require_digest(entry, "digest")
    elif operation == "installation_publication_wal":
        prior = _require_generation(document, "prior_generation")
        new = _require_generation(document, "new_generation")
        if new != prior + 1:
            raise IntegrityError("publication generations must advance by one")
        for field in (
            "prior_index_digest",
            "new_index_digest",
            "transaction_digest",
            "plan_digest",
        ):
            _require_digest(document, field)
        if not isinstance(document.get("prepared_receipts"), list):
            raise IntegrityError("prepared_receipts must be a list")
        _require_phase(document, "PREPARED", "APPLIED", "COMPLETE")
    elif operation == "authority_bootstrap_wal":
        locators = document.get("locators")
        attributes = document.get("item_attributes")
        inverses = document.get("conditional_inverses")
        if (
            not isinstance(locators, Mapping)
            or not locators
            or any(
                not isinstance(name, str)
                or not isinstance(locator, str)
                or not locator
                for name, locator in locators.items()
            )
        ):
            raise IntegrityError("locators must be a non-empty string mapping")
        if not isinstance(attributes, Mapping):
            raise IntegrityError("item_attributes must be an object")
        if not isinstance(inverses, list) or any(
            not isinstance(item, Mapping) for item in inverses
        ):
            raise IntegrityError("conditional_inverses must be an object list")
        _require_nonempty_string(document, "broker_code_identity")
        _require_nonempty_string(document, "creator_id")
        signature = document.get("broker_signature")
        if signature is not None and (
            not isinstance(signature, str) or not signature
        ):
            raise IntegrityError("broker_signature is invalid")
        _require_phase(document, "PREPARED", "COMPLETE")
    elif operation == "signing_key_bootstrap_wal":
        for field in ("keychain_locator", "operation_id", "creator_id"):
            _require_nonempty_string(document, field)
        if not isinstance(document.get("item_attributes"), Mapping):
            raise IntegrityError("item_attributes must be an object")
        if not isinstance(document.get("conditional_inverse"), Mapping):
            raise IntegrityError("conditional_inverse must be an object")
        _require_phase(document, "PREPARED", "COMPLETE")
    elif operation == "state_anchor_receipt":
        for field in (
            "anchor_namespace",
            "anchor_backend_id",
            "receipt_key_id",
            "transition_domain",
            "operation_id",
            "broker_receipt",
        ):
            _require_nonempty_string(document, field)
        _require_digest(document, "transition_digest")
        old = _require_generation(document, "old_generation")
        new = _require_generation(document, "new_generation")
        if new != old + 1:
            raise IntegrityError("anchor generations must advance by one")
        _require_digest(document, "old_commitment")
        _require_digest(document, "new_commitment")
    elif operation == "check_record":
        _require_generation(document, "sequence")
        for field in (
            "verifier_digest",
            "output_digest",
            "prior_hash",
            "record_hash",
        ):
            _require_digest(document, field)
        if document.get("result") not in {"PASS", "FAIL", "WARN"}:
            raise IntegrityError("check result is invalid")
    elif operation == "check_tail":
        _require_nonempty_string(document, "task_id")
        for field in (
            "task_version",
            "expected_sequence",
            "checkpoint_generation",
        ):
            _require_generation(document, field)
        _require_digest(document, "expected_record_hash")


def _json_copy(value: object) -> object:
    return json.loads(canonical_json_bytes(value))


def _unsigned(value: Mapping[str, object], field: str = "mac") -> dict[str, object]:
    return {key: copy.deepcopy(item) for key, item in value.items() if key != field}


class _VerifiedValue:
    __slots__ = (
        "__document",
        "installation_id",
        "generation",
        "root",
        "anchor_commitment",
        "__consumed",
    )

    def __init__(
        self,
        token: object,
        document: Mapping[str, object],
        *,
        installation_id: str,
        generation: int | None,
        root: str | None,
        anchor_commitment: str | None,
    ) -> None:
        if token is not _VERIFIED_TOKEN:
            raise TypeError(f"{type(self).__name__} cannot be constructed directly")
        self.__document = _json_copy(document)
        self.installation_id = installation_id
        self.generation = generation
        self.root = root
        self.anchor_commitment = anchor_commitment
        self.__consumed = False

    @property
    def document(self) -> dict[str, object]:
        return copy.deepcopy(self.__document)

    @property
    def consumed(self) -> bool:
        return self.__consumed

    def require_binding(
        self,
        *,
        expected_installation_id: str | None = None,
        expected_generation: int | None = None,
        expected_root: str | None = None,
        expected_anchor_commitment: str | None = None,
    ) -> None:
        expected = (
            ("installation_id", expected_installation_id, self.installation_id),
            ("generation", expected_generation, self.generation),
            ("root", expected_root, self.root),
            (
                "anchor_commitment",
                expected_anchor_commitment,
                self.anchor_commitment,
            ),
        )
        for name, wanted, actual in expected:
            if wanted is not None and wanted != actual:
                raise IntegrityError(f"verified binding mismatch for {name}")

    def consume(
        self,
        *,
        expected_installation_id: str | None = None,
        expected_generation: int | None = None,
        expected_root: str | None = None,
        expected_anchor_commitment: str | None = None,
    ) -> dict[str, object]:
        if self.__consumed:
            raise IntegrityError("verified value already consumed")
        self.require_binding(
            expected_installation_id=expected_installation_id,
            expected_generation=expected_generation,
            expected_root=expected_root,
            expected_anchor_commitment=expected_anchor_commitment,
        )
        self.__consumed = True
        return self.document

    def __reduce__(self):
        raise TypeError(f"{type(self).__name__} is non-serializable")


class VerifiedAdapterReceipt(_VerifiedValue):
    __slots__ = ()


class VerifiedStateAnchorReceipt(_VerifiedValue):
    __slots__ = ()


class VerifiedInstallPlan(_VerifiedValue):
    __slots__ = ()


class VerifiedInstallationIndex(_VerifiedValue):
    __slots__ = ()


class VerifiedBootstrapPlan(_VerifiedValue):
    __slots__ = ()


class VerifiedRollbackPlan(_VerifiedValue):
    __slots__ = ()


class VerifiedFinalizationPlan(_VerifiedValue):
    __slots__ = ()


class VerifiedInstallationState(_VerifiedValue):
    __slots__ = ("__receipts",)

    def __init__(
        self,
        token: object,
        document: Mapping[str, object],
        *,
        installation_id: str,
        generation: int | None,
        root: str | None,
        anchor_commitment: str | None,
        receipts: Mapping[str, VerifiedAdapterReceipt],
    ) -> None:
        super().__init__(
            token,
            document,
            installation_id=installation_id,
            generation=generation,
            root=root,
            anchor_commitment=anchor_commitment,
        )
        self.__receipts = MappingProxyType(dict(receipts))

    @property
    def receipts(self) -> Mapping[str, VerifiedAdapterReceipt]:
        return self.__receipts


def _issue(
    verified_type,
    document: Mapping[str, object],
    *,
    installation_id: str,
    generation: int | None,
    root: str | None,
    anchor_commitment: str | None,
):
    return verified_type(
        _VERIFIED_TOKEN,
        document,
        installation_id=installation_id,
        generation=generation,
        root=root,
        anchor_commitment=anchor_commitment,
    )


class IntegrityAuthority:
    """Narrow authenticated-document boundary; it exposes no generic signer."""

    __slots__ = (
        "__key_id",
        "__installation_id",
        "__mac_operation",
        "qualifying",
    )

    def __init__(
        self,
        token: object,
        *,
        key_id: str,
        installation_id: str,
        mac_operation: Callable[[bytes, bytes], bytes],
        qualifying: bool,
    ) -> None:
        if token is not _AUTHORITY_TOKEN:
            raise TypeError("IntegrityAuthority requires an opaque key handle")
        try:
            uuid.UUID(installation_id)
        except (AttributeError, TypeError, ValueError) as error:
            raise IntegrityError("authority installation_id must be UUID") from error
        self.__key_id = key_id
        self.__installation_id = installation_id
        self.__mac_operation = mac_operation
        self.qualifying = qualifying

    @property
    def key_id(self) -> str:
        return self.__key_id

    def _mac_for(self, operation: str, value: Mapping[str, object]) -> str:
        if value.get("installation_id") != self.__installation_id:
            raise IntegrityError("authenticated payload installation mismatch")
        payload = canonical_json_bytes(_unsigned(value))
        return self.__mac_operation(_MAC_DOMAINS[operation], payload).hex()

    def _mac_document(
        self, operation: str, kind: str, value: Mapping[str, object]
    ) -> str:
        document = require_document(value, kind)
        missing = [
            field
            for field in _MAC_REQUIRED_FIELDS[operation]
            if field not in document
        ]
        if missing:
            raise IntegrityError(
                f"{kind} is incomplete for authentication: {', '.join(missing)}"
            )
        _validate_mac_semantics(operation, document)
        return self._mac_for(operation, document)

    def mac_adapter_receipt(self, value: Mapping[str, object]) -> str:
        return self._mac_document(
            "adapter_receipt", "adapter-receipt", value
        )

    def mac_installation_index(self, value: Mapping[str, object]) -> str:
        return self._mac_document(
            "installation_index", "installation-index", value
        )

    def mac_installation_publication_wal(
        self, value: Mapping[str, object]
    ) -> str:
        return self._mac_document(
            "installation_publication_wal",
            "installation-publication-wal",
            value,
        )

    def mac_authority_bootstrap_wal(self, value: Mapping[str, object]) -> str:
        return self._mac_document(
            "authority_bootstrap_wal", "authority-bootstrap-wal", value
        )

    def mac_signing_key_bootstrap_wal(
        self, value: Mapping[str, object]
    ) -> str:
        return self._mac_document(
            "signing_key_bootstrap_wal",
            "signing-key-bootstrap-wal",
            value,
        )

    def mac_state_anchor_receipt(self, value: Mapping[str, object]) -> str:
        return self._mac_document(
            "state_anchor_receipt", "state-anchor-receipt", value
        )

    def mac_check_record(self, value: Mapping[str, object]) -> str:
        return self._mac_document("check_record", "check-record", value)

    def mac_check_tail(self, value: Mapping[str, object]) -> str:
        return self._mac_document("check_tail", "check-tail", value)

    def authenticate_installation_anchor_transition(
        self,
        phase: VerifiedInstallationState,
        value: Mapping[str, object],
    ) -> str:
        """Authenticate only the exact transition derived from verified phase state."""
        if not isinstance(phase, VerifiedInstallationState):
            raise TypeError("VerifiedInstallationState required")
        phase_document = phase.document
        self._verify_mac(phase_document, "installation_index")
        transition = phase_document.get("anchor_transition")
        if not isinstance(transition, Mapping):
            raise IntegrityError("verified installation transition is missing")
        unsigned = _unsigned(value, "authorization_mac")
        required = {
            "domain",
            "namespace",
            "installation_id",
            "subject_kind",
            "subject_id",
            "operation_kind",
            "old_generation",
            "old_commitment",
            "new_generation",
            "new_commitment",
            "plan_digest",
            "wal_digest",
            "event_digest",
            "check_digest",
            "record_digest",
            "authorization_epoch",
            "caller_code_identity",
            "broker_code_identity",
            "nonce",
            "expires_at",
        }
        if set(unsigned) != required:
            raise IntegrityError("anchor transition fields mismatch")
        receipts = phase.receipts.values()
        plan_digests = {
            receipt.document.get("plan_digest") for receipt in receipts
        }
        expected = {
            "domain": "installation-transaction",
            "installation_id": phase.installation_id,
            "subject_kind": "task",
            "subject_id": phase_document.get("publication_transaction"),
            "operation_kind": "publish-installation",
            "old_generation": phase.generation - 1,
            "old_commitment": transition.get("old_commitment"),
            "new_generation": phase.generation,
            "new_commitment": transition.get("new_commitment"),
            "plan_digest": (
                next(iter(plan_digests)) if len(plan_digests) == 1 else None
            ),
            "wal_digest": transition.get("wal_digest"),
            "event_digest": transition.get("event_digest"),
            "check_digest": transition.get("check_digest"),
            "record_digest": transition.get("record_digest"),
            "authorization_epoch": transition.get("authorization_epoch"),
        }
        if any(unsigned.get(name) != expected_value for name, expected_value in expected.items()):
            raise IntegrityError("anchor transition verified-state binding mismatch")
        for name in (
            "namespace",
            "caller_code_identity",
            "broker_code_identity",
            "nonce",
        ):
            _require_nonempty_string(unsigned, name)
        expires_at = unsigned.get("expires_at")
        if isinstance(expires_at, bool) or not isinstance(expires_at, int):
            raise IntegrityError("anchor transition expiry is invalid")
        return self._mac_for("anchor_transition_request", unsigned)

    def _verify_mac(
        self, value: Mapping[str, object], operation: str
    ) -> dict[str, object]:
        document = require_document(
            dict(value),
            operation.replace("_", "-"),
        )
        missing = [
            field
            for field in _MAC_REQUIRED_FIELDS[operation]
            if field not in document
        ]
        if missing:
            raise IntegrityError(
                f"{operation.replace('_', '-')} incomplete authentication: "
                + ", ".join(missing)
            )
        _validate_mac_semantics(operation, document)
        if "mac" not in document:
            raise IntegrityError("missing MAC")
        given = document["mac"]
        if (
            not isinstance(given, str)
            or len(given) != 64
            or any(character not in "0123456789abcdef" for character in given)
        ):
            raise IntegrityError("malformed MAC")
        expected = self._mac_for(operation, document)
        if not hmac.compare_digest(given, expected):
            raise IntegrityError("MAC verification failed")
        return document

    @staticmethod
    def _bindings(
        document: Mapping[str, object],
        *,
        expected_installation_id: str,
        expected_generation: int | None,
        expected_root: str | None,
        expected_anchor_commitment: str | None,
        root_field: str,
    ) -> tuple[str, int | None, str | None, str | None]:
        installation_id = document.get("installation_id")
        if installation_id != expected_installation_id:
            raise IntegrityError("installation binding mismatch")
        generation = document.get("generation")
        if expected_generation is not None and generation != expected_generation:
            raise IntegrityError("generation binding mismatch")
        root = document.get(root_field)
        if expected_root is not None and root != expected_root:
            raise IntegrityError("root binding mismatch")
        anchor = document.get("anchor_commitment")
        if (
            expected_anchor_commitment is not None
            and anchor != expected_anchor_commitment
        ):
            raise IntegrityError("anchor binding mismatch")
        return installation_id, generation, root, anchor

    def verify_adapter_receipt(
        self,
        value: object,
        *,
        expected_installation_id: str,
        expected_generation: int | None = None,
        expected_root: str | None = None,
        expected_anchor_commitment: str | None = None,
    ) -> VerifiedAdapterReceipt:
        document = require_document(value, "adapter-receipt")
        bindings = self._bindings(
            document,
            expected_installation_id=expected_installation_id,
            expected_generation=expected_generation,
            expected_root=expected_root,
            expected_anchor_commitment=expected_anchor_commitment,
            root_field="root",
        )
        verified = self._verify_mac(document, "adapter_receipt")
        return _issue(
            VerifiedAdapterReceipt,
            verified,
            installation_id=bindings[0],
            generation=bindings[1],
            root=bindings[2],
            anchor_commitment=bindings[3],
        )

    def verify_installation_index(
        self,
        value: object,
        *,
        expected_installation_id: str,
        expected_generation: int | None = None,
        expected_root: str | None = None,
        expected_anchor_commitment: str | None = None,
    ) -> VerifiedInstallationIndex:
        document = require_document(value, "installation-index")
        bindings = self._bindings(
            document,
            expected_installation_id=expected_installation_id,
            expected_generation=expected_generation,
            expected_root=expected_root,
            expected_anchor_commitment=expected_anchor_commitment,
            root_field="runtime_root",
        )
        verified = self._verify_mac(document, "installation_index")
        return _issue(
            VerifiedInstallationIndex,
            verified,
            installation_id=bindings[0],
            generation=bindings[1],
            root=bindings[2],
            anchor_commitment=bindings[3],
        )

    def verify_install_plan(
        self,
        value: object,
        *,
        expected_installation_id: str,
        expected_generation: int | None = None,
        expected_root: str | None = None,
        expected_anchor_commitment: str | None = None,
    ) -> VerifiedInstallPlan:
        document = require_document(value, "install-plan")
        given = document.get("plan_digest")
        if not isinstance(given, str):
            raise IntegrityError("missing plan digest")
        expected = hashlib.sha256(
            FINAL_INSTALL_PLAN_DOMAIN
            + canonical_json_bytes(
                {
                    key: item
                    for key, item in document.items()
                    if key != "plan_digest"
                }
            )
        ).hexdigest()
        if not hmac.compare_digest(given, expected):
            raise IntegrityError("plan digest mismatch")
        bindings = self._bindings(
            document,
            expected_installation_id=expected_installation_id,
            expected_generation=expected_generation,
            expected_root=expected_root,
            expected_anchor_commitment=expected_anchor_commitment,
            root_field="runtime_root",
        )
        return _issue(
            VerifiedInstallPlan,
            document,
            installation_id=bindings[0],
            generation=bindings[1],
            root=bindings[2],
            anchor_commitment=bindings[3],
        )

    def verify_state_anchor_receipt(
        self,
        value: object,
        *,
        expected_installation_id: str,
        expected_generation: int | None = None,
        expected_anchor_commitment: str | None = None,
    ) -> VerifiedStateAnchorReceipt:
        document = require_document(value, "state-anchor-receipt")
        verified = self._verify_mac(document, "state_anchor_receipt")
        if verified.get("installation_id") != expected_installation_id:
            raise IntegrityError("installation binding mismatch")
        generation = verified.get("new_generation")
        commitment = verified.get("new_commitment")
        if (
            expected_generation is not None
            and generation != expected_generation
        ):
            raise IntegrityError("generation binding mismatch")
        if (
            expected_anchor_commitment is not None
            and commitment != expected_anchor_commitment
        ):
            raise IntegrityError("anchor_commitment binding mismatch")
        return _issue(
            VerifiedStateAnchorReceipt,
            verified,
            installation_id=expected_installation_id,
            generation=generation,
            root=None,
            anchor_commitment=commitment,
        )

    def verify_bootstrap_plan(
        self,
        value: object,
        *,
        expected_installation_id: str,
        expected_generation: int | None,
        expected_root: str | None,
        expected_anchor_commitment: str | None,
    ) -> VerifiedBootstrapPlan:
        document = self._verify_mac(
            require_document(value, "signing-key-bootstrap-wal"),
            "signing_key_bootstrap_wal",
        )
        bindings = self._bindings(
            document,
            expected_installation_id=expected_installation_id,
            expected_generation=expected_generation,
            expected_root=expected_root,
            expected_anchor_commitment=expected_anchor_commitment,
            root_field="root",
        )
        return _issue(
            VerifiedBootstrapPlan,
            document,
            installation_id=bindings[0],
            generation=bindings[1],
            root=bindings[2],
            anchor_commitment=bindings[3],
        )

    def verify_finalization_plan(
        self,
        value: object,
        *,
        expected_installation_id: str,
        expected_generation: int | None,
        expected_root: str | None,
        expected_anchor_commitment: str | None,
    ) -> VerifiedFinalizationPlan:
        document = require_document(value, "finalization-plan")
        given = document.get("plan_digest")
        expected = hashlib.sha256(
            b"agent-harness/finalization-plan/v1\0"
            + canonical_json_bytes(
                {
                    key: item
                    for key, item in document.items()
                    if key != "plan_digest"
                }
            )
        ).hexdigest()
        if not isinstance(given, str) or not hmac.compare_digest(given, expected):
            raise IntegrityError("finalization plan digest mismatch")
        bindings = self._bindings(
            document,
            expected_installation_id=expected_installation_id,
            expected_generation=expected_generation,
            expected_root=expected_root,
            expected_anchor_commitment=expected_anchor_commitment,
            root_field="root",
        )
        return _issue(
            VerifiedFinalizationPlan,
            document,
            installation_id=bindings[0],
            generation=bindings[1],
            root=bindings[2],
            anchor_commitment=bindings[3],
        )


def create_test_integrity_authority(
    secret: bytes,
    *,
    installation_id: str,
    key_id: str = "test-integrity-key",
) -> IntegrityAuthority:
    if not isinstance(secret, bytes) or not secret:
        raise ValueError("test secret must be non-empty bytes")
    retained_secret = bytes(secret)

    def operation(domain: bytes, payload: bytes) -> bytes:
        return hmac.new(retained_secret, domain + payload, hashlib.sha256).digest()

    return IntegrityAuthority(
        _AUTHORITY_TOKEN,
        key_id=key_id,
        installation_id=installation_id,
        mac_operation=operation,
        qualifying=False,
    )


def load_installation_state(
    index: VerifiedInstallationIndex,
    registry: Mapping[str, object],
    *,
    authority: IntegrityAuthority,
) -> VerifiedInstallationState:
    if not isinstance(index, VerifiedInstallationIndex):
        raise TypeError("verified installation index required")
    document = index.document
    entries = document.get("receipts")
    receipt_count = document.get("receipt_count")
    if (
        not isinstance(entries, list)
        or isinstance(receipt_count, bool)
        or not isinstance(receipt_count, int)
        or receipt_count != len(entries)
    ):
        raise IntegrityError("receipt registry bijection count mismatch")

    by_path: dict[str, dict[str, object]] = {}
    receipt_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise IntegrityError("receipt registry bijection entry malformed")
        path = entry.get("path")
        receipt_id = entry.get("receipt_id")
        digest = entry.get("digest")
        if (
            not isinstance(path, str)
            or not isinstance(receipt_id, str)
            or not isinstance(digest, str)
            or path in by_path
            or receipt_id in receipt_ids
        ):
            raise IntegrityError("receipt registry bijection is not unique")
        by_path[path] = entry
        receipt_ids.add(receipt_id)
    if set(registry) != set(by_path):
        raise IntegrityError("receipt registry bijection mismatch")

    verified_receipts: dict[str, VerifiedAdapterReceipt] = {}
    for path, entry in by_path.items():
        raw_receipt = registry[path]
        if not isinstance(raw_receipt, dict):
            raise IntegrityError("receipt registry contains unchecked document")
        digest = hashlib.sha256(canonical_json_bytes(raw_receipt)).hexdigest()
        if not hmac.compare_digest(digest, entry["digest"]):
            raise IntegrityError("receipt registry digest mismatch")
        verified = authority.verify_adapter_receipt(
            raw_receipt,
            expected_installation_id=index.installation_id,
            expected_generation=index.generation,
            expected_root=index.root,
            expected_anchor_commitment=index.anchor_commitment,
        )
        receipt_id = raw_receipt.get("receipt_id")
        if receipt_id != entry["receipt_id"]:
            raise IntegrityError("receipt registry ID mismatch")
        verified_receipts[receipt_id] = verified

    return VerifiedInstallationState(
        _VERIFIED_TOKEN,
        document,
        installation_id=index.installation_id,
        generation=index.generation,
        root=index.root,
        anchor_commitment=index.anchor_commitment,
        receipts=verified_receipts,
    )


def issue_rollback_plan_for_test(
    *,
    installation_id: str,
    generation: int,
    root: str,
    anchor_commitment: str,
    document: Mapping[str, object],
) -> VerifiedRollbackPlan:
    return _issue(
        VerifiedRollbackPlan,
        document,
        installation_id=installation_id,
        generation=generation,
        root=root,
        anchor_commitment=anchor_commitment,
    )
