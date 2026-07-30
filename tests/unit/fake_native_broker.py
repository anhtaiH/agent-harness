#!/usr/bin/env python3
from __future__ import annotations

import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import uuid


STATE = Path(os.environ["AGENT_HARNESS_FAKE_NATIVE_STATE"])
LOCK = STATE.with_suffix(".lock")
RECEIPT_KEY = b"fake-native-receipt-key"
APPROVAL_KEY = b"fake-native-approval-key"
APPROVAL_PUBLIC_KEY_DIGEST = hashlib.sha256(APPROVAL_KEY).hexdigest()
CODE_IDENTITY = "test-native-code-v1"
TRANSITION_DOMAIN = b"agent-harness/verified-anchor-transition/v1\0"
TRANSITION_MAC_DOMAIN = b"agent-harness/mac/anchor-transition-request/v1\0"


def read_request() -> dict[str, object]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("request must be an object")
    return value


def load_state() -> dict[str, object]:
    if not STATE.exists():
        return {}
    value = json.loads(STATE.read_text())
    if not isinstance(value, dict):
        raise ValueError("state must be an object")
    return value


def save_state(value: dict[str, object]) -> None:
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))
    os.replace(temporary, STATE)


def locked(operation):
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return operation()


def receipt_signature(payload: bytes) -> str:
    return hmac.new(RECEIPT_KEY, payload, hashlib.sha256).hexdigest()


def approval_signature(envelope: bytes, summary: bytes) -> dict[str, str]:
    return {
        "algorithm": "p256-sha256",
        "public_key_digest": APPROVAL_PUBLIC_KEY_DIGEST,
        "envelope_digest": hashlib.sha256(envelope).hexdigest(),
        "summary_digest": hashlib.sha256(summary).hexdigest(),
        "signature": hmac.new(
            APPROVAL_KEY, envelope + b"\0" + summary, hashlib.sha256
        ).hexdigest(),
    }


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def require_transition_authorization(request: dict[str, object]) -> None:
    encoded_key = os.environ.get("AGENT_HARNESS_FAKE_TRANSITION_KEY")
    authorization = request.get("authorization_mac")
    if not encoded_key or not isinstance(authorization, str):
        raise ValueError("authenticated anchor transition required")
    try:
        key = bytes.fromhex(encoded_key)
    except ValueError as error:
        raise ValueError("authenticated anchor transition required") from error
    unsigned = {
        key: value
        for key, value in request.items()
        if key
        not in {
            "authorization_mac",
            "transition_domain",
            "transition_digest",
        }
    }
    encoded = canonical_json(unsigned)
    expected_digest = hashlib.sha256(TRANSITION_DOMAIN + encoded).hexdigest()
    expected_mac = hmac.new(
        key, TRANSITION_MAC_DOMAIN + encoded, hashlib.sha256
    ).hexdigest()
    if (
        request.get("transition_domain") != unsigned.get("domain")
        or request.get("transition_digest") != expected_digest
        or not hmac.compare_digest(authorization, expected_mac)
        or not isinstance(request.get("expires_at"), int)
        or request["expires_at"] <= int(datetime.now(timezone.utc).timestamp())
    ):
        raise ValueError("authenticated anchor transition required")


