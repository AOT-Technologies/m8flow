#!/usr/bin/env python3
"""Inventory the licenses of m8flow's runtime dependencies.

Writes DEPENDENCIES.md (``--write``) and fails (``--check``) when a runtime
dependency carries a strong-copyleft license that is not compatible with
shipping m8flow under Apache-2.0.

Python projects are installed from their uv lockfile into a throwaway
environment and read from package metadata;
npm projects are read from their installed node_modules with
license-checker-rseidelsohn, so run ``npm ci`` in each npm project first.
Development-only dependencies are excluded: they are not distributed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PYTHON_PROJECTS = [
    "m8flow-backend",
    "m8flow-mcp",
    "m8flow-nats-consumer",
    "m8flow-node-wire-proxy",
]
NPM_PROJECTS = [
    "m8flow-designer",
    "m8flow-bpmn",
]

LICENSE_CHECKER_VERSION = "4.4.2"

# Installers that uv may seed into an environment; not m8flow dependencies.
IGNORED_DISTRIBUTIONS = {"pip", "setuptools", "wheel"}

# Our own packages, built from this repository.
FIRST_PARTY = {
    "m8flow-backend",
    "m8flow-bpmn",
    "m8flow-bpmn-core",
    "m8flow-designer",
    "m8flow-mcp",
    "m8flow-mcp-server",
    "m8flow-nats-consumer",
    "m8flow-node-wire-proxy",
    "m8flow-telemetry",
}

# Packages whose metadata does not name their license precisely, checked by
# hand against the upstream LICENSE file.
LICENSE_OVERRIDES = {
    # https://github.com/dateutil/dateutil/blob/master/LICENSE
    "python-dateutil": "Apache-2.0 OR BSD-3-Clause",
    # https://github.com/mosquito/caio/blob/master/LICENSE
    "caio": "Apache-2.0",
}

SAFE = "Safe"
REVIEW = "Needs review"
RISKY = "Risky"

_SAFE_PATTERNS = [
    r"\bMIT\b",
    r"Apache",
    r"\bBSD\b",
    r"BSD-\d",
    r"\bISC\b",
    r"\bPSFL?\b",
    r"ZPL-2\.1",
    r"Python Software Foundation",
    r"0BSD",
    r"Unlicense",
    r"CC0",
    r"Zlib",
    r"BlueOak",
    r"\bHPND\b",
    r"MPL-2\.0",
    r"Mozilla Public License 2\.0",
    r"CC-BY-4\.0",
    r"Python-2\.0",
    r"OFL",
]
# Strong copyleft: GPL and AGPL, but not LGPL.
_RISKY_PATTERN = re.compile(r"(?<![L])(A?GPL|General Public License)(?!.*Lesser)", re.IGNORECASE)
_LGPL_PATTERN = re.compile(r"LGPL|Lesser General Public", re.IGNORECASE)


@dataclass(frozen=True)
class Dependency:
    project: str
    name: str
    version: str
    license: str
    url: str


def classify(license_text: str) -> str:
    text = license_text.strip()
    if not text or text.upper() == "UNKNOWN":
        return REVIEW
    if text.endswith("*"):
        # license-checker marks a license it guessed from a file with "*".
        return REVIEW
    if _LGPL_PATTERN.search(text):
        # LGPL libraries used unmodified as separate packages are compatible,
        # but the obligation (relinkable, unmodified) must be checked per use.
        return REVIEW
    if _RISKY_PATTERN.search(text):
        # Dual-licensed packages ("MIT OR GPL-2.0") let us choose the permissive one.
        if re.search(r"\bOR\b", text) and any(re.search(p, text) for p in _SAFE_PATTERNS):
            return SAFE
        return RISKY
    if any(re.search(p, text) for p in _SAFE_PATTERNS):
        return SAFE
    return REVIEW


def _run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        sys.stderr.write(f"Command failed in {cwd}: {' '.join(cmd)}\n{result.stderr}\n")
        raise SystemExit(result.returncode)
    return result.stdout


# Runs inside the project's environment and prints one JSON row per installed
# distribution. PEP 639 License-Expression wins over the free-text License
# field, which wins over trove classifiers.
_METADATA_SCRIPT = r"""
import json
from importlib.metadata import distributions

rows = []
for dist in distributions():
    meta = dist.metadata
    license_text = meta.get("License-Expression") or ""
    if not license_text:
        free_text = (meta.get("License") or "").strip()
        if free_text and len(free_text) <= 80 and "\n" not in free_text:
            license_text = free_text
    if not license_text:
        classifiers = [
            c.split(" :: ")[-1]
            for c in (meta.get_all("Classifier") or [])
            if c.startswith("License :: ") and c != "License :: OSI Approved"
        ]
        license_text = " OR ".join(classifiers)
    url = meta.get("Home-page") or ""
    if not url:
        for entry in meta.get_all("Project-URL") or []:
            label, _, link = entry.partition(",")
            if label.strip().lower() in {"homepage", "source", "repository", "source code"}:
                url = link.strip()
                break
    rows.append({"name": meta["Name"], "version": dist.version, "license": license_text, "url": url})
