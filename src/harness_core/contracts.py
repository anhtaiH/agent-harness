from __future__ import annotations

import json
import re
import uuid


SCHEMA_VERSION = 1
BASE_FIELDS = frozenset(
    {"schema", "schema_version", "created_at", "installation_id"}
)
FINAL_INSTALL_PLAN_DOMAIN = b"agent-harness/final-install-plan/v1\0"
_RFC3339_UTC = re.compile(
    r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\Z"
)


class SchemaError(ValueError):
    pass


def require_rfc3339_utc(value: object) -> str:
    if not isinstance(value, str) or not _RFC3339_UTC.fullmatch(value):
        raise SchemaError("created_at must be an RFC3339 UTC timestamp")
    try:
        from datetime import datetime

        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise SchemaError("created_at must be an RFC3339 UTC timestamp") from error
    return value


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except ValueError as error:
        raise SchemaError("canonical JSON contains a non-finite JSON number") from error


def new_document(
    kind: str,
    installation_id: str,
    *,
    created_at: str,
    **payload: object,
) -> dict[str, object]:
    try:
        uuid.UUID(installation_id)
    except (AttributeError, TypeError, ValueError) as error:
        raise SchemaError("installation_id must be a UUID") from error
    if BASE_FIELDS.intersection(payload):
        raise SchemaError("payload contains reserved field")
    require_rfc3339_utc(created_at)
    return {
        "schema": f"agent-harness/{kind}",
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "installation_id": installation_id,
        **payload,
    }


def require_document(
    value: object, kind: str, *, mutable: bool = True
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SchemaError(f"{kind} must be an object")
    if value.get("schema") != f"agent-harness/{kind}":
        raise SchemaError(f"expected agent-harness/{kind}")
    version = value.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise SchemaError("schema_version must be a positive integer")
    if mutable and version > SCHEMA_VERSION:
        raise SchemaError(f"newer schema_version {version} is read-only")
    return dict(value)
