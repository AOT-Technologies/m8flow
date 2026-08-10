#!/usr/bin/env python3
"""Detect verbatim copying of gitignored LGPL upstream (spiff-arena) source into
the Apache-2.0-licensed m8flow trees.

This is a licensing-boundary guard, not a general code-quality linter. It answers
one question per file: "is this Apache-tracked file a copy of its specific
gitignored upstream counterpart?" Upstream trees (spiffworkflow-backend/,
spiffworkflow-frontend/, spiff-arena-common/) must already be present locally
(they are fetched by bin/fetch-upstream.sh and are gitignored).

Detection is layered because a similarity percentage alone is not enough — a file
can be mostly original yet still paste in a give-away comment, and a partial copy
can dilute its whole-file ratio below any threshold:

  Layer A  whole-file line similarity ratio (difflib.SequenceMatcher)
  Layer B  longest run of contiguous identical lines (catches partial lifts that
           stay under the ratio threshold)
  Layer C1 marker scan: LGPL/GPL header text and unambiguous upstream attribution
           (author handles, sartography). ALWAYS fails — never grandfathered.
  Layer C2 verbatim distinctive-comment match against the upstream counterpart
           (comments are expression, not the functional column/type contract).

A checked-in baseline (bin/upstream-copy-baseline.json) grandfathers the copying
that already exists so the gate blocks *new* copying and *regressions* (an
existing override getting more copied) without demanding an immediate mass
rewrite. Files drop out of the baseline as they are remediated. Layer C1 markers
are never grandfathered.

Usage:
  # Regenerate the baseline from the current working tree (run after fetch-upstream):
  bin/check-upstream-copying.py --all --write-baseline bin/upstream-copy-baseline.json

  # Full-tree report without failing (what does the tree look like today?):
  bin/check-upstream-copying.py --all

  # PR gate: only files changed vs a base ref, fail on new copying / markers / regressions:
  bin/check-upstream-copying.py --diff origin/main

Exit code is non-zero when a violation is found, unless --report-only is passed
(in which case violations are printed but the exit code stays 0 — the rollout lever).
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Apache-2.0-tracked roots that this guard scans. Only backend/frontend have a
# path-convention upstream counterpart; the rest are scanned for C1 markers only.
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

# Apache path prefix -> upstream path prefix (the override path convention, also
# encoded in m8flow-frontend/vite-plugin-override-resolver.ts and the backend layout).
PATH_CONVENTION = [
    ("m8flow-backend/src/m8flow_backend/", "spiffworkflow-backend/src/spiffworkflow_backend/"),
    ("m8flow-frontend/src/", "spiffworkflow-frontend/src/"),
]

# Where to look for a basename fallback when the direct convention path is absent
# (renamed/moved upstream files).
UPSTREAM_SEARCH_ROOTS = [
    "spiffworkflow-backend/src/spiffworkflow_backend",
    "spiffworkflow-frontend/src",
    "spiff-arena-common",
]

SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}

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

# Layer C1 — unambiguous copy evidence. These ALWAYS fail and are never
# grandfathered. Kept deliberately conservative: "SpiffWorkflow" alone is NOT a
# marker (the framework is referenced legitimately all over m8flow). Extend with
# care — a marker must be something that should never appear in m8flow-owned code.
MARKER_PATTERNS = [
    # LGPL / GPL license header text
    (r"GNU\s+Lesser\s+General\s+Public\s+License", "LGPL license header text"),
    (r"GNU\s+General\s+Public\s+License", "GPL license header text"),
    (r"This\s+program\s+is\s+free\s+software", "GPL/LGPL header boilerplate"),
    (r"Free\s+Software\s+Foundation", "FSF license reference"),
    # Upstream developer/org attribution left in comments
    (r"\bjasquat\b", "upstream author handle (jasquat)"),
    (r"\bburnettk\b", "upstream author handle (burnettk)"),
    # Match the upstream repo URL / import path, not prose that merely names the org
    # (e.g. a comment noting a Sartography reference was removed is not copy evidence).
    (r"sartography/", "upstream repo URL or import path (sartography/...)"),
]
COMPILED_MARKERS = [(re.compile(p, re.IGNORECASE), why) for p, why in MARKER_PATTERNS]

# Comments too generic to be copy evidence for Layer C2.
COMMENT_NOISE = re.compile(
    r"noqa|type:\s*ignore|pylint|eslint-disable|@ts-|prettier-ignore|pragma|"
    r"flake8|mypy|coding[:=]|!/usr/bin",
    re.IGNORECASE,
)
MIN_DISTINCTIVE_COMMENT_LEN = 40

DEFAULT_THRESHOLD = 0.50
DEFAULT_BLOCK_LINES = 40
# Small drift so trivial edits to an already-flagged file are not treated as
# regressions; a real re-copy moves the numbers well past this.
RATIO_DRIFT = 0.02
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
    longest_block: int = 0
    comment_matches: int = 0
    markers: list[str] = field(default_factory=list)

    def signals(self) -> bool:
        """True if this file shows any copy signal worth recording/gating."""
        return bool(self.markers) or self.ratio > 0 or self.longest_block > 0 or self.comment_matches > 0


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def extract_comments(lines: list[str], suffix: str) -> set[str]:
    """Return the set of distinctive comment texts in a file (Layer C2 input)."""
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


def _meaningful_hashes(lines: list[str]) -> list[int]:
    """Hashes of substantive lines only, used for the content-addressed index.
    Short/boilerplate lines are skipped so the index stays discriminating."""
    return [hash(s) for ln in lines if len(s := ln.strip()) >= MEANINGFUL_LINE_MINLEN]


# Lazily built once per process — only when a content fallback is actually needed.
_UPSTREAM_INDEX: dict[int, list[str]] | None = None


def get_upstream_index() -> dict[int, list[str]]:
    """Inverted index: meaningful-line hash -> upstream files containing that line."""
    global _UPSTREAM_INDEX
    if _UPSTREAM_INDEX is not None:
        return _UPSTREAM_INDEX
    index: dict[int, list[str]] = {}
    for root in UPSTREAM_SEARCH_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.is_dir():
            continue
        for path in root_path.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            if SKIP_DIR_PARTS & set(path.relative_to(REPO_ROOT).parts):
                continue
            rel = str(path.relative_to(REPO_ROOT))
            for h in set(_meaningful_hashes(_read_lines(path))):
                index.setdefault(h, []).append(rel)
    _UPSTREAM_INDEX = index
    return index


def content_fallback(apache_path: str, a_lines: list[str], threshold: float, block_lines: int) -> Path | None:
    """Best content match against the whole upstream tree, ignoring filename.

    Catches a copy pasted into a differently-named file that has no path/basename
    counterpart. Conservative on purpose: it uses an inverted line-hash index to
    shortlist candidates, confirms them with the same ratio/block metrics, and only
    returns a counterpart that already clears the ratio or contiguous-block bar, so
    genuinely original files are not falsely attributed to upstream."""
    a_hashes = set(_meaningful_hashes(a_lines))
    if len(a_hashes) < FALLBACK_MIN_LINES:
        return None

    index = get_upstream_index()
    shared: dict[str, int] = {}
    for h in a_hashes:
        posting = index.get(h)
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
    best_score = (0.0, 0)  # (ratio, longest_block)
    for rel in candidates:
        cand = REPO_ROOT / rel
        b_lines = _read_lines(cand)
        score = (difflib.SequenceMatcher(None, a_lines, b_lines).ratio(), longest_matching_block(a_lines, b_lines))
        if score > best_score:
            best_score, best = score, cand

    if best is not None and (best_score[0] >= threshold or best_score[1] >= block_lines):
        return best
    return None


def resolve_upstream(apache_path: str, threshold: float, block_lines: int) -> Path | None:
    """Map an Apache-tracked path to its gitignored upstream counterpart via the
    path convention, then a basename search for renamed files, then a
    content-addressed search for copies pasted into differently-named files."""
    for a_prefix, u_prefix in PATH_CONVENTION:
        if apache_path.startswith(a_prefix):
            direct = REPO_ROOT / (u_prefix + apache_path[len(a_prefix) :])
            if direct.is_file():
                return direct
            break  # convention matched but file missing -> try basename fallback

    a_lines = _read_lines(REPO_ROOT / apache_path)
    if not a_lines:
        return None

    basename = Path(apache_path).name
    best: Path | None = None
    best_ratio = 0.0
    for root in UPSTREAM_SEARCH_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.is_dir():
            continue
        for cand in root_path.rglob(basename):
            if not cand.is_file():
                continue
            ratio = difflib.SequenceMatcher(None, a_lines, _read_lines(cand)).ratio()
            if ratio > best_ratio:
                best_ratio, best = ratio, cand
    if best is not None:
        return best

    # No path/basename counterpart -> search by content across the upstream tree.
    return content_fallback(apache_path, a_lines, threshold, block_lines)


def longest_matching_block(a_lines: list[str], b_lines: list[str]) -> int:
    sm = difflib.SequenceMatcher(None, a_lines, b_lines)
    return max((blk.size for blk in sm.get_matching_blocks()), default=0)


def analyze(apache_path: str, threshold: float, block_lines: int) -> FileResult:
    a_path = REPO_ROOT / apache_path
    a_lines = _read_lines(a_path)
    suffix = a_path.suffix
    result = FileResult(apache_path=apache_path, upstream_path=None)

    # Layer C1 markers run on every Apache-tracked file, counterpart or not.
    blob = "\n".join(a_lines)
    for pattern, why in COMPILED_MARKERS:
        if pattern.search(blob):
            result.markers.append(why)

    # A file with no meaningful content (e.g. an empty __init__.py) is not a copy
    # in any sense worth gating; two empty files score a perfect ratio otherwise.
    if not [ln for ln in a_lines if ln.strip()]:
        return result

    upstream = resolve_upstream(apache_path, threshold, block_lines)
    if upstream is None:
        return result
    result.upstream_path = str(upstream.relative_to(REPO_ROOT))
    b_lines = _read_lines(upstream)

    result.ratio = round(difflib.SequenceMatcher(None, a_lines, b_lines).ratio(), 4)
    result.longest_block = longest_matching_block(a_lines, b_lines)

    a_comments = extract_comments(a_lines, suffix)
    if a_comments:
        b_comments = extract_comments(b_lines, upstream.suffix)
        result.comment_matches = len(a_comments & b_comments)

    return result


def iter_source_files() -> list[str]:
    files: list[str] = []
    for root in APACHE_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.is_dir():
            continue
        for path in root_path.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            if SKIP_DIR_PARTS & set(path.relative_to(REPO_ROOT).parts):
                continue
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
        if f.startswith(roots) and Path(f).suffix in SOURCE_SUFFIXES and (REPO_ROOT / f).is_file()
    )


def load_baseline(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("files", {})


def build_baseline(results: list[FileResult], threshold: float, block_lines: int) -> dict:
    files = {}
    for r in results:
        if r.ratio >= threshold or r.longest_block >= block_lines or r.comment_matches > 0:
            files[r.apache_path] = {
                "upstream": r.upstream_path,
                "ratio": r.ratio,
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
        "threshold": threshold,
        "block_lines": block_lines,
        "files": dict(sorted(files.items())),
    }


def evaluate(
    r: FileResult, baseline: dict[str, dict], threshold: float, block_lines: int
) -> list[str]:
    """Return a list of violation messages for one file ([] if clean)."""
    violations: list[str] = []

    # C1 markers: always fatal, never grandfathered.
    for m in r.markers:
        violations.append(f"MARKER (never grandfathered): {m}")

    if r.upstream_path is None:
        return violations

    base = baseline.get(r.apache_path)
    base_ratio = base["ratio"] if base else 0.0
    base_block = base["longest_block"] if base else 0
    base_comments = base["comment_matches"] if base else 0

    if r.ratio >= threshold and r.ratio > base_ratio + RATIO_DRIFT:
        kind = "regression" if base else "new copying"
        violations.append(
            f"RATIO {r.ratio:.2f} >= {threshold:.2f} ({kind}; baseline {base_ratio:.2f}) "
            f"vs {r.upstream_path}"
        )
    if r.longest_block >= block_lines and r.longest_block > base_block + BLOCK_DRIFT:
        kind = "regression" if base else "new copying"
        violations.append(
            f"CONTIGUOUS BLOCK {r.longest_block} lines >= {block_lines} ({kind}; "
            f"baseline {base_block}) vs {r.upstream_path}"
        )
    if r.comment_matches > 0 and r.comment_matches > base_comments:
        kind = "regression" if base else "new"
        violations.append(
            f"VERBATIM COMMENT match x{r.comment_matches} ({kind}; baseline "
            f"{base_comments}) vs {r.upstream_path}"
        )
    return violations


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="scan every Apache-tracked source file")
    mode.add_argument("--diff", metavar="BASE_REF", help="scan only files changed vs BASE_REF (e.g. origin/main)")
    ap.add_argument("--baseline", default=str(REPO_ROOT / "bin" / "upstream-copy-baseline.json"))
    ap.add_argument("--write-baseline", metavar="PATH", help="write a fresh baseline to PATH and exit 0")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--block-lines", type=int, default=DEFAULT_BLOCK_LINES)
    ap.add_argument("--report-only", action="store_true", help="print violations but always exit 0")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON of all signals")
    args = ap.parse_args()

    targets = iter_source_files() if args.all else changed_files(args.diff)
    results = [analyze(p, args.threshold, args.block_lines) for p in targets]

    if args.write_baseline:
        baseline = build_baseline(results, args.threshold, args.block_lines)
        Path(args.write_baseline).write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline with {len(baseline['files'])} flagged files to {args.write_baseline}")
        return 0

    if args.json:
        print(json.dumps([r.__dict__ for r in results if r.signals()], indent=2))
        return 0

    baseline = load_baseline(Path(args.baseline))
    scanned = len(results)
    failed: list[tuple[str, list[str]]] = []
    warned = 0

    for r in results:
        violations = evaluate(r, baseline, args.threshold, args.block_lines)
        if violations:
            failed.append((r.apache_path, violations))
        elif r.upstream_path and r.apache_path in baseline:
            warned += 1  # grandfathered copy, still tracked

    print(f"Scanned {scanned} Apache-tracked source file(s) "
          f"({'full tree' if args.all else 'changed vs ' + args.diff}).")
    print(f"Threshold: ratio >= {args.threshold:.2f}, contiguous block >= {args.block_lines} lines.")
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
