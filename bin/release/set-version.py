#!/usr/bin/env python3
"""Set the version of every m8flow component to one release version.

Usage:
  bin/release/set-version.py 2.0.0     # write the version everywhere
  bin/release/set-version.py --check 2.0.0  # fail if any component differs

Updates each component's pyproject.toml, package.json, setup.py, and the
component's own entries in uv.lock and package-lock.json, so the lockfiles stay
in step without a re-lock. The GitHub Release workflow runs --check against
the release tag.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PYPROJECTS = [
    "m8flow-backend/pyproject.toml",
    "m8flow-mcp/pyproject.toml",
    "m8flow-nats-consumer/pyproject.toml",
    "m8flow-node-wire-proxy/pyproject.toml",
    "m8flow-telemetry/pyproject.toml",
]
SETUP_PYS = ["m8flow-mcp/setup.py"]
UV_LOCKS = [
    "m8flow-backend/uv.lock",
    "m8flow-mcp/uv.lock",
    "m8flow-nats-consumer/uv.lock",
    "m8flow-node-wire-proxy/uv.lock",
]
PACKAGE_JSONS = ["m8flow-designer/package.json", "m8flow-bpmn/package.json"]
PACKAGE_LOCKS = ["m8flow-designer/package-lock.json", "m8flow-bpmn/package-lock.json"]

# Package names built from this repository; their lockfile entries follow the
# release version. Third-party packages are never touched.
FIRST_PARTY = {
    "m8flow-backend",
    "m8flow-mcp",
    "m8flow-nats-consumer",
    "m8flow-node-wire-proxy",
    "m8flow-telemetry",
    "m8flow-designer",
    "m8flow-bpmn",
}

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _pyproject(text: str, version: str) -> tuple[str, list[str]]:
    found = re.findall(r'(?m)^version = "([^"]+)"', text)
    return re.sub(r'(?m)^version = "[^"]+"', f'version = "{version}"', text, count=1), found[:1]


def _setup_py(text: str, version: str) -> tuple[str, list[str]]:
    found = re.findall(r'version="([^"]+)"', text)
    return re.sub(r'version="[^"]+"', f'version="{version}"', text, count=1), found[:1]


def _uv_lock(text: str, version: str) -> tuple[str, list[str]]:
    names = "|".join(re.escape(n) for n in FIRST_PARTY)
    pattern = re.compile(rf'(?m)^(name = "(?:{names})"\r?\nversion = ")([^"]+)(")')
    found = [m.group(2) for m in pattern.finditer(text)]
    return pattern.sub(rf"\g<1>{version}\g<3>", text), found


def _package_json(text: str, version: str) -> tuple[str, list[str]]:
    # Replace in place: re-serializing would reflow hand-formatted JSON.
    found = [json.loads(text)["version"]]
    return re.sub(r'(?m)^(  "version": ")[^"]+(")', rf"\g<1>{version}\g<2>", text, count=1), found


def _package_lock(text: str, version: str) -> tuple[str, list[str]]:
    data = json.loads(text)
    found = []
    if data.get("name") in FIRST_PARTY:
        found.append(data["version"])
        data["version"] = version
    for key, entry in data.get("packages", {}).items():
        # A local file: dependency (key "../m8flow-bpmn") carries a version but
        # no name, so name it by its path. Never by a node_modules path: that is
        # a registry package, which may share a first-party name.
        name = entry.get("name")
        if name is None and key and "node_modules" not in key.split("/"):
            name = key.rsplit("/", 1)[-1]
        if name in FIRST_PARTY and "version" in entry:
            found.append(entry["version"])
            entry["version"] = version
    root = data.get("packages", {}).get("")
    if root is not None and "version" in root and root.get("name") is None:
        found.append(root["version"])
        root["version"] = version
    newline = "\r\n" if "\r\n" in text else "\n"
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").replace("\n", newline), found


EDITORS = (
    [(p, _pyproject) for p in PYPROJECTS]
    + [(p, _setup_py) for p in SETUP_PYS]
    + [(p, _uv_lock) for p in UV_LOCKS]
    + [(p, _package_json) for p in PACKAGE_JSONS]
    + [(p, _package_lock) for p in PACKAGE_LOCKS]
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="release version, X.Y.Z")
    parser.add_argument("--check", action="store_true", help="only check; change nothing")
    args = parser.parse_args()
    if not VERSION_RE.match(args.version):
        parser.error(f"{args.version!r} is not an X.Y.Z version")

    mismatches = []
    for relative, edit in EDITORS:
        path = REPO_ROOT / relative
        # newline="" keeps each file's own line endings (some use CRLF).
        with path.open(encoding="utf-8", newline="") as handle:
            original = handle.read()
        updated, found = edit(original, args.version)
        if not found:
            mismatches.append(f"{relative}: no version field found")
            continue
        wrong = sorted({v for v in found if v != args.version})
        if args.check:
            if wrong:
                mismatches.append(f"{relative}: {', '.join(wrong)} (expected {args.version})")
        elif updated != original:
            with path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(updated)
            print(f"{relative}: {', '.join(wrong)} -> {args.version}")

    if mismatches:
        print("Component versions don't match the release:", file=sys.stderr)
        for line in mismatches:
            print(f"  {line}", file=sys.stderr)
        return 1
    if args.check:
        print(f"Every component is at {args.version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
