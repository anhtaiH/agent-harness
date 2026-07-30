from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any


INSTALLATION_ID = "12345678-1234-5678-9234-567812345678"
OTHER_INSTALLATION_ID = "87654321-4321-6789-a234-567812345678"
CREATED_AT = "2026-07-29T12:34:56Z"
ROOT_COMMIT = "a" * 40
RUNTIME_ROOT = "/var/lib/agent-harness/runtime"
ROLLBACK_ROOT = "/var/lib/agent-harness/rollback"
ANCHOR_COMMITMENT = "1" * 64
OTHER_ANCHOR_COMMITMENT = "2" * 64


def valid_workspace_manifest(
    *, extra: dict[str, object] | None = None
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "agent-harness/workspace-manifest",
        "schema_version": 1,
        "created_at": CREATED_AT,
        "installation_id": INSTALLATION_ID,
        "workspace": "test",
        "source_commit": ROOT_COMMIT,
        "source_content_identity": "3" * 64,
        "runtime_root": RUNTIME_ROOT,
        "rollback_root": ROLLBACK_ROOT,
        "generation": 0,
    }
    if extra:
        document.update(extra)
    return document


def canonical_digest(domain: bytes, value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(domain + encoded).hexdigest()


def git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "-c", "protocol.file.allow=always", *args],
        cwd=repo,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout


def init_repo(path: Path, files: dict[str, bytes] | None = None) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "agent@example.invalid")
    git(path, "config", "user.name", "Agent Harness Test")
    for relative, content in (files or {"tracked.txt": b"tracked\n"}).items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    git(path, "add", ".")
    git(path, "commit", "-qm", "fixture")
    return path


def commit_all(repo: Path, message: str = "fixture change") -> str:
    git(repo, "add", ".")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD").decode().strip()


class MemoryAuthorityBackend:
    """Specific native-broker double; production orchestration remains real."""

    qualifying = False

    def __init__(self, *, code_identity: str = "test-broker-code-v1") -> None:
        self.code_identity = code_identity
        self.items: dict[str, dict[str, Any]] = {}
        self.anchors: dict[str, tuple[int, str]] = {}
        self.provision_calls = 0
        self.approval_public_key_digest = "a" * 64
        self.user_presence_available = True

    def observe(self, locators: tuple[str, ...]) -> dict[str, object]:
        return {
            locator: (
                {"state": "absent"}
                if locator not in self.items
                else {"state": "present", "item": dict(self.items[locator])}
            )
            for locator in locators
        }

    def add_item(self, locator: str, value: dict[str, Any]) -> None:
        if locator in self.items:
            raise FileExistsError(locator)
        self.items[locator] = dict(value)

    def read_item(self, locator: str) -> dict[str, Any] | None:
        value = self.items.get(locator)
        return dict(value) if value is not None else None

    def remove_exact(self, locator: str, markers: dict[str, object]) -> bool:
        value = self.items.get(locator)
        if value is None:
            return True
        if any(value.get(key) != expected for key, expected in markers.items()):
            return False
        del self.items[locator]
        return True

    def sign_receipt(self, payload: bytes) -> str:
        return hashlib.sha256(b"test-broker-receipt\0" + payload).hexdigest()

    def verify_receipt(self, payload: bytes, signature: str) -> bool:
        return self.sign_receipt(payload) == signature

    def approve(
        self, envelope: bytes, summary: bytes, *, protected_user_presence: bool
    ) -> str:
        if not self.user_presence_available or not protected_user_presence:
            raise PermissionError("protected user presence required")
        return hashlib.sha256(
            b"test-approval\0" + envelope + b"\0" + summary
        ).hexdigest()
