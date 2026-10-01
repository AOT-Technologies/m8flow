#!/usr/bin/env python3
"""Alembic migration checks for m8flow-backend.

Fails the job on:
  - a migration file that cannot be read or does not compile;
  - a broken revision chain: duplicate revision ids, a down_revision that
    does not exist, or more than one head.

Warns, with the file and line, on destructive operations in the upgrade() of
migrations changed by this pull request or push: op.drop_*, and DROP /
ALTER TABLE ... DROP / TRUNCATE / DELETE FROM in raw SQL (a heuristic).
downgrade() is expected to drop what its
upgrade() created, so it is not scanned.

Usage: check_migrations.py [BASE_SHA]
  BASE_SHA: compare against it to find changed migrations. Without it (or
  if it is not in the history), every migration counts as changed.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

VERSIONS = Path("m8flow-backend/migrations/versions")
# Comments may sit between keywords ("DELETE -- all rows\n FROM t").
_GAP = r"(?:\s|--[^\n]*\n|/\*.*?\*/)+"
SQL_DESTRUCTIVE = re.compile(
    rf"\b(DROP{_GAP}(?:TABLE|COLUMN|INDEX|CONSTRAINT|SCHEMA|TYPE|VIEW|MATERIALIZED{_GAP}VIEW|SEQUENCE)"
    rf"|ALTER{_GAP}TABLE\b[^;]*?\bDROP"
    rf"|TRUNCATE|DELETE{_GAP}FROM)\b",
    re.I | re.S,
)


def summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def changed_files(base: str | None) -> set[str] | None:
    if not base or set(base) == {"0"}:
        return None
    try:
        subprocess.run(["git", "cat-file", "-e", f"{base}^{{commit}}"], check=True, capture_output=True)
        out = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AMR", f"{base}...HEAD", "--", str(VERSIONS)],
                             check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
        return None
    return {line.strip() for line in out.splitlines() if line.strip()}


def literal(node: ast.AST | None):
    """The node's Python value, or None if it is not a plain literal."""
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


def revisions(tree: ast.Module) -> tuple[str | None, list[str]]:
    rev, down = None, []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            value = literal(node.value)
            if "revision" in names and isinstance(value, str):
                rev = value
            if "down_revision" in names:
                if isinstance(value, str):
                    down = [value]
                elif isinstance(value, (tuple, list)):
                    down = [v for v in value if isinstance(v, str)]
    return rev, down


def call_name(func: ast.AST) -> tuple[str, str]:
    """(owner, name) of a call: op.drop_table -> ("op", "drop_table"); text -> ("", "text")."""
    if isinstance(func, ast.Attribute):
        owner = func.value.id if isinstance(func.value, ast.Name) else ""
        return owner, func.attr
    if isinstance(func, ast.Name):
        return "", func.id
    return "", ""


def destructive(tree: ast.Module) -> list[tuple[int, str]]:
    """Destructive operations in upgrade(): op.drop_*, and destructive raw SQL
    passed to op.execute / sa.text / text. The SQL match is a heuristic."""
    found = []
    for fn in tree.body:
        if not (isinstance(fn, ast.FunctionDef) and fn.name == "upgrade"):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            owner, name = call_name(node.func)
            if owner == "op" and name.startswith("drop_"):
                found.append((node.lineno, f"op.{name}(...)"))
            elif (owner, name) in (("op", "execute"), ("sa", "text"), ("", "text")) and node.args:
                sql = literal(node.args[0])
                m = SQL_DESTRUCTIVE.search(sql) if isinstance(sql, str) else None
                if m:
                    found.append((node.lineno, f"SQL (heuristic): {m.group(0)}"))
    return found


def main() -> int:
    if not VERSIONS.is_dir():
        print(f"::warning::{VERSIONS} not found; nothing to check.")
        return 0
    files = sorted(VERSIONS.glob("*.py"))
    base = sys.argv[1] if len(sys.argv) > 1 else None
    changed = changed_files(base)
    errors: list[str] = []
    graph: dict[str, list[str]] = {}
    where: dict[str, str] = {}
    flagged: list[tuple[str, int, str]] = []

    for f in files:
        rel = f.as_posix()
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            errors.append(f"{rel}:{exc.lineno or 1}: does not compile: {exc.msg}")
            print(f"::error file={rel},line={exc.lineno or 1}::Migration does not compile: {exc.msg}")
            continue
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            # ValueError: null bytes, before Python 3.12 (3.12 raises SyntaxError).
            errors.append(f"{rel}: cannot be read: {exc}")
            print(f"::error file={rel}::Migration cannot be read: {exc}")
            continue
        rev, down = revisions(tree)
        if not rev:
            errors.append(f"{rel}: no `revision = \"...\"`")
            continue
        if rev in where:
            errors.append(f"{rel}: duplicate revision {rev} (also in {where[rev]})")
        where[rev] = rel
        graph[rev] = down
        if changed is None or rel in changed:
            flagged += [(rel, line, what) for line, what in destructive(tree)]

    for rev, downs in graph.items():
        for d in downs:
            if d not in graph:
                errors.append(f"{where[rev]}: down_revision {d} does not exist")
    parents = {d for downs in graph.values() for d in downs}
    heads = sorted(r for r in graph if r not in parents)
    if graph and len(heads) != 1:
        errors.append(f"expected one head, found {len(heads)}: {', '.join(heads)}. Another migration "
                      f"was merged meanwhile: merge the latest base branch, then run "
                      f"`alembic merge heads` (or re-point down_revision)")

    scope = "all migrations" if changed is None else f"{len(changed)} changed migration(s)"
    lines = ["## Migration check", "",
             f"- {len(files)} migration files, head: `{heads[0] if len(heads) == 1 else ', '.join(heads)}`",
             f"- Destructive-operation scan: {scope}", ""]
    if flagged:
        lines += ["### ⚠️ Destructive operations in upgrade()", "", "| File | Line | Operation |", "|---|---:|---|"]
        lines += [f"| `{rel}` | {line} | `{what}` |" for rel, line, what in flagged]
        lines.append("")
        for rel, line, what in flagged:
            print(f"::warning file={rel},line={line}::Destructive migration operation in upgrade(): {what}. "
                  "Make sure it is intended and the data is migrated first.")
    if errors:
        lines += ["### ❌ Errors", ""] + [f"- {e}" for e in errors]
        for e in errors:
            print(f"::error::{e}")
    else:
        lines.append("✅ Revision chain is consistent and every migration compiles.")
    summary("\n".join(lines))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
