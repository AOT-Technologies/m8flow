#!/usr/bin/env python3
"""Detect verbatim copying of gitignored LGPL upstream (spiff-arena) source into
the Apache-2.0-licensed m8flow trees.

This is a licensing-boundary guard, not a general code-quality linter. It answers
one question per file: "is this Apache-tracked file a copy of a gitignored upstream
file?" Upstream trees (spiffworkflow-backend/, spiffworkflow-frontend/,
spiff-arena-common/) must already be present locally (fetched by
bin/fetch-upstream.sh; they are gitignored).

Detection is layered because a single similarity percentage is not enough:

  A  whole-file line similarity (difflib.SequenceMatcher over code lines)
  B  longest run of contiguous identical code lines (partial lifts under the ratio)
  Ct CONTAINMENT — fraction of THIS file's code lines found in the upstream file.
     Asymmetric, so a small file that copies a chunk of a much larger upstream file
     (e.g. one module split out of a big upstream component, or a thin *_patch.py
     that lifts part of an upstream controller) is caught even when the symmetric
     ratio is diluted by the upstream file's size.
  C1 marker scan: LGPL/GPL header text and unambiguous upstream attribution
     (author handles, sartography URLs). ALWAYS fails — never grandfathered.
  C2 verbatim distinctive-comment match against the upstream counterpart.

Comparison is on "code lines" (blank lines stripped) so reindentation and blank-line
changes do not hide a copy. File coverage spans code AND the config/template/diagram
/shell files that are copied wholesale (.json, .yml, .toml, .ini, .ftl, .mako,
.bpmn, .dmn, .sh, ...).

Counterpart resolution: (1) path convention, (2) basename search, (3) a
content-addressed search across the whole upstream tree for copies pasted into
differently-named files.

A checked-in baseline (bin/upstream-copy-baseline.json) grandfathers the copying
that already exists so the gate blocks *new* copying and *regressions* without
demanding an immediate mass rewrite. Files drop out of the baseline as they are
remediated. Layer C1 markers are never grandfathered.

Usage:
  # Regenerate the baseline from the current working tree (after fetch-upstream):
  bin/check-upstream-copying.py --all --write-baseline bin/upstream-copy-baseline.json

  # Full-tree report without failing:
  bin/check-upstream-copying.py --all

  # PR gate: only files changed vs a base ref:
  bin/check-upstream-copying.py --diff origin/main

Exit code is non-zero on a violation, unless --report-only is passed.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Apache-2.0-tracked roots that this guard scans.
APACHE_ROOTS = [
    "m8flow-backend",
    "m8flow-frontend",
    "extensions",
    "keycloak-extensions",
    "m8flow-connector-proxy",
    "m8flow-mcp",
    "m8flow-nats-consumer",
    "m8flow-telemetry",
]

# Apache path prefix -> upstream path prefix, most specific first (resolution stops
# at the first prefix that matches). The src prefixes must precede the bare-tree
# prefixes because the package directory is renamed (m8flow_backend ->
# spiffworkflow_backend), unlike keycloak/, migrations/, public/, etc.
PATH_CONVENTION = [
    ("m8flow-backend/src/m8flow_backend/", "spiffworkflow-backend/src/spiffworkflow_backend/"),
    ("m8flow-frontend/src/", "spiffworkflow-frontend/src/"),
    ("m8flow-frontend/public/", "spiffworkflow-frontend/public/"),
    ("m8flow-frontend/", "spiffworkflow-frontend/"),
    ("extensions/m8flow-frontend/", "spiffworkflow-frontend/"),
    ("m8flow-connector-proxy/", "connector-proxy-demo/"),
    ("m8flow-backend/", "spiffworkflow-backend/"),
]

# Whole upstream trees searched for basename / content-addressed fallback. Trees
# that the default `bin/fetch-upstream.sh` does not pull (connector-proxy-demo,
# connector-proxies) are listed so they are compared *when present*, without
# changing the default pull — a missing tree is simply skipped.
UPSTREAM_SEARCH_ROOTS = [
    "spiffworkflow-backend",
    "spiffworkflow-frontend",
    "spiff-arena-common",
    "connector-proxy-demo",
    "connector-proxies",
]

# Files that get copied wholesale, not just code. Comment extraction (C2) only runs
# on CODE_SUFFIXES, since comment syntax is language specific and "//" inside a JSON
# string is not a comment.
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
TEXT_SUFFIXES = CODE_SUFFIXES | {
    ".sh", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg",
    ".ftl", ".mako", ".bpmn", ".dmn", ".xml", ".sql", ".css", ".scss",
}

SKIP_DIR_PARTS = {
    "node_modules",
    "__pycache__",
    ".venv",
    "dist",
    "build",
    "coverage",
    "__snapshots__",
    ".git",
}

# Auto-generated Alembic version files are m8flow-authored schema changes that all
# share the same boilerplate (imports, revision headers, upgrade/downgrade); a
# cross-tree similarity match there is boilerplate coincidence, not copying. The
# migration *template* (script.py.mako) and alembic.ini are still scanned.
SKIP_PATH_SUBSTRINGS = ("/migrations/versions/",)

# Generated dependency manifests: not copied source, full of registry/git URLs.
SKIP_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "uv.lock", "Pipfile.lock",
}


def _skip_path(rel: str) -> bool:
    if Path(rel).name in SKIP_FILENAMES:
        return True
    return any(s in ("/" + rel) for s in SKIP_PATH_SUBSTRINGS)

# Layer C1 — unambiguous copy evidence. These ALWAYS fail and are never
# grandfathered. Kept deliberately conservative: "SpiffWorkflow" alone is NOT a
# marker (the framework is referenced legitimately all over m8flow). Extend with
# care — a marker must be something that should never appear in m8flow-owned code.
# License-text markers apply to ALL files — a GPL/LGPL header is a copy signal
# anywhere it appears.
LICENSE_MARKERS = [
    (r"GNU\s+Lesser\s+General\s+Public\s+License", "LGPL license header text"),
    (r"GNU\s+General\s+Public\s+License", "GPL license header text"),
    (r"This\s+program\s+is\s+free\s+software", "GPL/LGPL header boilerplate"),
    (r"Free\s+Software\s+Foundation", "FSF license reference"),
]
# Attribution markers apply to CODE files only. In a dependency manifest a
# `sartography/` reference is a legitimate package/git dependency, not copy evidence;
# in source code an upstream author handle or repo URL is.
ATTRIBUTION_MARKERS = [
    (r"\bjasquat\b", "upstream author handle (jasquat)"),
    (r"\bburnettk\b", "upstream author handle (burnettk)"),
    (r"sartography/", "upstream repo URL or import path (sartography/...)"),
]
COMPILED_LICENSE_MARKERS = [(re.compile(p, re.IGNORECASE), why) for p, why in LICENSE_MARKERS]
COMPILED_ATTRIBUTION_MARKERS = [(re.compile(p, re.IGNORECASE), why) for p, why in ATTRIBUTION_MARKERS]

# Comments too generic to be copy evidence for Layer C2.
COMMENT_NOISE = re.compile(
    r"noqa|type:\s*ignore|pylint|eslint-disable|@ts-|prettier-ignore|pragma|"
    r"flake8|mypy|coding[:=]|!/usr/bin",
    re.IGNORECASE,
)
MIN_DISTINCTIVE_COMMENT_LEN = 40

DEFAULT_THRESHOLD = 0.50
DEFAULT_BLOCK_LINES = 40
# Containment (fraction of THIS file found upstream) is set low so thin `*_patch.py`
# wrappers and small partial overrides are also captured, not just wholesale copies.
# The baseline grandfathers everything that exists today, so this tracks partial
# copies for regression without an immediate rewrite; the cost is that a genuinely
# new file sharing >=25% of its lines with an upstream file will trip the gate and
# need review (regenerate the baseline if it is a legitimate new partial).
DEFAULT_CONTAINMENT = 0.25
# Small drift so trivial edits to an already-flagged file are not treated as
# regressions; a real re-copy moves the numbers well past this.
RATIO_DRIFT = 0.02
CONTAINMENT_DRIFT = 0.02
BLOCK_DRIFT = 5

# Content-addressed fallback: used only when path/basename resolution finds no
# counterpart, so a copy pasted into a brand-new, differently-named file is still
# caught. Deliberately conservative to keep false positives off genuinely original
# files (see content_fallback).
FALLBACK_MIN_LINES = 15         # skip tiny files (coincidental matches / noise)
FALLBACK_MIN_SHARED = 10        # a candidate must share at least this many lines
FALLBACK_TOP_K = 5              # confirm at most this many candidates precisely
FALLBACK_COMMON_LINE_CAP = 100  # ignore ultra-common lines when ranking candidates
MEANINGFUL_LINE_MINLEN = 12     # only index/compare substantive lines


@dataclass
class FileResult:
    apache_path: str
    upstream_path: str | None
    ratio: float = 0.0
    containment: float = 0.0
    longest_block: int = 0
    comment_matches: int = 0
    markers: list[str] = field(default_factory=list)

    def signals(self) -> bool:
        """True if this file shows any copy signal worth recording/gating."""
        return (
            bool(self.markers)
            or self.ratio > 0
            or self.containment > 0
            or self.longest_block > 0
            or self.comment_matches > 0
        )


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def code_lines(lines: list[str]) -> list[str]:
    """Non-blank lines, whitespace-normalized — the unit of comparison. Stripping
    blank lines makes reindentation/blank-line churn not hide a copy."""
    return [s for ln in lines if (s := ln.strip())]


def compare_code(a_code: list[str], b_code: list[str]) -> tuple[float, float, int]:
    """Return (symmetric ratio, containment of a in b, longest contiguous block)."""
    sm = difflib.SequenceMatcher(None, a_code, b_code, autojunk=False)
    blocks = sm.get_matching_blocks()
    matched = sum(b.size for b in blocks)
    longest = max((b.size for b in blocks), default=0)
    ratio = sm.ratio()
    containment = matched / len(a_code) if a_code else 0.0
    return ratio, containment, longest


def iter_tree_files(root_path: Path, suffixes: set[str]):
    """Yield files under root_path with a matching suffix, pruning SKIP_DIR_PARTS
    (so huge trees like node_modules are never traversed)."""
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_PARTS]
        for fn in filenames:
            if Path(fn).suffix not in suffixes:
                continue
            path = Path(dirpath) / fn
            if _skip_path(str(path.relative_to(REPO_ROOT))):
                continue
            yield path


def extract_comments(lines: list[str], suffix: str) -> set[str]:
    """Return the set of distinctive comment texts in a code file (Layer C2 input)."""
    if suffix not in CODE_SUFFIXES:
        return set()
    out: set[str] = set()
    for raw in lines:
        text: str | None = None
        stripped = raw.strip()
        if suffix == ".py":
            idx = raw.find("#")
            if idx != -1:
                text = raw[idx + 1 :].strip()
        else:  # ts/tsx/js/jsx
            if "//" in raw:
                text = raw.split("//", 1)[1].strip()
            elif stripped.startswith("*") or stripped.startswith("/*"):
                text = stripped.lstrip("/*").strip()
        if not text:
            continue
        if len(text) < MIN_DISTINCTIVE_COMMENT_LEN:
            continue
        if COMMENT_NOISE.search(text):
            continue
        out.add(text)
    return out


def _line_hash(s: str) -> int:
    """Stable content hash for line-index keys (not Python's process-randomized hash())."""
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


def _meaningful_hashes(lines: list[str]) -> list[int]:
    """Hashes of substantive lines only, used for the content-addressed index.
    Short/boilerplate lines are skipped so the index stays discriminating."""
    return [_line_hash(s) for ln in lines if len(s := ln.strip()) >= MEANINGFUL_LINE_MINLEN]


# Lazily built once per process — only when a basename/content fallback is needed.
_UPSTREAM_INDEX: tuple[dict[int, list[str]], dict[str, list[str]]] | None = None


def get_upstream_index() -> tuple[dict[int, list[str]], dict[str, list[str]]]:
    """Return (line-hash -> upstream files, basename -> upstream files)."""
    global _UPSTREAM_INDEX
    if _UPSTREAM_INDEX is not None:
        return _UPSTREAM_INDEX
    line_index: dict[int, list[str]] = {}
    base_index: dict[str, list[str]] = {}
    for root in UPSTREAM_SEARCH_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.is_dir():
            continue
        for path in iter_tree_files(root_path, TEXT_SUFFIXES):
            rel = str(path.relative_to(REPO_ROOT))
            base_index.setdefault(path.name, []).append(rel)
            for h in set(_meaningful_hashes(_read_lines(path))):
                line_index.setdefault(h, []).append(rel)
    _UPSTREAM_INDEX = (line_index, base_index)
    return _UPSTREAM_INDEX


def _accepts(ratio: float, containment: float, block: int, thr: float, ct: float, blk: int) -> bool:
    return ratio >= thr or containment >= ct or block >= blk


def content_fallback(a_lines: list[str], thr: float, ct: float, blk: int) -> Path | None:
    """Best content match against the whole upstream tree, ignoring filename.

    Catches a copy pasted into a differently-named file with no path/basename
    counterpart (including one module split out of a larger upstream file — caught
    via containment). Conservative: uses an inverted line-hash index to shortlist
    candidates, confirms with precise metrics, and only returns a counterpart that
    already clears a bar, so genuinely original files are not falsely attributed."""
    a_hashes = set(_meaningful_hashes(a_lines))
    if len(a_hashes) < FALLBACK_MIN_LINES:
        return None
    a_code = code_lines(a_lines)

    line_index, _ = get_upstream_index()
    shared: dict[str, int] = {}
    for h in a_hashes:
        posting = line_index.get(h)
        if not posting or len(posting) > FALLBACK_COMMON_LINE_CAP:
            continue  # unknown, or an ultra-common line that is not discriminating
        for rel in posting:
            shared[rel] = shared.get(rel, 0) + 1

    candidates = sorted(
        (rel for rel, n in shared.items() if n >= FALLBACK_MIN_SHARED),
        key=lambda rel: shared[rel],
        reverse=True,
    )[:FALLBACK_TOP_K]

    best: Path | None = None
    best_score = (0.0, 0.0, 0)  # (containment, ratio, block)
    for rel in candidates:
        cand = REPO_ROOT / rel
        ratio, containment, block = compare_code(a_code, code_lines(_read_lines(cand)))
        score = (containment, ratio, block)
        if score > best_score:
            best_score, best = score, cand

    if best is not None and _accepts(best_score[1], best_score[0], best_score[2], thr, ct, blk):
        return best
    return None


def resolve_upstream(apache_path: str, thr: float, ct: float, blk: int) -> Path | None:
    """Map an Apache-tracked path to its upstream counterpart via path convention,
    then a basename search for renamed files, then a content-addressed search."""
    for a_prefix, u_prefix in PATH_CONVENTION:
        if apache_path.startswith(a_prefix):
            direct = REPO_ROOT / (u_prefix + apache_path[len(a_prefix) :])
            if direct.is_file():
                return direct
            break  # convention matched but file missing -> fall through to search

    a_lines = _read_lines(REPO_ROOT / apache_path)
    if not a_lines:
        return None
    a_code = code_lines(a_lines)

    _, base_index = get_upstream_index()
    best: Path | None = None
    best_score = (0.0, 0.0, 0)  # (containment, ratio, block)
    for rel in base_index.get(Path(apache_path).name, []):
        ratio, containment, block = compare_code(a_code, code_lines(_read_lines(REPO_ROOT / rel)))
        score = (containment, ratio, block)
        if score > best_score:
            best_score, best = score, REPO_ROOT / rel
    # Only accept a basename hit that clears a real copy bar — a shared name like
    # conftest.py / __init__.py / main.py must not block content fallback or pin an
    # unrelated upstream file as the counterpart.
    if best is not None and _accepts(best_score[1], best_score[0], best_score[2], thr, ct, blk):
        return best

    # No strong path/basename counterpart -> search by content across the upstream tree.
    return content_fallback(a_lines, thr, ct, blk)


def analyze(apache_path: str, thr: float, ct: float, blk: int) -> FileResult:
    a_path = REPO_ROOT / apache_path
    a_lines = _read_lines(a_path)
    result = FileResult(apache_path=apache_path, upstream_path=None)

    # Layer C1 markers run on every Apache-tracked file, counterpart or not.
    # License-text markers apply to all files; attribution markers to code only.
    blob = "\n".join(a_lines)
    markers = COMPILED_LICENSE_MARKERS + (
        COMPILED_ATTRIBUTION_MARKERS if a_path.suffix in CODE_SUFFIXES else []
    )
    for pattern, why in markers:
        if pattern.search(blob):
            result.markers.append(why)

    a_code = code_lines(a_lines)
    if not a_code:  # empty / whitespace-only file is not a copy
        return result

    upstream = resolve_upstream(apache_path, thr, ct, blk)
    if upstream is None:
        return result
    result.upstream_path = str(upstream.relative_to(REPO_ROOT))
    b_lines = _read_lines(upstream)

    ratio, containment, longest = compare_code(a_code, code_lines(b_lines))
    result.ratio = round(ratio, 4)
    result.containment = round(containment, 4)
    result.longest_block = longest

    a_comments = extract_comments(a_lines, a_path.suffix)
    if a_comments:
        result.comment_matches = len(a_comments & extract_comments(b_lines, upstream.suffix))

    return result


def iter_source_files() -> list[str]:
    files: list[str] = []
    for root in APACHE_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.is_dir():
            continue
        for path in iter_tree_files(root_path, TEXT_SUFFIXES):
            files.append(str(path.relative_to(REPO_ROOT)))
    return sorted(files)


def changed_files(base_ref: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", "--diff-filter=d", f"{base_ref}...HEAD"],
            cwd=REPO_ROOT,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        print(f"error: git diff failed: {exc}", file=sys.stderr)
        sys.exit(2)
    roots = tuple(r + "/" for r in APACHE_ROOTS)
    return sorted(
        f
        for f in out.splitlines()
        if f.startswith(roots)
        and Path(f).suffix in TEXT_SUFFIXES
        and not _skip_path(f)
        and (REPO_ROOT / f).is_file()
    )


def load_baseline(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("files", {})


def _flagged(r: FileResult, thr: float, ct: float, blk: int) -> bool:
    return r.ratio >= thr or r.containment >= ct or r.longest_block >= blk or r.comment_matches > 0


def build_baseline(results: list[FileResult], thr: float, ct: float, blk: int) -> dict:
    files = {}
    for r in results:
        if _flagged(r, thr, ct, blk):
            files[r.apache_path] = {
                "upstream": r.upstream_path,
                "ratio": r.ratio,
                "containment": r.containment,
                "longest_block": r.longest_block,
                "comment_matches": r.comment_matches,
            }
    return {
        "_comment": (
            "Grandfathered upstream-copy signals. The gate blocks NEW copying and "
            "REGRESSIONS beyond these values; files drop out as they are remediated. "
            "Regenerate with: bin/check-upstream-copying.py --all --write-baseline "
            "bin/upstream-copy-baseline.json"
        ),
        "threshold": thr,
        "containment": ct,
        "block_lines": blk,
        "files": dict(sorted(files.items())),
    }


def evaluate(r: FileResult, baseline: dict[str, dict], thr: float, ct: float, blk: int) -> list[str]:
    """Return a list of violation messages for one file ([] if clean)."""
    violations: list[str] = []

    # C1 markers: always fatal, never grandfathered.
    for m in r.markers:
        violations.append(f"MARKER (never grandfathered): {m}")

    if r.upstream_path is None:
        return violations

    base = baseline.get(r.apache_path)
    base_ratio = base.get("ratio", 0.0) if base else 0.0
    base_containment = base.get("containment", 0.0) if base else 0.0
    base_block = base.get("longest_block", 0) if base else 0
    base_comments = base.get("comment_matches", 0) if base else 0

    if r.ratio >= thr and r.ratio > base_ratio + RATIO_DRIFT:
        kind = "regression" if base else "new copying"
        violations.append(
            f"RATIO {r.ratio:.2f} >= {thr:.2f} ({kind}; baseline {base_ratio:.2f}) vs {r.upstream_path}"
        )
    if r.containment >= ct and r.containment > base_containment + CONTAINMENT_DRIFT:
        kind = "regression" if base else "new copying"
        violations.append(
            f"CONTAINMENT {r.containment:.2f} >= {ct:.2f} (fraction of this file copied "
            f"from upstream; {kind}; baseline {base_containment:.2f}) vs {r.upstream_path}"
        )
    if r.longest_block >= blk and r.longest_block > base_block + BLOCK_DRIFT:
        kind = "regression" if base else "new copying"
        violations.append(
            f"CONTIGUOUS BLOCK {r.longest_block} lines >= {blk} ({kind}; "
            f"baseline {base_block}) vs {r.upstream_path}"
        )
    if r.comment_matches > 0 and r.comment_matches > base_comments:
        kind = "regression" if base else "new"
        violations.append(
            f"VERBATIM COMMENT match x{r.comment_matches} ({kind}; baseline "
            f"{base_comments}) vs {r.upstream_path}"
        )
    return violations


def render_markdown(failed: list[tuple[str, list[str]]], warned: int, scanned: int,
                    mode_desc: str, thr: float, ct: float, blk: int) -> str:
    """Render the gate result as a GitHub-flavored-markdown summary/PR comment."""
    if not failed:
        out = [
            "### ✅ Upstream-copy gate passed",
            "",
            f"Scanned {scanned} file(s) ({mode_desc}); no new copying, regressions, "
            "or license/attribution markers.",
        ]
        if warned:
            out.append(f"\n_{warned} grandfathered file(s) still carry baseline-level "
                       "copying (tracked, not blocking)._")
        return "\n".join(out) + "\n"

    out = [
        f"### ❌ Upstream-copy gate: {len(failed)} file(s) with new/regressed copying or markers",
        "",
        f"Scanned {scanned} file(s) ({mode_desc}); thresholds: ratio ≥ {thr:.2f}, "
        f"containment ≥ {ct:.2f}, contiguous block ≥ {blk} lines.",
        "",
        "| File | Findings |",
        "|---|---|",
    ]
    for path, violations in failed:
        cell = "<br>".join(v.replace("|", "\\|") for v in violations)
        out.append(f"| `{path}` | {cell} |")
    out += [
        "",
        "**Remediation:** re-express the copied upstream boilerplate independently "
        "(own structure/comments) while preserving the functional contract (column "
        "names/types, exported API); for frontend, wrap the upstream component instead "
        "of forking it. If this is an intentional, reviewed change to an already-flagged "
        "file, regenerate the baseline (`bin/check-upstream-copying.py --all "
        "--write-baseline bin/upstream-copy-baseline.json`) and get the diff reviewed.",
    ]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="scan every Apache-tracked source file")
    mode.add_argument("--diff", metavar="BASE_REF", help="scan only files changed vs BASE_REF (e.g. origin/main)")
    ap.add_argument("--baseline", default=str(REPO_ROOT / "bin" / "upstream-copy-baseline.json"))
    ap.add_argument("--write-baseline", metavar="PATH", help="write a fresh baseline to PATH and exit 0")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--containment", type=float, default=DEFAULT_CONTAINMENT)
    ap.add_argument("--block-lines", type=int, default=DEFAULT_BLOCK_LINES)
    ap.add_argument("--report-only", action="store_true", help="print violations but always exit 0")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON of all signals")
    ap.add_argument("--summary-md", metavar="PATH", help="write a markdown result summary (for the CI job summary / PR comment)")
    args = ap.parse_args()

    thr, ct, blk = args.threshold, args.containment, args.block_lines
    targets = iter_source_files() if args.all else changed_files(args.diff)
    results = [analyze(p, thr, ct, blk) for p in targets]

    if args.write_baseline:
        baseline = build_baseline(results, thr, ct, blk)
        Path(args.write_baseline).write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline with {len(baseline['files'])} flagged files to {args.write_baseline}")
        return 0

    if args.json:
        print(json.dumps([r.__dict__ for r in results if r.signals()], indent=2))
        return 0

    baseline = load_baseline(Path(args.baseline))
    failed: list[tuple[str, list[str]]] = []
    warned = 0
    for r in results:
        violations = evaluate(r, baseline, thr, ct, blk)
        if violations:
            failed.append((r.apache_path, violations))
        elif r.upstream_path and r.apache_path in baseline:
            warned += 1  # grandfathered copy, still tracked

    mode_desc = "full tree" if args.all else "changed vs " + args.diff
    if args.summary_md:
        Path(args.summary_md).write_text(
            render_markdown(failed, warned, len(results), mode_desc, thr, ct, blk),
            encoding="utf-8",
        )

    print(f"Scanned {len(results)} Apache-tracked source file(s) ({mode_desc}).")
    print(f"Thresholds: ratio >= {thr:.2f}, containment >= {ct:.2f}, block >= {blk} lines.")
    if warned:
        print(f"{warned} grandfathered file(s) still carrying baseline-level copying (remediation pending).")

    if not failed:
        print("PASS: no new copying, regressions, or license/attribution markers.")
        return 0

    print(f"\nFAIL: {len(failed)} file(s) with new/regressed copying or markers:\n")
    for path, violations in failed:
        print(f"  {path}")
        for v in violations:
            print(f"      - {v}")
    print(
        "\nRemediation: express the copied upstream boilerplate independently (own "
        "structure/comments) while preserving the functional contract (column "
        "names/types, exported API). For frontend, shrink the override to the "
        "tenant/RBAC delta and wrap the upstream component instead of forking its body.\n"
        "If this is an intentional, reviewed change to an already-flagged file, "
        "regenerate the baseline with --write-baseline and get the diff reviewed."
    )
    return 0 if args.report_only else 1


if __name__ == "__main__":
    sys.exit(main())
