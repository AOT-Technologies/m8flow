#!/usr/bin/env python
"""Replace m8flow's copied model files with thin re-export shims.

Background
----------
m8flow used to copy each upstream model file and add its tenant column, which
placed LGPL-2.1 upstream code inside the Apache-2.0 tree.  The schema delta now
lives in m8flow_backend/models/tenant_schema.py, which augments upstream's own
mapped classes, so the copies serve no purpose.

This script rewrites each copied model module as a shim that re-exports the
upstream names, so existing `from m8flow_backend.models.X import Y` imports keep
working unchanged.

It also empties model_override_patch._OVERRIDES.  That is required, not
optional: while an entry exists, `spiffworkflow_backend.models.X` is redirected
to `m8flow_backend.models.X`, and a shim importing upstream would resolve back
to itself.

Usage
-----
    python bin/generate-model-shims.py --dry-run     # show what would change
    python bin/generate-model-shims.py               # write the changes

Requires the upstream tree to be present (bin/fetch-upstream.sh|ps1).
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
MODELS = REPO / "m8flow-backend/src/m8flow_backend/models"
UPSTREAM = REPO / "spiffworkflow-backend/src/spiffworkflow_backend/models"
OVERRIDE_PATCH = (
    REPO / "m8flow-backend/src/m8flow_backend/services/model_override_patch.py"
)

#: Modules that carry m8flow behaviour beyond the schema delta. A plain shim
#: would silently DROP that behaviour, so these are never auto-generated.
#: Each needs its m8flow logic re-expressed as a patch module first; remove it
#: from this list once that is done and reviewed.
HOLD: dict[str, str] = {}

# RESOLVED - no longer held, kept here as a record of why:
#
#   process_instance, permission_target
#       Method-level deltas (ProcessInstanceModel.get_data and
#       PermissionTargetModel.__init__) now live in
#       m8flow_backend.services.upstream_model_behaviour_patch.
#
#   task_definition, bpmn_process_definition
#       Their only Python delta was calling db_utils.insert_or_ignore_duplicate()
#       instead of importing the function, so the tenant monkey-patch would take
#       effect. tenant_scoping_patch now rebinds the name inside the upstream
#       modules that import it directly, so the copies are unnecessary.
#
#   message_instance
#       Added MessageStatuses.cancelled, which is dead code - nothing in the
#       backend, frontend or tests reads or writes it. Dropped.
#       BEFORE MERGING, confirm no rows carry it:
#           SELECT count(*) FROM message_instance WHERE status = 'cancelled';
#       Must be 0. A Python Enum cannot be extended after definition, so if rows
#       do exist the whole enum has to be replaced - raise it rather than guess.

#: No per-module docstring: it would be the same sentence in every shim. What these
#: modules are is recorded once, in m8flow_backend/models/__init__.py.
SHIM_TEMPLATE = '''from __future__ import annotations

from {upstream_module} import (  # noqa: F401
{imports}
)

__all__ = [
{exports}
]
'''


def public_names(path: pathlib.Path) -> list[str]:
    """Public classes, functions and module-level constants of an upstream module."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    names.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if not node.target.id.startswith("_"):
                names.append(node.target.id)
    seen: set[str] = set()
    return [n for n in names if not (n in seen or seen.add(n))]


def overridden_modules() -> list[str]:
    """The model stems currently listed in _OVERRIDES."""
    src = OVERRIDE_PATCH.read_text(encoding="utf-8")
    return sorted(set(re.findall(r'"spiffworkflow_backend\.models\.(\w+)"\s*:', src)))


def build_shim(stem: str) -> str | None:
    upstream_file = UPSTREAM / f"{stem}.py"
    if not upstream_file.exists():
        print(f"  SKIP {stem}: no upstream file at {upstream_file}", file=sys.stderr)
        return None
    names = public_names(upstream_file)
    if not names:
        print(f"  SKIP {stem}: upstream exports nothing public", file=sys.stderr)
        return None
    return SHIM_TEMPLATE.format(
        upstream_module=f"spiffworkflow_backend.models.{stem}",
        stem=stem,
        imports="\n".join(f"    {n}," for n in names),
        exports="\n".join(f'    "{n}",' for n in names),
    )


def empty_overrides(text: str) -> str:
    """Replace the _OVERRIDES body with an empty dict and an explanatory note."""
    return re.sub(
        r"_OVERRIDES\s*=\s*\{.*?\n\}",
        (
            "# Model overrides are no longer used. m8flow's schema delta is applied to\n"
            "# upstream's tables by m8flow_backend.models.tenant_schema, so upstream's own\n"
            "# model classes already carry m8flow's columns - there is nothing to override.\n"
            "#\n"
            "# Do not add entries here. Schema changes go in models/tenant_schema.py.\n"
            "_OVERRIDES: dict[str, str] = {}"
        ),
        text,
        flags=re.S,
    )


def main() -> int:
    global UPSTREAM
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--upstream",
        help="path to spiffworkflow-backend/src/spiffworkflow_backend/models "
        "(defaults to the in-repo fetched tree)",
    )
    args = parser.parse_args()

    if args.upstream:
        UPSTREAM = pathlib.Path(args.upstream)

    if not UPSTREAM.exists():
        print(f"upstream tree missing: {UPSTREAM}", file=sys.stderr)
        print("run bin/fetch-upstream.sh (or .ps1) first", file=sys.stderr)
        return 2

    stems = overridden_modules()
    print(f"{len(stems)} modules listed in _OVERRIDES\n")

    written = skipped = 0
    held: list[str] = []
    for stem in stems:
        if stem in HOLD:
            held.append(stem)
            continue
        target = MODELS / f"{stem}.py"
        if not target.exists():
            print(f"  SKIP {stem}: {target} does not exist", file=sys.stderr)
            skipped += 1
            continue
        shim = build_shim(stem)
        if shim is None:
            skipped += 1
            continue
        before = len(target.read_text(encoding="utf-8").splitlines())
        after = len(shim.splitlines())
        print(f"  {stem:44s} {before:4d} -> {after:3d} lines")
        if not args.dry_run:
            target.write_text(shim, encoding="utf-8")
        written += 1

    if held:
        print(f"\nHELD BACK - {len(held)} modules carry behaviour a shim would drop:")
        for stem in held:
            print(f"  {stem:38s} {HOLD[stem]}")
        print("  These keep their _OVERRIDES entry until their logic is re-expressed.")

    # Only empty the override map once nothing is held back - otherwise the held
    # modules would stop being served and their behaviour would vanish anyway.
    changed = False
    if not held:
        patch_src = OVERRIDE_PATCH.read_text(encoding="utf-8")
        new_patch = empty_overrides(patch_src)
        changed = new_patch != patch_src
        if changed and not args.dry_run:
            OVERRIDE_PATCH.write_text(new_patch, encoding="utf-8")
    else:
        print("\n_OVERRIDES left intact - entries for held modules are still required.")
        print("Remove the shimmed modules' entries by hand, or clear HOLD and re-run.")

    print(f"\nshims {'planned' if args.dry_run else 'written'}: {written}")
    print(f"held back: {len(held)}")
    print(f"skipped: {skipped}")
    print(f"_OVERRIDES emptied: {changed}")
    if args.dry_run:
        print("\nDRY RUN - nothing written")
    else:
        print("\nNEXT: uv run alembic revision --autogenerate -m check")
        print("      the migration MUST be empty, then delete it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
