#!/usr/bin/env python
"""Apply LGPL-2.1 SPDX headers to frontend files that retain upstream code.

Background
----------
m8flow's frontend overrides carry substantial code copied from SpiffArena. Where
the copy cannot be removed - because upstream exposes no extension point and
m8flow-core is kept as a pristine mirror - the correct remedy is to license the
file properly rather than misrepresent it as Apache-2.0.

This is the first of the two remedies Sartography proposed: bring the derived
files into compliance with LGPL-2.1, or replace/remove them.

What it does
------------
* prepends an SPDX header naming the actual upstream source file
* skips files whose remaining overlap is only signatures / JSX scaffolding
* is idempotent - re-running changes nothing

Usage
-----
    python bin/apply-lgpl-headers.py --dry-run
    python bin/apply-lgpl-headers.py
"""
from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DATA = REPO / "docs" / "upstream-derived-files-merged.json"

#: Below this many copied lines, what remains is function signatures, import
#: statements and JSX scaffolding - required for compatibility, not authored
#: expression. Headering those would wrongly mark m8flow's own code as LGPL.
THRESHOLD = 20

HEADER = """\
// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileCopyrightText: Sartography and the SpiffArena contributors
// SPDX-FileCopyrightText: 2026 AOT Technologies Inc.
//
// Derived from {upstream} in SpiffArena
// (https://github.com/sartography/spiff-arena), licensed LGPL-2.1-or-later.
// AOT's modifications to this file are released under the same licence.
// See LICENSES/LGPL-2.1-or-later.txt and NOTICE.
"""

BLOCK_START = ("/*",)
LINE_COMMENT = "//"


def code_lines(text: str) -> list[str]:
    out, blk = [], False
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if blk:
            blk = "*/" not in s
            continue
        if s.startswith(BLOCK_START):
            blk = "*/" not in s
            continue
        if s.startswith(LINE_COMMENT):
            continue
        out.append(s)
    return out


def copied_lines(local: pathlib.Path, upstream: pathlib.Path) -> int:
    a, b = code_lines(local.read_text(encoding="utf-8", errors="replace")), \
           code_lines(upstream.read_text(encoding="utf-8", errors="replace"))
    return sum(x.size for x in difflib.SequenceMatcher(None, a, b).get_matching_blocks())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    by = {f["path"]: f for f in data["files"]}
    targets = data["groups"]["B"] + data["groups"]["E2"]

    headered, skipped, already = [], [], []
    for rel in sorted(targets):
        local, upstream = REPO / rel, REPO / by[rel]["up"]
        if not local.exists() or not upstream.exists():
            print(f"  MISSING {rel}", file=sys.stderr)
            continue

        text = local.read_text(encoding="utf-8", errors="replace")
        if "SPDX-License-Identifier" in text:
            already.append(rel)
            continue

        n = copied_lines(local, upstream)
        if n < THRESHOLD:
            skipped.append((rel, n))
            continue

        header = HEADER.format(upstream=by[rel]["up"])
        if not args.dry_run:
            local.write_text(header + "\n" + text, encoding="utf-8")
        headered.append((rel, n))

    print(f"HEADERED ({len(headered)})")
    for rel, n in headered:
        print(f"  {n:5d} copied   {rel.replace('m8flow-frontend/src/', '')}")

    print(f"\nSKIPPED - overlap below {THRESHOLD} lines, signatures/scaffolding only ({len(skipped)})")
    for rel, n in skipped:
        print(f"  {n:5d} copied   {rel.replace('m8flow-frontend/src/', '')}")

    if already:
        print(f"\nALREADY HEADERED ({len(already)})")

    total = sum(n for _, n in headered)
    print(f"\ncopied lines now correctly licensed: {total}")
    if args.dry_run:
        print("DRY RUN - nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