def require_approval_envelope(envelope: bytes, summary: object) -> None:
    try:
        document = json.loads(envelope)
    except json.JSONDecodeError as error:
        raise ValueError("version-one external-write envelope required") from error
    if not isinstance(document, dict) or canonical_json(document) != envelope:
        raise ValueError("version-one external-write envelope required")
    required = {
        "schema",
        "schema_version",
        "installation_id",
        "intent_digest",
        "predecessor_task_event_hash",
        "expires_at",
    }
    if (
        not required <= set(document)
        or document.get("schema")
        != "agent-harness/external-write-envelope"
        or document.get("schema_version") != 1
        or not isinstance(summary, str)
        or not summary.strip()
    ):
        raise ValueError("version-one external-write envelope required")
    try:
        uuid.UUID(document["installation_id"])
        expires_at = datetime.fromisoformat(
            document["expires_at"].removesuffix("Z") + "+00:00"
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("version-one external-write envelope required") from error
    state = load_state()
    markers = state.get("bootstrap_markers")
    if (
        not isinstance(markers, dict)
        or markers.get("installation_id") != document["installation_id"]
    ):
        raise ValueError("approval installation binding mismatch")
    for field in ("intent_digest", "predecessor_task_event_hash"):
        value = document.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("version-one external-write envelope required")
    lifetime = (
        expires_at - datetime.now(timezone.utc)
    ).total_seconds()
    if lifetime <= 0 or lifetime > 900:
        raise ValueError("external-write envelope expiry is invalid")


def bootstrap(
    request: dict[str, object], *, allow_existing: bool
) -> dict[str, object]:
    markers = {
        key: request[key]
        for key in (
            "created_at",
            "installation_id",
            "creator_id",
            "descriptor_digest",
            "final_plan_digest",
            "wal_digest",
            "anchor_namespace",
            "initial_anchor_generation",
            "initial_anchor_commitment",
        )
    }

    def mutate():
        state = load_state()
        existing = state.get("bootstrap_markers")
        if existing is not None and existing != markers:
            raise ValueError("foreign fixed-locator collision")
        if existing is not None and not allow_existing:
            raise ValueError("authority bootstrap fixed locators are not absent")
        state["bootstrap_markers"] = markers
        items = state.setdefault("bootstrap_items", [])
        crash_after = request.get("test_crash_after")
        for stage in (
            "approval_key",
            "receipt_key",
            "anchor",
            "bootstrap_record",
        ):
            if stage in items:
                continue
            items.append(stage)
            if stage == "anchor":
                state["anchor"] = {
                    "namespace": request["anchor_namespace"],
                    "generation": request["initial_anchor_generation"],
                    "commitment": request["initial_anchor_commitment"],
                }
            save_state(state)
            if crash_after == stage:
                raise RuntimeError(f"injected native crash after {stage}")
        state["bootstrap_complete"] = True
        save_state(state)
        return state

    locked(mutate)
    content_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest = {
        "schema": "agent-harness/authority-manifest",
        "schema_version": 1,
        "created_at": request["created_at"],
        "installation_id": request["installation_id"],
        "broker_code_identity": CODE_IDENTITY,
        "broker_content_digest": content_digest,
        "approval_public_key_digest": APPROVAL_PUBLIC_KEY_DIGEST,
        "approval_persistent_reference": "opaque:fake-approval-key",
        "anchor_backend_id": "fake-native-anchor-v1",
        "anchor_namespace": request["anchor_namespace"],
        "receipt_key_id": "fake-native-receipt-key",
        "receipt_public_key_digest": hashlib.sha256(RECEIPT_KEY).hexdigest(),
        "receipt_persistent_reference": "opaque:fake-receipt-key",
        "terminal_pin_locator": "agent-harness.authority.terminal-pin.v1",
        "terminal_pin_attributes": {
            "add_only": True,
            "contains_key_material": False,
            "synchronizable": False,
            "accessibility": "AfterFirstUnlockThisDeviceOnly",
        },
        "capability_state": [
            "protected-user-presence-approval",
            "installation-anchor-cas",
            "broker-signed-receipts",
            "retirement-terminal-pin-add",
        ],
        "bootstrap_digest": request["descriptor_digest"],
        "pending_plan_commitment": request["final_plan_digest"],
    }
    encoded = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode()
    manifest["broker_signature"] = receipt_signature(encoded)
    return manifest


def main() -> None:
    command = sys.argv[1]
    if command == "--attest":
        response = {
            "protocol_version": 1,
            "code_identity": CODE_IDENTITY,
            "content_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
    elif command == "health":
        response = {
            "healthy": True,
            "code_identity": CODE_IDENTITY,
            "approval_public_key_digest": APPROVAL_PUBLIC_KEY_DIGEST,
        }
    elif command == "bootstrap":
        response = bootstrap(read_request(), allow_existing=False)
    elif command == "bootstrap-recover":
        response = bootstrap(read_request(), allow_existing=True)
    elif command == "anchor-read":
        state = load_state()
        response = state["anchor"]
    elif command == "anchor-compare-and-advance":
        request = read_request()
        require_transition_authorization(request)

        def compare_and_advance():
            state = load_state()
            anchor = state["anchor"]
            if (
                anchor["namespace"] != request["namespace"]
                or anchor["generation"] != request["old_generation"]
                or anchor["commitment"] != request["old_commitment"]
            ):
                raise ValueError("stale anchor generation or commitment")
            anchor = {
                "namespace": request["namespace"],
                "generation": request["new_generation"],
                "commitment": request["new_commitment"],
            }
            state["anchor"] = anchor
            save_state(state)
            receipt = {
                "schema": "agent-harness/state-anchor-receipt",
                "schema_version": 1,
                "created_at": datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "installation_id": request["installation_id"],
                "anchor_namespace": request["namespace"],
                "anchor_backend_id": "fake-native-anchor-v1",
                "receipt_key_id": "fake-native-receipt-key",
                "transition_domain": request["transition_domain"],
                "transition_digest": request["transition_digest"],
                "old_generation": request["old_generation"],
                "old_commitment": request["old_commitment"],
                "new_generation": request["new_generation"],
                "new_commitment": request["new_commitment"],
                "operation_id": request["nonce"],
            }
            payload = json.dumps(
                receipt, sort_keys=True, separators=(",", ":")
            ).encode()
            receipt["broker_receipt"] = receipt_signature(payload)
            return receipt

        response = locked(compare_and_advance)
    elif command == "receipt-verify":
        request = read_request()
        payload = base64.b64decode(request["payload_base64"], validate=True)
        response = {
            "valid": hmac.compare_digest(
                receipt_signature(payload), request["signature"]
            )
        }
    elif command == "approval-sign":
        request = read_request()
        envelope = base64.b64decode(request["envelope_base64"], validate=True)
        require_approval_envelope(envelope, request.get("summary"))
        response = approval_signature(envelope, request["summary"].encode())
    elif command == "approval-verify":
        request = read_request()
        envelope = base64.b64decode(request["envelope_base64"], validate=True)
        expected = approval_signature(envelope, request["summary"].encode())
        response = {
            "valid": isinstance(request["approval"], dict)
            and request["approval"] == expected
        }
    elif command == "retirement-pin":
        request = read_request()
        signature = request.get("broker_signature")
        unsigned = {
            key: value
            for key, value in request.items()
            if key != "broker_signature"
        }
        if not isinstance(signature, str) or not hmac.compare_digest(
            receipt_signature(
                json.dumps(
                    unsigned, sort_keys=True, separators=(",", ":")
                ).encode()
            ),
            signature,
        ):
            raise ValueError("authenticated retirement capability required")

        def add_terminal_pin():
            state = load_state()
            if "terminal_pin" in state:
                raise ValueError("foreign fixed-locator collision")
            state["terminal_pin"] = unsigned
            save_state(state)

        locked(add_terminal_pin)
        response = {"ok": True}
    else:
        raise ValueError("unsupported fake native operation")
    print(json.dumps(response, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"fake native broker: {error}", file=sys.stderr)
        raise SystemExit(1)
