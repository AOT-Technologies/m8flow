#!/usr/bin/env python3
"""Reject local wheel paths in production dependency manifests."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_DEPENDENCY_MANIFEST_NAMES = {"pyproject.toml", "uv.lock", "poetry.lock", "Pipfile", "Pipfile.lock"}
_SKIP_DIRECTORIES = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}
_LOCAL_WHEEL_REFERENCE = re.compile(
    r"(?:\bpath\s*=\s*['\"](?P<path>[^'\"]+\.whl)['\"]|\bfile://[^\s'\"<>]+\.whl)",
    re.IGNORECASE,
)


def _is_dependency_manifest(path: Path) -> bool:
    return path.name in _DEPENDENCY_MANIFEST_NAMES or (
        path.name.startswith("requirements") and path.suffix.lower() == ".txt"
    )


def _is_approved_node_wire_wheel(root: Path, manifest: Path, match: re.Match) -> bool:
    wheel_path = match.group("path")
    if not wheel_path or manifest.relative_to(root).parts[:1] != ("m8flow-node-wire-proxy",):
        return False
    normalized = wheel_path.replace("\\", "/").removeprefix("./")
    if not normalized.startswith("vendor/wheels/"):
        return False
    candidate = (manifest.parent / wheel_path).resolve()
    try:
        candidate.relative_to((manifest.parent / "vendor" / "wheels").resolve())
    except ValueError:
        return False
    return candidate.is_file()


def find_local_wheel_sources(root: Path) -> list[tuple[Path, int, str]]:
    """Return wheel-path references found in production dependency manifests."""
    findings = []
    for directory, child_directories, filenames in os.walk(root):
        child_directories[:] = [name for name in child_directories if name not in _SKIP_DIRECTORIES]
        for filename in filenames:
            manifest = Path(directory) / filename
            if not _is_dependency_manifest(manifest):
                continue
            try:
                lines = manifest.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                continue
            for line_number, line in enumerate(lines, start=1):
                match = _LOCAL_WHEEL_REFERENCE.search(line)
                if match and not _is_approved_node_wire_wheel(root, manifest, match):
                    findings.append((manifest.relative_to(root), line_number, line.strip()))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root to scan (defaults to this script's repository)",
    )
    args = parser.parse_args()
    findings = find_local_wheel_sources(args.root.resolve())
    if not findings:
        print("No local wheel sources found in production dependency manifests.")
        return 0

    print("::error::Local wheel paths are not allowed in production dependency manifests:")
    for manifest, line_number, line in findings:
        print(f"  {manifest}:{line_number}: {line}")
    print("Publish the wheel to the package registry and pin its version before merging to main.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
