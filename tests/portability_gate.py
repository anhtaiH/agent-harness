#!/usr/bin/env python3
"""Reject machine identity, secrets, unsafe links, and package drift."""

from __future__ import annotations

import argparse
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


HOME_PATTERNS = [
    re.compile(r"/" + r"Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/" + r"home/[A-Za-z0-9._-]+/"),
]
PREFIX_PATTERNS = [re.compile(r"/" + r"opt/homebrew(?:/|\b)")]
SECRET_PATTERNS = [
    re.compile(r"gh" + r"[pousr]_[0-9A-Za-z_]{24,}"),
    re.compile(r"sk-" + r"[0-9A-Za-z]{24,}"),
    re.compile(r"-----BEGIN " + r"(?:RSA |EC |OPENSSH |)?PRIVATE KEY-----"),
]
TEXT_LIMIT = 8 * 1024 * 1024


def scan_bytes(label: str, content: bytes) -> list[str]:
    if len(content) > TEXT_LIMIT or b"\0" in content:
        return []
    text = content.decode("utf-8", errors="replace")
    failures = []
    for pattern in [*HOME_PATTERNS, *PREFIX_PATTERNS, *SECRET_PATTERNS]:
        if pattern.search(text):
            failures.append(f"forbidden content in {label}: {pattern.pattern}")
    return failures


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [root / item.decode() for item in result.stdout.split(b"\0") if item]


def scan_tree(root: Path) -> list[str]:
    failures = []
    for path in tracked_files(root):
        if path.is_symlink():
            failures.append(f"tracked symlink is not allowed: {path.relative_to(root)}")
        elif path.is_file():
            failures.extend(scan_bytes(str(path.relative_to(root)), path.read_bytes()))
    return failures


def package_path_allowed(path: PurePosixPath) -> bool:
    if not path.parts or path.parts[0] != "package":
        return False
    relative = PurePosixPath(*path.parts[1:])
    exact = {"package.json", "package-lock.json", "npm-shrinkwrap.json", "README.md", "INSTALL.md"}
    roots = {"bin", "runtime", "src", "tests"}
    return str(relative) in exact or (relative.parts and relative.parts[0] in roots)


def scan_package(package: Path) -> list[str]:
    failures = []
    with tarfile.open(package, "r:gz") as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                failures.append(f"unsafe package path: {member.name}")
                continue
            if member.issym() or member.islnk():
                failures.append(f"package link is not allowed: {member.name}")
                continue
            if not package_path_allowed(path):
                failures.append(f"unexpected package file: {member.name}")
                continue
            if member.isfile():
                handle = archive.extractfile(member)
                if handle:
                    failures.extend(scan_bytes(member.name, handle.read()))
    return failures


def negative_self_test() -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        injected = root / "injected.txt"
        injected.write_text("/" + "Users" + "/machine-owner/private\n")
        subprocess.run(["git", "-C", str(root), "add", "injected.txt"], check=True)
        if not scan_tree(root):
            return ["negative self-test failed to reject injected home path"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tree", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    failures = []
    if args.tree:
        failures.extend(scan_tree(args.tree.resolve()))
    if args.package:
        failures.extend(scan_package(args.package.resolve()))
    if args.self_test:
        failures.extend(negative_self_test())
    for failure in failures:
        print(failure)
    print(f"portability gate: {'FAIL' if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
