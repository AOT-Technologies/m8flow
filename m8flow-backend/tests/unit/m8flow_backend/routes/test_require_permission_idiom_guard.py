"""Pin one authorization idiom in routes/: gates via @require_permission,
queries via user_has_permission — no inline allow_uri gates.

Architecture review C3 / wayfinder finish-require-permission ticket 06.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROUTES_DIR = (
    Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "routes"
)

# Out-of-map files that still call allow_uri (query or gate) until a later effort.
_ALLOW_URI_ALLOWLIST = frozenset(
    {
        "capabilities_controller.py",
        "keycloak_controller.py",
    }
)

_MIGRATED_NO_ALLOW_URI_IMPORT = frozenset(
    {
        "process_instances_controller.py",
        "processes_controller.py",
        "task_review_controller.py",
        "home_controller.py",
    }
)

_IDIOM_HINT = (
    "Use @require_permission for gates; user_has_permission for queries that shape a payload."
)


def _route_py_files() -> list[Path]:
    return sorted(p for p in _ROUTES_DIR.glob("*.py") if p.name != "__init__.py")


def _imports_allow_uri(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "allow_uri":
                    return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "allow_uri" or alias.name.endswith(".allow_uri"):
                    return True
    return False


def _calls_named(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == name:
                return True
    return False


def _is_not_call_to(test: ast.AST, name: str) -> bool:
    """True for `if not name(...):` (UnaryOp Not wrapping a Call to name)."""
    if not isinstance(test, ast.UnaryOp) or not isinstance(test.op, ast.Not):
        return False
    operand = test.operand
    return (
        isinstance(operand, ast.Call)
        and isinstance(operand.func, ast.Name)
        and operand.func.id == name
    )


def _gate_violations(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if _is_not_call_to(node.test, "allow_uri"):
            found.append(f"line {node.lineno}: if not allow_uri(...) gate")
        if _is_not_call_to(node.test, "user_has_permission"):
            found.append(
                f"line {node.lineno}: if not user_has_permission(...) DIY gate"
            )
    return found


def _scan_source(source: str, *, filename: str) -> list[str]:
    """Return human-readable violations for one routes module source."""
    tree = ast.parse(source, filename=filename)
    violations = _gate_violations(tree)

    imports_allow = _imports_allow_uri(tree)
    calls_allow = _calls_named(tree, "allow_uri")

    if filename in _MIGRATED_NO_ALLOW_URI_IMPORT and imports_allow:
        violations.append("must not import allow_uri (use the two verbs)")

    if filename not in _ALLOW_URI_ALLOWLIST and (imports_allow or calls_allow):
        violations.append(
            "calls/imports allow_uri outside the allow-list "
            f"({', '.join(sorted(_ALLOW_URI_ALLOWLIST))})"
        )

    return violations


def test_routes_use_one_authorization_idiom():
    """Every routes/*.py file: no inline allow_uri / DIY user_has_permission gates;
    only allow-listed controllers may still touch allow_uri.
    """
    assert _ROUTES_DIR.is_dir(), f"routes dir missing: {_ROUTES_DIR}"
    failures: list[str] = []
    for path in _route_py_files():
        for message in _scan_source(path.read_text(encoding="utf-8"), filename=path.name):
            failures.append(f"{path.name}: {message}")
    assert not failures, (
        "Authorization idiom regression in routes/.\n"
        + _IDIOM_HINT
        + "\n"
        + "\n".join(failures)
    )


@pytest.mark.parametrize(
    "snippet,filename,expect_substr",
    [
        (
            "def h():\n    if not allow_uri(u, 'GET', '/x'):\n        return\n",
            "widget_controller.py",
            "if not allow_uri",
        ),
        (
            "def h():\n    if not user_has_permission(u, 'GET', '/x'):\n        raise X\n",
            "widget_controller.py",
            "if not user_has_permission",
        ),
        (
            "from m8flow_backend.authorization import allow_uri\n\ndef h():\n    return allow_uri(u, 'GET', '/x')\n",
            "home_controller.py",
            "must not import allow_uri",
        ),
        (
            "from m8flow_backend.authorization import allow_uri\n\ndef h():\n    return allow_uri(u, 'GET', '/x')\n",
            "new_controller.py",
            "outside the allow-list",
        ),
    ],
)
def test_idiom_guard_detects_forbidden_patterns(snippet, filename, expect_substr):
    """Prove the scan bites — synthetic sources must fail with a clear hint."""
    violations = _scan_source(snippet, filename=filename)
    assert violations, f"expected violations for {filename!r}"
    blob = "\n".join(violations)
    assert expect_substr in blob
    # Message contract: one-line pointer at the two verbs.
    assert "@require_permission" in _IDIOM_HINT
    assert "user_has_permission" in _IDIOM_HINT


def test_idiom_guard_allows_query_verb_and_allowlisted_allow_uri():
    """user_has_permission as a boolean (not `if not …`) is fine; allow-list may call allow_uri."""
    query_ok = (
        "from m8flow_backend.authorization import user_has_permission\n"
        "def get_home_stats():\n"
        "    can = user_has_permission(u, 'GET', '/v1.0/tasks')\n"
        "    if can:\n"
        "        return 1\n"
        "    return None\n"
    )
    assert _scan_source(query_ok, filename="home_controller.py") == []

    allowlisted = (
        "from m8flow_backend.authorization import allow_uri\n"
        "def get_capabilities():\n"
        "    return allow_uri(u, 'POST', '/v1.0/process-instances')\n"
    )
    assert _scan_source(allowlisted, filename="capabilities_controller.py") == []
