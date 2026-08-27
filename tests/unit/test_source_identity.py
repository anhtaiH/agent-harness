from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import time
import unicodedata
import unittest

from harness_core.authorities import SetupBodyV1
from harness_core.contracts import canonical_json_bytes
from harness_core.source_identity import (
    SourceIdentityError,
    compute_source_content_identity,
    materialize_source_snapshot,
)
from tests.unit.support import commit_all, git, init_repo


DOMAIN = b"agent-harness/source-content-identity/v1\0"


def length_prefix(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


def expected_single_file_identity(path: bytes, content: bytes, mode: bytes) -> str:
    payload = hashlib.sha256(content).digest()
    entry = b"".join(
        (
            length_prefix(path),
            length_prefix(b"blob"),
            length_prefix(mode),
            length_prefix(payload),
        )
    )
    stream = (
        DOMAIN
        + length_prefix(b"sha256")
        + length_prefix(b"1")
        + length_prefix(b"git-tracked-clean-tree")
        + length_prefix(b"1")
        + entry
    )
    return hashlib.sha256(stream).hexdigest()


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_stream_is_domain_separated_length_prefixed_and_raw_path_sorted(self):
        repo = init_repo(self.root / "repo", {"z.txt": b"last\n", "a.txt": b"first\n"})
        identity = compute_source_content_identity(repo)
        a_entry = b"".join(
            (
                length_prefix(b"a.txt"),
                length_prefix(b"blob"),
                length_prefix(b"100644"),
                length_prefix(hashlib.sha256(b"first\n").digest()),
            )
        )
        z_entry = b"".join(
            (
                length_prefix(b"z.txt"),
                length_prefix(b"blob"),
                length_prefix(b"100644"),
                length_prefix(hashlib.sha256(b"last\n").digest()),
            )
        )
        stream = (
            DOMAIN
            + length_prefix(b"sha256")
            + length_prefix(b"1")
            + length_prefix(b"git-tracked-clean-tree")
            + length_prefix(b"1")
            + a_entry
            + z_entry
        )
        self.assertEqual(identity.digest, hashlib.sha256(stream).hexdigest())
        self.assertEqual(
            identity.ordered_manifest_digest,
            hashlib.sha256(a_entry + z_entry).hexdigest(),
        )
        self.assertEqual([entry.path for entry in identity.entries], [b"a.txt", b"z.txt"])

    def test_regular_blob_digest_uses_content_not_git_object_id(self):
        repo = init_repo(self.root / "repo", {"tracked.txt": b"tracked\n"})
        identity = compute_source_content_identity(repo)
        self.assertEqual(
            identity.digest,
            expected_single_file_identity(b"tracked.txt", b"tracked\n", b"100644"),
        )

    def test_executable_bit_symlink_target_and_tracked_content_change_identity(self):
        repo = init_repo(
            self.root / "repo",
            {"script": b"#!/bin/sh\nexit 0\n", "target-a": b"a\n"},
        )
        os.symlink("target-a", repo / "link")
        commit_all(repo, "add symlink")
        baseline = compute_source_content_identity(repo).digest

        os.chmod(repo / "script", 0o755)
        commit_all(repo, "executable")
        executable = compute_source_content_identity(repo).digest
        self.assertNotEqual(executable, baseline)

        (repo / "link").unlink()
        os.symlink("target-b", repo / "link")
        commit_all(repo, "symlink target")
        symlink = compute_source_content_identity(repo).digest
        self.assertNotEqual(symlink, executable)

        (repo / "script").write_bytes(b"#!/bin/sh\nexit 1\n")
        commit_all(repo, "content")
        content = compute_source_content_identity(repo).digest
        self.assertNotEqual(content, symlink)

    def test_non_utf8_symlink_target_round_trips_document_plan_and_snapshot(self):
        repo = init_repo(self.root / "repo")
        raw_target = b"target-\xff"
        os.symlink(raw_target, os.fsencode(repo / "raw-link"))
        git(repo, "add", "raw-link")
        git(repo, "commit", "-qm", "add raw symlink")

        identity = compute_source_content_identity(repo)
        document = identity.to_document()
        symlink = next(
            entry
            for entry in document["entries"]
            if entry["kind"] == "symlink"
        )
        self.assertEqual(symlink["symlink_target_encoding"], "base64")
        self.assertEqual(
            base64.b64decode(symlink["symlink_target_base64"], validate=True),
            raw_target,
        )
        body = SetupBodyV1(
            installation_id="12345678-1234-5678-9234-567812345678",
            runtime_root="/var/lib/agent-harness/runtime",
            rollback_root="/var/lib/agent-harness/rollback",
            source_identity=identity,
            adapter_plan_digests=(),
            operations=(),
        )
        canonical_json_bytes(body.to_document())

        destination = self.root / "snapshot"
        materialize_source_snapshot(repo, destination, identity)
        self.assertEqual(
            os.readlink(os.fsencode(destination / "raw-link")), raw_target
        )

    def test_algorithm_or_inclusion_policy_change_alters_identity(self):
        repo = init_repo(self.root / "repo")
        baseline = compute_source_content_identity(repo)
        algorithm = compute_source_content_identity(repo, algorithm_version=2)
        policy_version = compute_source_content_identity(repo, policy_version=2)
        policy_name = compute_source_content_identity(
            repo, inclusion_policy="git-tracked-clean-tree-plus-generated"
        )
        self.assertEqual(
            len({baseline.digest, algorithm.digest, policy_version.digest, policy_name.digest}),
            4,
        )

    def test_timestamps_and_checkout_location_do_not_change_identity(self):
        repo = init_repo(self.root / "repo")
        baseline = compute_source_content_identity(repo)
        time.sleep(0.01)
        os.utime(repo / "tracked.txt", None)
        self.assertEqual(compute_source_content_identity(repo).digest, baseline.digest)

        clone = self.root / "elsewhere"
        git(self.root, "clone", "-q", str(repo), str(clone))
        self.assertEqual(compute_source_content_identity(clone).digest, baseline.digest)

    def test_recursive_submodule_identity_and_commit_are_bound(self):
        child = init_repo(self.root / "child", {"dependency.txt": b"one\n"})
        parent = init_repo(self.root / "parent")
        git(parent, "submodule", "add", "-q", str(child), "vendor/child")
        commit_all(parent, "add submodule")
        baseline = compute_source_content_identity(parent)
        submodule_entry = next(
            entry for entry in baseline.entries if entry.kind == "submodule"
        )
        self.assertEqual(submodule_entry.mode, b"160000")
        self.assertIsNotNone(submodule_entry.submodule_identity)

        (child / "dependency.txt").write_bytes(b"two\n")
        commit_all(child, "dependency change")
        git(parent / "vendor/child", "pull", "-q")
        commit_all(parent, "advance submodule")
        changed = compute_source_content_identity(parent)
        self.assertNotEqual(changed.digest, baseline.digest)

    def test_dirty_index_or_worktree_is_rejected(self):
        for staged in (False, True):
            with self.subTest(staged=staged):
                repo = init_repo(self.root / f"repo-{staged}")
                (repo / "tracked.txt").write_bytes(b"dirty\n")
                if staged:
                    git(repo, "add", "tracked.txt")
                with self.assertRaisesRegex(SourceIdentityError, "dirty"):
                    compute_source_content_identity(repo)

    def test_dirty_or_uninitialized_submodule_is_rejected(self):
        child = init_repo(self.root / "child", {"dependency.txt": b"one\n"})
        parent = init_repo(self.root / "parent")
        git(parent, "submodule", "add", "-q", str(child), "vendor/child")
        commit_all(parent, "add submodule")
        (parent / "vendor/child/dependency.txt").write_bytes(b"dirty\n")
        with self.assertRaisesRegex(SourceIdentityError, "submodule.*dirty"):
            compute_source_content_identity(parent)

        git(parent / "vendor/child", "reset", "--hard", "-q")
        git(parent, "submodule", "deinit", "-f", "--", "vendor/child")
        with self.assertRaisesRegex(SourceIdentityError, "uninitialized submodule"):
            compute_source_content_identity(parent)

    def test_unsupported_non_utf8_path_is_rejected(self):
        repo = init_repo(self.root / "repo")
        object_id = git(repo, "hash-object", "-w", "--stdin", input_bytes=b"bad\n").strip()
        tree = git(
            repo,
            "mktree",
            "-z",
            input_bytes=b"100644 blob " + object_id + b"\tbad-\xff\0",
        ).strip()
        commit = git(repo, "commit-tree", tree.decode(), "-m", "non utf8").strip()
        git(repo, "update-ref", "HEAD", commit.decode())
        with self.assertRaisesRegex(SourceIdentityError, "unsupported path"):
            compute_source_content_identity(repo)

    def test_case_and_unicode_normalization_collisions_are_rejected(self):
        for paths in (
            (b"Config.toml", b"config.toml"),
            (
                unicodedata.normalize("NFC", "cafe\u0301").encode(),
                unicodedata.normalize("NFD", "cafe\u0301").encode(),
            ),
        ):
            with self.subTest(paths=paths):
                repo = init_repo(self.root / f"repo-{len(list(self.root.iterdir()))}")
                object_id = git(repo, "hash-object", "-w", "--stdin", input_bytes=b"x\n").strip()
                tree_input = b"".join(
                    b"100644 blob " + object_id + b"\t" + path + b"\0"
                    for path in sorted(paths)
                )
                tree = git(repo, "mktree", "-z", input_bytes=tree_input).strip()
                commit = git(repo, "commit-tree", tree.decode(), "-m", "collision").strip()
                git(repo, "update-ref", "HEAD", commit.decode())
                with self.assertRaisesRegex(SourceIdentityError, "collision"):
                    compute_source_content_identity(repo)

    def test_untracked_nonignored_executable_or_configuration_is_rejected(self):
        for name, executable in (("local-tool", True), ("local.toml", False)):
            with self.subTest(name=name):
                repo = init_repo(self.root / f"repo-{name.replace('.', '-')}")
                candidate = repo / name
                candidate.write_text("input\n")
                if executable:
                    candidate.chmod(0o755)
                with self.assertRaisesRegex(SourceIdentityError, "untracked.*input"):
                    compute_source_content_identity(repo)

    def test_materialization_uses_only_frozen_tracked_snapshot(self):
        repo = init_repo(
            self.root / "repo",
            {
                ".gitignore": (
                    b"node_modules/\n.superpowers/\nbuild/\ndist/\nevidence/\n"
                ),
                "tracked.txt": b"trusted\n",
            },
        )
        excluded = {
            "node_modules/cache.js": b"cache\n",
            ".superpowers/sdd/goal.json": b"goal\n",
            "evidence/result.json": b"evidence\n",
            "build/output.bin": b"build\n",
            "dist/package.tgz": b"dist\n",
        }
        for relative, content in excluded.items():
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        identity = compute_source_content_identity(repo)
        destination = self.root / "snapshot"
        materialize_source_snapshot(repo, destination, identity)
        self.assertEqual((destination / "tracked.txt").read_bytes(), b"trusted\n")
        for relative in excluded:
            self.assertFalse((destination / relative).exists(), relative)

    def test_materialization_refuses_symlink_traversal_and_changed_identity(self):
        repo = init_repo(self.root / "repo", {"directory/file": b"safe\n"})
        identity = compute_source_content_identity(repo)
        destination = self.root / "snapshot"
        destination.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        os.symlink(outside, destination / "directory")
        with self.assertRaisesRegex(SourceIdentityError, "symlink"):
            materialize_source_snapshot(repo, destination, identity)
        self.assertEqual(list(outside.iterdir()), [])

        shutil.rmtree(destination)
        (repo / "directory/file").write_bytes(b"dirty\n")
        with self.assertRaisesRegex(SourceIdentityError, "dirty"):
            materialize_source_snapshot(repo, destination, identity)


if __name__ == "__main__":
    unittest.main()