print(json.dumps(rows))
"""


def python_dependencies(project: str) -> list[Dependency]:
    # A throwaway environment with runtime dependencies only. `uv run` syncs
    # inexactly, so reusing the developer's .venv would also report dev tools.
    with tempfile.TemporaryDirectory(prefix="m8flow-licenses-") as venv:
        env = {**os.environ, "UV_PROJECT_ENVIRONMENT": venv}
        result = subprocess.run(  # noqa: S603
            ["uv", "run", "--frozen", "--no-dev", "--quiet", "python", "-c", _METADATA_SCRIPT],
            cwd=REPO_ROOT / project,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        sys.stderr.write(f"Could not read {project}'s dependencies:\n{result.stderr}\n")
        raise SystemExit(result.returncode)
    deps = []
    for row in json.loads(result.stdout.strip().splitlines()[-1]):
        name = row["name"]
        if name.lower() in IGNORED_DISTRIBUTIONS or name.lower() in FIRST_PARTY:
            continue
        license_text = LICENSE_OVERRIDES.get(name.lower(), row["license"])
        deps.append(Dependency(project, name, row["version"], license_text, row["url"]))
    return deps


def npm_dependencies(project: str) -> list[Dependency]:
    project_dir = REPO_ROOT / project
    if not (project_dir / "node_modules").is_dir():
        sys.stderr.write(f"{project}/node_modules is missing; run `npm ci --ignore-scripts` there first.\n")
        raise SystemExit(1)
    out = _run(
        [
            "npx",
            "--yes",
            f"license-checker-rseidelsohn@{LICENSE_CHECKER_VERSION}",
            "--production",
            "--json",
            "--excludePrivatePackages",
        ],
        project_dir,
    )
    deps = []
    for key, info in json.loads(out).items():
        name, _, version = key.rpartition("@")
        if name in FIRST_PARTY:
            continue
        licenses = info.get("licenses", "")
        if isinstance(licenses, list):
            licenses = " OR ".join(licenses)
        deps.append(Dependency(project, name, version, licenses, info.get("repository", "")))
    return deps


def render(deps: list[Dependency]) -> str:
    lines = [
        "# m8flow third-party dependencies",
        "",
        "This file is generated by `bin/compliance/dependency_licenses.py --write`. Don't edit it by hand.",
        "It lists the runtime dependencies of each shipped component; development-only tools are not",
        "distributed and are not listed.",
        "",
        "## License classification",
        "",
        "* **Safe (permissive):** MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0, and similar. Compatible with",
        "  shipping m8flow under Apache-2.0.",
        "* **Needs review:** LGPL, custom, or unrecognized licenses. A maintainer or Legal confirms the",
        "  obligations are met (for LGPL: the library is unmodified and installed as a separate package).",
        "* **Risky (strong copyleft):** GPL and AGPL. Not allowed in runtime dependencies; CI fails.",
        "",
    ]
    counts = {SAFE: 0, REVIEW: 0, RISKY: 0}
    for dep in deps:
        counts[classify(dep.license)] += 1
    lines += [
        "## Summary",
        "",
        "| Classification | Count |",
        "|---|---|",
        *(f"| {k} | {v} |" for k, v in counts.items()),
        "",
    ]
    review = [d for d in deps if classify(d.license) != SAFE]
    if review:
        lines += [
            "## Needs attention",
            "",
            "| Component | Package | Version | License | Classification |",
            "|---|---|---|---|---|",
            *(
                f"| {d.project} | {d.name} | {d.version} | {d.license or 'UNKNOWN'} | {classify(d.license)} |"
                for d in review
            ),
            "",
        ]
    for project in sorted({d.project for d in deps}):
        lines += [
            f"## {project}",
            "",
            "| Package | Version | License | Classification |",
            "|---|---|---|---|",
        ]
        for d in sorted((d for d in deps if d.project == project), key=lambda d: d.name.lower()):
            name = f"[{d.name}]({d.url})" if d.url.startswith("http") else d.name
            license_text = (d.license or "UNKNOWN").replace("|", "/")
            lines.append(f"| {name} | {d.version} | {license_text} | {classify(d.license)} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="write DEPENDENCIES.md")
    parser.add_argument("--check", action="store_true", help="fail on strong-copyleft runtime dependencies")
    parser.add_argument("--python", nargs="*", default=PYTHON_PROJECTS, help="uv projects to inventory")
    parser.add_argument("--npm", nargs="*", default=NPM_PROJECTS, help="npm projects to inventory")
    args = parser.parse_args()
    if not (args.write or args.check):
        parser.error("pass --write, --check, or both")

    deps: list[Dependency] = []
    for project in args.python:
        deps += python_dependencies(project)
    for project in args.npm:
        deps += npm_dependencies(project)

    if args.write:
        (REPO_ROOT / "DEPENDENCIES.md").write_text(render(deps), encoding="utf-8")
        print(f"Wrote DEPENDENCIES.md ({len(deps)} dependencies)")

    risky = [d for d in deps if classify(d.license) == RISKY]
    review = [d for d in deps if classify(d.license) == REVIEW]
    for d in review:
        print(f"::warning title=License review::{d.project}: {d.name} {d.version} is '{d.license or 'UNKNOWN'}'")
    for d in risky:
        print(f"::error title=Copyleft dependency::{d.project}: {d.name} {d.version} is '{d.license}'")
    if args.check and risky:
        print(f"{len(risky)} runtime dependencies have a strong-copyleft license.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
