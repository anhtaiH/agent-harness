from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import unicodedata


_DOMAIN = b"agent-harness/source-content-identity/v1\0"
_FROZEN_DOMAIN = b"agent-harness/frozen-source-snapshot/v1\0"
_CONFIG_SUFFIXES = frozenset(
    {
        ".cfg",
        ".ini",
        ".js",
        ".json",
        ".mjs",
        ".py",
        ".sh",
        ".toml",
        ".ts",
        ".yaml",
        ".yml",
    }
)
_CONFIG_NAMES = frozenset(
    {"dockerfile", "gemfile", "makefile", "package-lock.json", "package.json"}
)


class SourceIdentityError(ValueError):
    pass


def _length_prefix(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def _git(
    repo: Path, *arguments: str, input_bytes: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-c", "core.quotePath=false", *arguments],
            cwd=repo,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
    except OSError as error:
        raise SourceIdentityError(f"Git invocation failed: {error}") from error


def _git_output(repo: Path, *arguments: str) -> bytes:
    result = _git(repo, *arguments)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise SourceIdentityError(message or "Git command failed")
    return result.stdout


@dataclass(frozen=True)
class SourceEntryV1:
    path: bytes
    kind: str
    mode: bytes
    object_id: str
    payload: bytes
    submodule_identity: SourceContentIdentityV1 | None = None

    def encoded(self) -> bytes:
        return b"".join(
            (
                _length_prefix(self.path),
                _length_prefix(self.kind.encode()),
                _length_prefix(self.mode),
                _length_prefix(self.payload),
            )
        )

    def to_document(self) -> dict[str, object]:
        value: dict[str, object] = {
            "path": self.path.decode("utf-8"),
            "kind": self.kind,
            "mode": self.mode.decode("ascii"),
            "object_id": self.object_id,
        }
        if self.kind == "blob":
            value["blob_sha256"] = self.payload.hex()
        elif self.kind == "symlink":
            value["symlink_target"] = self.payload.decode(
                "utf-8", "surrogateescape"
            )
        else:
            value["submodule_identity"] = (
                self.submodule_identity.to_document()
                if self.submodule_identity is not None
                else None
            )
        return value


@dataclass(frozen=True)
class SourceContentIdentityV1:
    algorithm: str
    algorithm_version: int
    inclusion_policy: str
    policy_version: int
    ordered_manifest_digest: str
    source_commit: str
    frozen_snapshot_digest: str
    digest: str
    entries: tuple[SourceEntryV1, ...]

    def to_document(self) -> dict[str, object]:
        return {
            "algorithm": self.algorithm,
            "algorithm_version": self.algorithm_version,
            "inclusion_policy": self.inclusion_policy,
            "policy_version": self.policy_version,
            "ordered_manifest_digest": self.ordered_manifest_digest,
            "source_commit": self.source_commit,
            "frozen_snapshot_digest": self.frozen_snapshot_digest,
            "digest": self.digest,
        }


def _validate_path(path: bytes, seen: dict[str, bytes]) -> str:
    if not path or path.startswith(b"/") or b"\0" in path:
        raise SourceIdentityError("unsupported path")
    components = path.split(b"/")
    if any(component in (b"", b".", b"..") for component in components):
        raise SourceIdentityError("unsupported path component")
    try:
        decoded = path.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceIdentityError("unsupported path encoding") from error
    if os.fsencode(decoded) != path:
        raise SourceIdentityError("unsupported path round trip")
    collision_key = unicodedata.normalize("NFC", decoded).casefold()
    previous = seen.get(collision_key)
    if previous is not None and previous != path:
        raise SourceIdentityError("case or Unicode-normalization collision")
    seen[collision_key] = path
    return decoded


def _tree_records(repo: Path, commit: str) -> list[tuple[bytes, bytes, str, bytes]]:
    output = _git_output(repo, "ls-tree", "-r", "-z", "--full-tree", commit)
    records: list[tuple[bytes, bytes, str, bytes]] = []
    seen: dict[str, bytes] = {}
    for raw in output.split(b"\0"):
        if not raw:
            continue
        try:
            metadata, path = raw.split(b"\t", 1)
            mode, kind, object_id = metadata.split(b" ", 2)
        except ValueError as error:
            raise SourceIdentityError("malformed Git tree entry") from error
        _validate_path(path, seen)
        records.append((mode, kind, object_id.decode("ascii"), path))
    records.sort(key=lambda item: item[3])
    return records


def _untracked_input(repo: Path, path: bytes) -> bool:
    decoded = path.decode("utf-8", "surrogateescape")
    candidate = repo / decoded
    try:
        mode = candidate.lstat().st_mode
    except FileNotFoundError:
        return True
    name = candidate.name.casefold()
    return (
        stat.S_ISLNK(mode)
        or bool(mode & 0o111)
        or candidate.suffix.casefold() in _CONFIG_SUFFIXES
        or name in _CONFIG_NAMES
    )


def _require_clean_checkout(repo: Path) -> None:
    status_output = _git_output(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignore-submodules=none",
    )
    dirty = False
    for record in status_output.split(b"\0"):
        if not record:
            continue
        if record.startswith(b"?? "):
            path = record[3:]
            if _untracked_input(repo, path):
                raise SourceIdentityError(
                    "untracked executable or configuration input"
                )
        else:
            dirty = True
    if dirty:
        raise SourceIdentityError("source index or worktree is dirty")


def _submodule_identity(
    repo: Path,
    path: bytes,
    expected_commit: str,
    *,
    algorithm_version: int,
    inclusion_policy: str,
    policy_version: int,
) -> SourceContentIdentityV1:
    decoded = path.decode("utf-8")
    checkout = repo / decoded
    if not checkout.is_dir() or not (checkout / ".git").exists():
        raise SourceIdentityError(f"uninitialized submodule {decoded}")
    actual_result = _git(checkout, "rev-parse", "HEAD^{commit}")
    if actual_result.returncode:
        raise SourceIdentityError(f"uninitialized submodule {decoded}")
    actual = actual_result.stdout.decode().strip()
    if actual != expected_commit:
        raise SourceIdentityError(f"submodule {decoded} dirty or wrong commit")
    try:
        return compute_source_content_identity(
            checkout,
            algorithm_version=algorithm_version,
            inclusion_policy=inclusion_policy,
            policy_version=policy_version,
        )
    except SourceIdentityError as error:
        raise SourceIdentityError(f"submodule {decoded} dirty: {error}") from error


def compute_source_content_identity(
    repo: Path | str,
    *,
    algorithm_version: int = 1,
    inclusion_policy: str = "git-tracked-clean-tree",
    policy_version: int = 1,
) -> SourceContentIdentityV1:
    if (
        isinstance(algorithm_version, bool)
        or not isinstance(algorithm_version, int)
        or algorithm_version < 1
        or isinstance(policy_version, bool)
        or not isinstance(policy_version, int)
        or policy_version < 1
    ):
        raise SourceIdentityError("algorithm and policy versions must be positive")
    if not isinstance(inclusion_policy, str) or not inclusion_policy:
        raise SourceIdentityError("inclusion policy must be non-empty")

    root = Path(repo)
    commit = _git_output(root, "rev-parse", "HEAD^{commit}").decode().strip()
    records = _tree_records(root, commit)
    entries: list[SourceEntryV1] = []
    for mode, object_kind, object_id, path in records:
        if mode in (b"100644", b"100755") and object_kind == b"blob":
            content = _git_output(root, "cat-file", "blob", object_id)
            entries.append(
                SourceEntryV1(
                    path=path,
                    kind="blob",
                    mode=mode,
                    object_id=object_id,
                    payload=hashlib.sha256(content).digest(),
                )
            )
        elif mode == b"120000" and object_kind == b"blob":
            target = _git_output(root, "cat-file", "blob", object_id)
            if b"\0" in target:
                raise SourceIdentityError("unsupported symlink target")
            entries.append(
                SourceEntryV1(
                    path=path,
                    kind="symlink",
                    mode=mode,
                    object_id=object_id,
                    payload=target,
                )
            )
        elif mode == b"160000" and object_kind == b"commit":
            nested = _submodule_identity(
                root,
                path,
                object_id,
                algorithm_version=algorithm_version,
                inclusion_policy=inclusion_policy,
                policy_version=policy_version,
            )
            payload = _length_prefix(object_id.encode()) + _length_prefix(
                bytes.fromhex(nested.digest)
            )
            entries.append(
                SourceEntryV1(
                    path=path,
                    kind="submodule",
                    mode=mode,
                    object_id=object_id,
                    payload=payload,
                    submodule_identity=nested,
                )
            )
        else:
            raise SourceIdentityError(
                f"unsupported Git path type {mode.decode()} {object_kind.decode()}"
            )

    _require_clean_checkout(root)
    encoded_entries = b"".join(entry.encoded() for entry in entries)
    stream = b"".join(
        (
            _DOMAIN,
            _length_prefix(b"sha256"),
            _length_prefix(str(algorithm_version).encode()),
            _length_prefix(inclusion_policy.encode()),
            _length_prefix(str(policy_version).encode()),
            encoded_entries,
        )
    )
    digest = hashlib.sha256(stream).hexdigest()
    frozen_digest = hashlib.sha256(
        _FROZEN_DOMAIN
        + _length_prefix(commit.encode())
        + _length_prefix(bytes.fromhex(digest))
    ).hexdigest()
    return SourceContentIdentityV1(
        algorithm="sha256",
        algorithm_version=algorithm_version,
        inclusion_policy=inclusion_policy,
        policy_version=policy_version,
        ordered_manifest_digest=hashlib.sha256(encoded_entries).hexdigest(),
        source_commit=commit,
        frozen_snapshot_digest=frozen_digest,
        digest=digest,
        entries=tuple(entries),
    )


def _open_parent_at(root_descriptor: int, components: tuple[str, ...]) -> int:
    current = os.dup(root_descriptor)
    try:
        for component in components:
            try:
                os.mkdir(component, mode=0o755, dir_fd=current)
                os.fsync(current)
            except FileExistsError:
                pass
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            os.close(current)
            current = next_descriptor
        return current
    except OSError as error:
        os.close(current)
        raise SourceIdentityError(
            "materialization refused symlink traversal"
        ) from error


def _materialize_entries(
    repository: Path,
    destination: Path,
    root_descriptor: int,
    identity: SourceContentIdentityV1,
) -> None:
    for entry in identity.entries:
        relative = entry.path.decode("utf-8")
        components = Path(relative).parts
        parent_descriptor = _open_parent_at(
            root_descriptor, tuple(components[:-1])
        )
        leaf = components[-1]
        try:
            if entry.kind == "blob":
                content = _git_output(
                    repository, "cat-file", "blob", entry.object_id
                )
                if hashlib.sha256(content).digest() != entry.payload:
                    raise SourceIdentityError("frozen blob digest mismatch")
                try:
                    descriptor = os.open(
                        leaf,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=parent_descriptor,
                    )
                except OSError as error:
                    raise SourceIdentityError(
                        "materialization target collision or symlink"
                    ) from error
                try:
                    offset = 0
                    while offset < len(content):
                        offset += os.write(descriptor, content[offset:])
                    os.fchmod(
                        descriptor, 0o755 if entry.mode == b"100755" else 0o644
                    )
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            elif entry.kind == "symlink":
                try:
                    os.symlink(
                        entry.payload,
                        os.fsencode(leaf),
                        dir_fd=parent_descriptor,
                    )
                except OSError as error:
                    raise SourceIdentityError(
                        "materialization target collision or symlink"
                    ) from error
            elif entry.kind == "submodule":
                if entry.submodule_identity is None:
                    raise SourceIdentityError("submodule identity missing")
                try:
                    os.mkdir(leaf, mode=0o755, dir_fd=parent_descriptor)
                except OSError as error:
                    raise SourceIdentityError(
                        "materialization submodule target collision"
                    ) from error
                submodule_descriptor = os.open(
                    leaf,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=parent_descriptor,
                )
                try:
                    _materialize_entries(
                        repository / relative,
                        destination / relative,
                        submodule_descriptor,
                        entry.submodule_identity,
                    )
                    os.fsync(submodule_descriptor)
                finally:
                    os.close(submodule_descriptor)
            else:
                raise SourceIdentityError("unsupported materialization entry")
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)


def materialize_source_snapshot(
    repo: Path | str,
    destination: Path | str,
    identity: SourceContentIdentityV1,
) -> Path:
    if not isinstance(identity, SourceContentIdentityV1):
        raise TypeError("SourceContentIdentityV1 required")
    current = compute_source_content_identity(
        repo,
        algorithm_version=identity.algorithm_version,
        inclusion_policy=identity.inclusion_policy,
        policy_version=identity.policy_version,
    )
    if current != identity:
        raise SourceIdentityError("source identity changed before materialization")

    root = Path(destination)
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise SourceIdentityError("materialization destination is not a directory")
    else:
        root.mkdir(mode=0o755)

    repository = Path(repo)
    try:
        root_descriptor = os.open(
            root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError as error:
        raise SourceIdentityError(
            "materialization destination is a symlink"
        ) from error
    try:
        _materialize_entries(repository, root, root_descriptor, identity)
        os.fsync(root_descriptor)
    finally:
        os.close(root_descriptor)
    return root
