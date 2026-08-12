#!/usr/bin/env python3
"""Token-level guard against copying gitignored LGPL upstream (spiff-arena) source
into the Apache-2.0 m8flow trees, using PMD CPD (Copy/Paste Detector).

This complements bin/check-upstream-copying.py. That gate compares *raw lines* and
is cross-language, comment-aware, and fast — but heavy reflowing, reindentation, or
identifier renaming lower its scores. CPD tokenizes the source, so with
--ignore-identifiers/--ignore-literals it still matches a copy that was reformatted
and renamed to dodge the line-based gate. The two run side by side; neither
replaces the other.

Scope: cross-tree clones only — a duplicated token block that appears in BOTH an
Apache-2.0 owned tree AND a gitignored upstream tree. Intra-repo duplication is out
of scope. Owned trees scanned today are m8flow-backend/src and m8flow-frontend/src
only; m8flow-connector-proxy is intentionally out of CPD scope (covered by the
raw-line gate in bin/check-upstream-copying.py, which fetches connector-proxy
extras).

REVIEWED SCOPE BOUNDARY (see the gate coverage audit): CPD deliberately covers only
the python + typescript src trees — token-level, reformat/rename-resistant detection
where it matters most. It is NOT the completeness net for the whole repo. Everything
outside that (non-src files, other owned trees, other languages, config/data assets,
shebang scripts, Dockerfiles) is covered by the raw-line gate in
bin/check-upstream-copying.py, which spans all owned trees and includes shebang
scripts and Dockerfiles. The two gates are complementary by design; do not read CPD's
narrow scope as a coverage gap.

A checked-in baseline (bin/upstream-cpd-baseline.json) grandfathers the
clones that already exist so the gate blocks only NEW cross-tree clones and
regressions (a bigger duplicated block against the same counterpart). Clones drop
out of the baseline as files are remediated. Paths listed in
NONCOPYRIGHTABLE_ALLOWLIST are exempted with reviewable rationale (library API /
props contract / scenes a faire) and never re-enter a regenerated baseline.

Fail-closed behavior (license gate must not silently PASS when misconfigured):
- Owned + upstream trees for each scanned language must exist (run fetch-upstream).
- CPD parse/launch errors fail the run (--no-fail-on-error is NOT used).
- If a large baseline is present but few of its still-on-disk pairs are recovered,
  the run fails (broken detector / empty scan), not PASS.

PMD CPD notes handled here:
- CPD's `typescript` language registers `.ts` only and cannot read `.tsx`/`.jsx`,
  though its lexer tokenizes JSX fine once the file carries a `.ts` extension.
  So frontend files are staged into a temp tree with normalized `.ts` extensions
  and the reported paths are mapped back to the real repo paths. Non-`.ts`
  sources get a `stem__tsx.ts`-style name so they cannot overwrite a sibling `.ts`.
- Requires a PMD 7 install. Point to it with $PMD_BIN (path to the `pmd`
  launcher), or have `pmd`/`cpd` on PATH.

Usage:
  # Regenerate the baseline from the current working tree (after fetch-upstream):
  bin/check-upstream-cpd.py --write-baseline bin/upstream-cpd-baseline.json

  # Gate (fail on new cross-tree clones / regressions vs the baseline):
  bin/check-upstream-cpd.py

  # See everything without failing:
  bin/check-upstream-cpd.py --report-only
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Apache-2.0 owned trees that have a gitignored upstream counterpart.
# Intentionally narrower than check-upstream-copying.py: connector-proxy is not
# scanned here (raw-line gate + fetch-upstream-extra.sh cover that tree).
OWNED_TREES = {
    "python": ["m8flow-backend/src"],
    "typescript": ["m8flow-frontend/src"],
}
UPSTREAM_TREES = {
    "python": ["spiffworkflow-backend/src", "spiff-arena-common"],
    "typescript": ["spiffworkflow-frontend/src"],
}

TS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}  # normalized to .ts when staged

# 75 tokens (~12-18 duplicated lines) balances catching small-model evasion against
# false positives on structurally-similar boilerplate; tune with --min-tokens.
DEFAULT_MIN_TOKENS = 75
TOKEN_DRIFT = 20  # allow small growth on an already-flagged pair before calling it a regression

# If this many baseline pairs still exist on disk but fewer than half are recovered
# from the CPD scan, treat the detector as broken (fail closed) rather than PASS.
BASELINE_RECOVERY_MIN_EXPECTED = 5
BASELINE_RECOVERY_RATIO = 0.5

SKIP_DIR_PARTS = {"node_modules", "__pycache__", ".venv", "dist", "build", "coverage", "__snapshots__", ".git"}

# Path-exact waivers for residual token clones that are non-copyrightable
# (library API / props contract / scènes à faire), mirroring
# bin/check-upstream-copying.py's NONCOPYRIGHTABLE_ALLOWLIST. Allowlisted owned
# files are omitted from regenerated baselines and similarity violations; they
# are still scanned so a future larger clone against a new counterpart would
# surface if the path were removed from this map.
NONCOPYRIGHTABLE_ALLOWLIST: dict[str, str] = {
    # Map ticket 14 — diagram cluster: props/API contract + bpmn-js modeler config.
    "m8flow-frontend/src/components/ReactDiagramEditor.types.ts":
        "Diagram editor props type contract (ReactDiagramEditorProps); prop names are the call-site API surface plus m8flow hideDeleteButton/hideViewXmlButton.",
    "m8flow-frontend/src/components/useDiagramModeler.ts":
        "bpmn-js / dmn-js modeler construction and library wiring (scenes a faire / published package API); copyrightable import/event logic was rewritten in ticket 14.",
}

def find_pmd() -> str:
    env = os.environ.get("PMD_BIN")
    if env and Path(env).exists():
        return env
    for name in ("pmd", "cpd"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit(
        "error: PMD not found. Install PMD 7 and set $PMD_BIN to its `pmd` launcher, "
        "or put `pmd`/`cpd` on PATH. See .github/workflows/ci.yml for the pinned version."
    )


def require_trees() -> None:
    """Fail closed when owned trees exist but their upstream counterparts do not.

    Without upstream, every scan would find zero cross-tree clones and PASS.
    """
    missing: list[str] = []
    for lang in ("python", "typescript"):
        owned_present = any((REPO_ROOT / t).is_dir() for t in OWNED_TREES[lang])
        if not owned_present:
            continue
        upstream_present = any((REPO_ROOT / t).is_dir() for t in UPSTREAM_TREES[lang])
        if not upstream_present:
            missing.extend(UPSTREAM_TREES[lang])
    if missing:
        sys.exit(
            "error: upstream trees missing (required for cross-tree CPD): "
            + ", ".join(missing)
            + ". Run bin/fetch-upstream.sh first."
        )


def _is_under(path: Path, trees: list[str]) -> str | None:
    """Return the owning tree prefix if path is under one of trees, else None."""
    rel = str(path)
    for tree in trees:
        if rel == tree or rel.startswith(tree + "/"):
            return tree
    return None


def _staged_ts_rel(rel: Path) -> Path:
    """Map a real TS/JS path to a unique staged `.ts` path (no sibling collisions)."""
    if rel.suffix == ".ts":
        return rel
    # Foo.tsx -> Foo__tsx.ts so it cannot overwrite Foo.ts in the same directory.
    return rel.parent / f"{rel.stem}__{rel.suffix.lstrip('.')}.ts"


def stage_typescript() -> tuple[Path, dict[str, str]]:
    """Copy TS/TSX/JS/JSX sources into a temp tree with a normalized `.ts` extension
    (CPD's typescript language only reads `.ts`). Returns (staged_root, mapping from
    staged absolute path -> real repo-relative path)."""
    staged_root = Path(tempfile.mkdtemp(prefix="cpd-ts-"))
    mapping: dict[str, str] = {}
    for tree in OWNED_TREES["typescript"] + UPSTREAM_TREES["typescript"]:
        tree_path = REPO_ROOT / tree
        if not tree_path.is_dir():
            continue
        for src in tree_path.rglob("*"):
            if not src.is_file() or src.suffix not in TS_SUFFIXES:
                continue
            rel = src.relative_to(REPO_ROOT)
            if SKIP_DIR_PARTS & set(rel.parts):
                continue
            dst = staged_root / _staged_ts_rel(rel)
            if dst.exists():
                sys.exit(
                    f"error: staged path collision for {rel} -> {dst.relative_to(staged_root)} "
                    f"(already mapped from {mapping.get(str(dst.resolve()), '?')})"
                )
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            mapping[str(dst.resolve())] = str(rel)
    return staged_root, mapping


def run_cpd(pmd: str, language: str, dirs: list[Path], min_tokens: int, ignore_identifiers: bool, ignore_literals: bool) -> str:
    cmd = [
        pmd, "cpd",
        "--minimum-tokens", str(min_tokens),
        "--language", language,
        "--format", "csv",
        # Violations are expected and parsed from stdout; do not treat them as failure.
        # Do NOT pass --no-fail-on-error: lexical/parse errors must fail the license gate.
        "--no-fail-on-violation",
    ]
    if ignore_identifiers:
        cmd.append("--ignore-identifiers")
    if ignore_literals:
        cmd.append("--ignore-literals")
    for d in dirs:
        cmd += ["--dir", str(d)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # CPD exits 0 with --no-fail-on-violation; exit 4 is the historical "violations found"
    # code some PMD builds still emit. Any other non-zero is a real launch/parse error.
    if proc.returncode not in (0, 4):
        sys.stderr.write(proc.stderr)
        sys.exit(f"error: CPD failed (exit {proc.returncode}) for language {language}")
    if proc.stderr.strip():
        # Surface warnings (e.g. skipped files) without failing on empty stderr noise.
        sys.stderr.write(proc.stderr)
        if not proc.stderr.endswith("\n"):
            sys.stderr.write("\n")
    return proc.stdout


def parse_csv(csv_text: str) -> list[dict]:
    """Parse CPD CSV rows into {tokens, files:[abs,...]} dicts.

    CPD `csv` format: lines,tokens,occurrences, then (start_line, path)*occurrences.
    Uses the csv module so quoted paths with commas still parse; asserts occurrence
    counts match so a malformed row cannot silently drop clones.
    """
    clones: list[dict] = []
    reader = csv.reader(io.StringIO(csv_text))
    for parts in reader:
        if len(parts) < 5 or not parts[1].isdigit():
            continue  # header or malformed
        tokens = int(parts[1])
        occ = int(parts[2])
        # After lines,tokens,occurrences: pairs of (start_line, path)
        rest = parts[3:]
        if len(rest) != 2 * occ:
            sys.exit(
                f"error: malformed CPD CSV row (expected {2 * occ} occurrence fields, "
                f"got {len(rest)}): {parts[:6]}..."
            )
        files = []
        for i in range(occ):
            path = rest[2 * i + 1]
            if not path:
                sys.exit(f"error: empty file path in CPD CSV row: {parts[:6]}...")
            files.append(path)
        if len(files) != occ:
            sys.exit(f"error: CPD CSV occurrence mismatch ({len(files)} != {occ})")
        clones.append({"tokens": tokens, "files": files})
    return clones


def cross_tree_pairs(clones: list[dict], owned: list[str], upstream: list[str], staged_map: dict[str, str] | None) -> dict[str, dict[str, int]]:
    """From CPD clones, keep only cross-tree ones and return
    {owned_relpath: {upstream_relpath: max_tokens}}."""
    result: dict[str, dict[str, int]] = {}
    for clone in clones:
        # Map each occurrence's absolute path back to a repo-relative path.
        rels = []
        for abs_path in clone["files"]:
            if staged_map is not None:
                rel = staged_map.get(str(Path(abs_path).resolve()))
                if rel is None:
                    continue
            else:
                try:
                    rel = str(Path(abs_path).resolve().relative_to(REPO_ROOT))
                except ValueError:
                    continue
            rels.append(rel)
        owned_hits = [r for r in rels if _is_under(Path(r), owned)]
        upstream_hits = [r for r in rels if _is_under(Path(r), upstream)]
        if not owned_hits or not upstream_hits:
            continue  # not a cross-tree clone
        for o in owned_hits:
            for u in upstream_hits:
                result.setdefault(o, {})
                result[o][u] = max(result[o].get(u, 0), clone["tokens"])
    return result


def collect(pmd: str, min_tokens: int, ignore_identifiers: bool, ignore_literals: bool) -> dict[str, dict[str, int]]:
    pairs: dict[str, dict[str, int]] = {}

    # Python — run directly on the real trees (require_trees already ensured upstream).
    py_dirs = [REPO_ROOT / t for t in OWNED_TREES["python"] + UPSTREAM_TREES["python"] if (REPO_ROOT / t).is_dir()]
    if py_dirs:
        clones = parse_csv(run_cpd(pmd, "python", py_dirs, min_tokens, ignore_identifiers, ignore_literals))
        for o, ups in cross_tree_pairs(clones, OWNED_TREES["python"], UPSTREAM_TREES["python"], None).items():
            pairs.setdefault(o, {}).update(ups)

    # TypeScript/TSX — stage into a `.ts`-normalized temp tree first.
    staged_root, staged_map = stage_typescript()
    try:
        if any(staged_map):
            clones = parse_csv(run_cpd(pmd, "typescript", [staged_root], min_tokens, ignore_identifiers, ignore_literals))
            for o, ups in cross_tree_pairs(clones, OWNED_TREES["typescript"], UPSTREAM_TREES["typescript"], staged_map).items():
                pairs.setdefault(o, {}).update(ups)
    finally:
        shutil.rmtree(staged_root, ignore_errors=True)

    return pairs


def drop_allowlisted(pairs: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    """Omit owned paths on NONCOPYRIGHTABLE_ALLOWLIST from gate/baseline maps."""
    return {
        owned: ups
        for owned, ups in pairs.items()
        if owned not in NONCOPYRIGHTABLE_ALLOWLIST
    }


def build_baseline(pairs: dict[str, dict[str, int]], min_tokens: int, ignore_identifiers: bool, ignore_literals: bool) -> dict:
    gated = drop_allowlisted(pairs)
    return {
        "_comment": (
            "Grandfathered cross-tree CPD clones (owned <-> upstream). The gate blocks "
            "NEW clones and REGRESSIONS (larger duplicated blocks) beyond these token "
            "counts; clones drop out as files are remediated. Paths on "
            "NONCOPYRIGHTABLE_ALLOWLIST are omitted (exempt with rationale, not "
            "remediation-pending). Regenerate with: "
            "bin/check-upstream-cpd.py --write-baseline bin/upstream-cpd-baseline.json"
        ),
        "min_tokens": min_tokens,
        "ignore_identifiers": ignore_identifiers,
        "ignore_literals": ignore_literals,
        "clones": {o: dict(sorted(ups.items())) for o, ups in sorted(gated.items())},
    }


def baseline_recovery(pairs: dict[str, dict[str, int]], base: dict) -> tuple[int, int]:
    """Count baseline pairs whose files still exist on disk, and how many CPD recovered.

    Used to fail closed when the detector returns an empty/near-empty scan against a
    large baseline (misconfigured PMD, missing upstream, etc.) rather than PASS.
    """
    expected = 0
    found = 0
    for owned, ups in base.items():
        if not (REPO_ROOT / owned).is_file():
            continue
        for upstream in ups:
            if not (REPO_ROOT / upstream).is_file():
                continue
            expected += 1
            if pairs.get(owned, {}).get(upstream, 0) > 0:
                found += 1
    return expected, found


def render_markdown(viol: list[tuple], total: int, grandfathered: int, min_tokens: int,
                    ignore_identifiers: bool, ignore_literals: bool, error: str | None = None) -> str:
    """Render the CPD gate result as a GitHub-flavored-markdown summary/PR comment."""
    if error:
        return f"### ⚠️ Upstream-copy (CPD) gate error\n\n{error}\n"
    if not viol:
        out = [
            "### ✅ Upstream-copy (CPD) gate passed",
            "",
            f"{total} cross-tree token clone pair(s) at ≥ {min_tokens} tokens — all grandfathered.",
        ]
        if grandfathered:
            out.append(f"\n_{grandfathered} grandfathered clone pair(s) still present "
                       "(tracked, not blocking)._")
        return "\n".join(out) + "\n"

    out = [
        f"### ❌ Upstream-copy (CPD) gate: {len(viol)} new/regressed cross-tree clone(s)",
        "",
        f"Token-level (PMD CPD, `--ignore-identifiers`={ignore_identifiers}, "
        f"`--ignore-literals`={ignore_literals}), minimum {min_tokens} tokens.",
        "",
        "| Owned file | Upstream | Tokens | Kind |",
        "|---|---|---|---|",
    ]
    for owned, upstream, tokens, kind, base_tokens in viol:
        tok = f"{tokens}" if kind == "new clone" else f"{tokens} (baseline {base_tokens})"
        out.append(f"| `{owned}` | `{upstream}` | {tok} | {kind} |")
    out += [
        "",
        "**Remediation:** token-level duplication survived reformatting/renaming — "
        "re-express the copied logic independently, or (for a reviewed, intentional "
        "change) regenerate the baseline (`bin/check-upstream-cpd.py --write-baseline "
        "bin/upstream-cpd-baseline.json`).",
    ]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", default=str(REPO_ROOT / "bin" / "upstream-cpd-baseline.json"))
    ap.add_argument("--write-baseline", metavar="PATH", help="write a fresh baseline to PATH and exit 0")
    ap.add_argument("--min-tokens", type=int, default=DEFAULT_MIN_TOKENS)
    ap.add_argument("--no-ignore-identifiers", action="store_true", help="do not ignore identifier names (less rename-resistant)")
    ap.add_argument("--no-ignore-literals", action="store_true", help="do not ignore literal values")
    ap.add_argument("--report-only", action="store_true", help="print findings but always exit 0")
    ap.add_argument("--summary-md", metavar="PATH", help="write a markdown result summary (for the CI job summary / PR comment)")
    args = ap.parse_args()

    require_trees()
    pmd = find_pmd()
    ignore_identifiers = not args.no_ignore_identifiers
    ignore_literals = not args.no_ignore_literals
    pairs = drop_allowlisted(
        collect(pmd, args.min_tokens, ignore_identifiers, ignore_literals)
    )

    if args.write_baseline:
        baseline = build_baseline(pairs, args.min_tokens, ignore_identifiers, ignore_literals)
        n = sum(len(v) for v in baseline["clones"].values())
        Path(args.write_baseline).write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote CPD baseline: {len(baseline['clones'])} owned file(s), {n} cross-tree clone pair(s) -> {args.write_baseline}")
        return 0

    baseline_data = json.loads(Path(args.baseline).read_text(encoding="utf-8")) if Path(args.baseline).is_file() else {}
    base = baseline_data.get("clones", {})

    total = sum(len(v) for v in pairs.values())
    grandfathered = sum(
        1 for o, ups in pairs.items() for u, t in ups.items()
        if base.get(o, {}).get(u, 0) > 0 and t <= base.get(o, {}).get(u, 0) + TOKEN_DRIFT
    )

    expected, recovered = baseline_recovery(pairs, base)
    if expected >= BASELINE_RECOVERY_MIN_EXPECTED and recovered < expected * BASELINE_RECOVERY_RATIO:
        msg = (
            f"error: CPD recovered only {recovered}/{expected} on-disk baseline clone "
            f"pair(s) (< {BASELINE_RECOVERY_RATIO:.0%}). Treating this as a broken "
            f"detector (empty/partial scan), not a clean tree. Check PMD install, "
            f"upstream fetch, and CPD stderr above. After intentional mass remediation, "
            f"regenerate the baseline with --write-baseline."
        )
        if args.summary_md:
            Path(args.summary_md).write_text(
                render_markdown([], total, grandfathered, args.min_tokens,
                                ignore_identifiers, ignore_literals, error=msg),
                encoding="utf-8",
            )
        if args.report_only:
            print(msg, file=sys.stderr)
        else:
            sys.exit(msg)

    # (owned, upstream, tokens, kind, base_tokens)
    viol: list[tuple] = []
    for owned, ups in sorted(pairs.items()):
        for upstream, tokens in sorted(ups.items()):
            base_tokens = base.get(owned, {}).get(upstream, 0)
            if base_tokens == 0:
                viol.append((owned, upstream, tokens, "new clone", 0))
            elif tokens > base_tokens + TOKEN_DRIFT:
                viol.append((owned, upstream, tokens, "regression", base_tokens))

    if args.summary_md:
        Path(args.summary_md).write_text(
            render_markdown(viol, total, grandfathered, args.min_tokens,
                            ignore_identifiers, ignore_literals),
            encoding="utf-8",
        )

    print(f"CPD cross-tree clones: {total} pair(s) at >= {args.min_tokens} tokens "
          f"(ignore_identifiers={ignore_identifiers}, ignore_literals={ignore_literals}).")
    if expected:
        print(f"Baseline recovery: {recovered}/{expected} on-disk grandfathered pair(s) still detected.")
    if grandfathered:
        print(f"{grandfathered} grandfathered clone pair(s) still present (remediation pending).")

    if not viol:
        print("PASS: no new cross-tree clones or regressions.")
        return 0

    print(f"\nFAIL: {len(viol)} new/regressed cross-tree clone(s):\n")
    for owned, upstream, tokens, kind, base_tokens in viol:
        extra = "" if kind == "new clone" else f", baseline {base_tokens}"
        print(f"  - {kind.upper()}: {owned}  <->  {upstream}  ({tokens} tokens{extra})")
    print(
        "\nToken-level duplication survived reformatting/renaming. Re-express the "
        "copied logic independently, or (for a reviewed, intentional change) "
        "regenerate the baseline with --write-baseline."
    )
    return 0 if args.report_only else 1


if __name__ == "__main__":
    sys.exit(main())
