"""Celery monitoring and control access, end to end.

Locks in: every /m8flow/celery/* route is super-admin only; tenant-admin, editor and
reviewer stay out of reads and control actions alike, including through
POST /permissions-check, which drives the designer.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest
import yaml

from m8flow_backend import identity
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.authorization import _NO_GROUP_FALLBACK_PREFIXES, _path_matches, allow_uri
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups

_SRC = Path(__file__).resolve().parents[4] / "src" / "m8flow_backend"
_SERVICE = "https://example.test/realms/m8flow"
_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

EXPECTED_CELERY_ROUTE_SPECS = {
    "/celery/overview": {
        "method": "GET",
        "action": "read",
        "permission_name": "read-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.overview",
        "is_control": False,
    },
    "/celery/workers": {
        "method": "GET",
        "action": "read",
        "permission_name": "read-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.workers",
        "is_control": False,
    },
    "/celery/tasks": {
        "method": "GET",
        "action": "read",
        "permission_name": "read-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.tasks",
        "is_control": False,
    },
    "/celery/broker": {
        "method": "GET",
        "action": "read",
        "permission_name": "read-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.broker",
        "is_control": False,
    },
    "/celery/history": {
        "method": "GET",
        "action": "read",
        "permission_name": "read-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.history",
        "is_control": False,
    },
    "/celery/history/{task_id}": {
        "method": "GET",
        "action": "read",
        "permission_name": "read-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.history_task",
        "is_control": False,
    },
    "/celery/task-types": {
        "method": "GET",
        "action": "read",
        "permission_name": "read-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.task_types",
        "is_control": False,
    },
    "/celery/control/revoke": {
        "method": "POST",
        "action": "create",
        "permission_name": "manage-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/control/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.control_revoke",
        "is_control": True,
    },
    "/celery/control/rate-limit": {
        "method": "POST",
        "action": "create",
        "permission_name": "manage-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/control/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.control_rate_limit",
        "is_control": True,
    },
    "/celery/control/time-limit": {
        "method": "POST",
        "action": "create",
        "permission_name": "manage-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/control/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.control_time_limit",
        "is_control": True,
    },
    "/celery/control/workers/{worker_name}": {
        "method": "POST",
        "action": "create",
        "permission_name": "manage-celery-monitoring",
        "expected_permission_uri": "/m8flow/celery/control/*",
        "operation_id": "m8flow_backend.routes.celery_monitoring_controller.control_worker",
        "is_control": True,
    },
}


def _spec() -> dict:
    return yaml.safe_load((_SRC / "api.yml").read_text(encoding="utf-8"))


def _celery_routes() -> list[tuple[str, str]]:
    return sorted(
        (method.upper(), "/v1.0/m8flow" + re.sub(r"\{[^}]+\}", "x", path))
        for path, operations in _spec()["paths"].items()
        if path.startswith("/celery/")
        for method in operations
        if method.lower() in _HTTP_METHODS
    )


CELERY_ROUTES = _celery_routes()
READ_ROUTES = [route for route in CELERY_ROUTES if route[0] == "GET"]
CONTROL_ROUTES = [route for route in CELERY_ROUTES if route[0] == "POST"]


# Connexion validates a request body before the route's permission gate runs, so each
# control route gets a body that passes its schema; the permission layer is under test.
_VALID_BODIES = {
    "revoke": {"taskId": "t1"},
    "rate-limit": {"taskName": "m8flow.task"},
    "time-limit": {"taskName": "m8flow.task"},
    "x": {"action": "pool_grow"},
}


def _call(client, method: str, path: str, **kwargs):
    if method == "POST":
        return client.post(path, json=_VALID_BODIES[path.rsplit("/", 1)[-1]], **kwargs)
    return client.get(path, **kwargs)


def test_api_yml_celery_routes_exact_match_contract():
    """Assert api.yml contains all expected Celery paths and no undocumented ones."""
    spec_paths = {p for p in _spec()["paths"] if "celery" in p}
    expected_paths = set(EXPECTED_CELERY_ROUTE_SPECS.keys())
    assert spec_paths == expected_paths, f"api.yml celery paths mismatch: {spec_paths ^ expected_paths}"


def test_route_level_security_in_api_yml_for_all_celery_operations():
    """Explicitly validate route-level security, methods, 401/403 responses,
    and operationId bindings for every /celery/* and /celery/control/* path.
    """
    spec = _spec()
    for path, expected in EXPECTED_CELERY_ROUTE_SPECS.items():
        assert path in spec["paths"], f"Route {path} missing from api.yml"
        path_item = spec["paths"][path]

        declared_methods = {
            m.upper() for m in path_item if m.lower() in _HTTP_METHODS
        }
        assert declared_methods == {expected["method"]}, (
            f"Route {path} has methods {declared_methods}, expected {expected['method']}"
        )

        op = path_item[expected["method"].lower()]

        # Must not bypass authentication with `security: []`
        assert "security" not in op or op["security"] != [], (
            f"Route {path} {expected['method']} must not bypass authentication (has security: [])"
        )

        responses = op.get("responses", {})
        assert "401" in responses, f"Route {path} {expected['method']} missing 401 response in api.yml"
        assert "403" in responses, f"Route {path} {expected['method']} missing 403 response in api.yml"

        assert op.get("operationId") == expected["operation_id"], (
            f"Route {path} operationId mismatch: got {op.get('operationId')}, expected {expected['operation_id']}"
        )

        # Confirm operation handler can be imported
        module_name, func_name = expected["operation_id"].rsplit(".", 1)
        mod = importlib.import_module(module_name)
        assert hasattr(mod, func_name) and callable(getattr(mod, func_name)), (
            f"Operation {expected['operation_id']} is not callable in {module_name}"
        )


def test_every_celery_route_is_covered_by_strict_fallback_prefix(db_session):
    """Every /celery/* route must be covered by _NO_GROUP_FALLBACK_PREFIXES so
    the tenant-admin / editor group fallback cannot re-open super-admin endpoints.
    """
    for path in EXPECTED_CELERY_ROUTE_SPECS:
        target_path = f"/m8flow{path}"
        assert target_path.startswith(_NO_GROUP_FALLBACK_PREFIXES), (
            f"{target_path} is not covered by _NO_GROUP_FALLBACK_PREFIXES"
        )

    # Unit check: allow_uri forces group_fallback=False when evaluating celery paths
    # even when group_fallback=True is passed in.
    dummy_user = _provision(db_session, username="editor-fallback-probe", groups=["t1:editor"])
    # Even with group_fallback=True, a non-super-admin user without Celery grants must fail
    assert allow_uri(dummy_user, "GET", "/v1.0/m8flow/celery/overview", session=db_session, group_fallback=True) is False
    assert allow_uri(dummy_user, "POST", "/v1.0/m8flow/celery/control/revoke", session=db_session, group_fallback=True) is False


def test_every_celery_route_maps_to_expected_permissions_yaml():
    """Verify the YAML permission grants in m8flow.yml cover all Celery routes
    with super-admin only and matching read vs create/write actions.
    """
    permissions = yaml.safe_load(
        (_SRC / "config" / "permissions" / "m8flow.yml").read_text(encoding="utf-8")
    )["permissions"]

    for path, expected in EXPECTED_CELERY_ROUTE_SPECS.items():
        auth_path = f"/m8flow{path}"
        perm = permissions.get(expected["permission_name"])
        assert perm is not None, f"Permission {expected['permission_name']} missing from m8flow.yml"
        assert perm["groups"] == ["super-admin"], f"Permission {expected['permission_name']} must be super-admin only"
        assert expected["action"] in perm["actions"], (
            f"Permission {expected['permission_name']} action mismatch: {perm['actions']} does not contain {expected['action']}"
        )
        assert perm["uri"] == expected["expected_permission_uri"]

        # Verify wildcard path matching
        assert _path_matches(auth_path, perm["uri"]), f"{auth_path} does not match {perm['uri']}"

        # Control routes must NOT match the read permission, and read routes must NOT match control
        if expected["is_control"]:
            # Control routes are POSTs (action 'create'), which read-celery-monitoring excludes
            assert expected["action"] not in permissions["read-celery-monitoring"]["actions"]
            assert set(perm["actions"]) == {"create"}
        else:
            manage_perm_uri = permissions["manage-celery-monitoring"]["uri"]
            assert not _path_matches(auth_path, manage_perm_uri), f"Read path {auth_path} matched control uri {manage_perm_uri}"


def test_controller_handlers_have_strict_gate_decorator_and_super_admin_check():
    """Verify in the controller AST that:
    1. _gate is initialized as require_permission(group_fallback=False).
    2. Every handler referenced by api.yml operationId is decorated with @_gate.
    3. Every handler calls _require_super_admin().
    """
    controller_path = _SRC / "routes" / "celery_monitoring_controller.py"
    tree = ast.parse(controller_path.read_text(encoding="utf-8"), filename="celery_monitoring_controller.py")

    # 1. Check _gate definition
    gate_found = False
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_gate":
                    if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                        if node.value.func.id == "require_permission":
                            for kw in node.value.keywords:
                                if kw.arg == "group_fallback" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                                    gate_found = True
    assert gate_found, "_gate must be defined as require_permission(group_fallback=False)"

    # 2 & 3. Check every handler
    expected_handler_names = {spec["operation_id"].rsplit(".", 1)[-1] for spec in EXPECTED_CELERY_ROUTE_SPECS.values()}
    found_handlers = set()

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in expected_handler_names:
            found_handlers.add(node.name)
            decorator_names = [d.id for d in node.decorator_list if isinstance(d, ast.Name)]
            assert "_gate" in decorator_names, f"Handler {node.name} must be decorated with @_gate"

            calls = [
                n.func.id
                for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            ]
            assert "_require_super_admin" in calls, f"Handler {node.name} must call _require_super_admin()"

    assert found_handlers == expected_handler_names


def test_reads_are_get_and_controls_are_post_under_control():
    assert [path for _, path in READ_ROUTES] == [
        "/v1.0/m8flow/celery/broker",
        "/v1.0/m8flow/celery/history",
        "/v1.0/m8flow/celery/history/x",
        "/v1.0/m8flow/celery/overview",
        "/v1.0/m8flow/celery/task-types",
        "/v1.0/m8flow/celery/tasks",
        "/v1.0/m8flow/celery/workers",
    ]
    assert [path for _, path in CONTROL_ROUTES] == [
        "/v1.0/m8flow/celery/control/rate-limit",
        "/v1.0/m8flow/celery/control/revoke",
        "/v1.0/m8flow/celery/control/time-limit",
        "/v1.0/m8flow/celery/control/workers/x",
    ]
    assert all("/celery/control/" in path for _, path in CONTROL_ROUTES)
    assert len(CONTROL_ROUTES) == 4


def test_grants_are_super_admin_only():
    permissions = yaml.safe_load((_SRC / "config" / "permissions" / "m8flow.yml").read_text(encoding="utf-8"))["permissions"]
    grants = {name: p for name, p in permissions.items() if str(p.get("uri", "")).startswith("/m8flow/celery")}
    assert grants == {
        "read-celery-monitoring": {"groups": ["super-admin"], "actions": ["read"], "uri": "/m8flow/celery/*"},
        "manage-celery-monitoring": {"groups": ["super-admin"], "actions": ["create"], "uri": "/m8flow/celery/control/*"},
    }


@pytest.mark.parametrize(
    ("method", "action"),
    [
        ("GET", "read"), ("get", "read"), (" Get ", "read"), ("HEAD", "read"), ("OPTIONS", "read"),
        ("POST", "create"), ("post", "create"), ("Post", "create"),
        ("PUT", "update"), ("PATCH", "update"), ("delete", "delete"),
        ("create", "create"), ("Create", "create"), ("CREATE", "create"), (" read ", "read"),
        ("start", "start"), ("Execute", "execute"),
        # Not an HTTP method and not an action in m8flow.yml: denied, never read.
        ("write", "unknown"), ("Write", "unknown"), ("WRITE", "unknown"),
        ("PURGE", "unknown"), ("readd", "unknown"), ("", "unknown"),
    ],
)
def test_method_to_action_is_case_insensitive_and_fails_closed(method, action):
    """PR review on #294: mixed case must not depend on which keys happen to exist, and an
    unknown method or action must not fall back to "read"."""
    from m8flow_backend.authorization import _method_to_action

    assert _method_to_action(method) == action


def test_an_unknown_action_is_logged_on_one_line(caplog):
    """CodeQL py/log-injection on #294: the method can come from a request body."""
    from m8flow_backend.authorization import _method_to_action

    caplog.set_level("WARNING", logger="m8flow_backend.authorization")
    assert _method_to_action("Frob\nWARNING forged line" + "x" * 500) == "unknown"
    [message] = [r.getMessage() for r in caplog.records if r.name == "m8flow_backend.authorization"]
    assert "\n" not in message and "\r" not in message
    assert "Frob\\nWARNING forged line" in message
    assert len(message) < 160  # the value is capped


def test_an_unknown_action_is_denied_where_read_is_granted(db_session):
    reader = _provision(db_session, username="reader-action-test", groups=["super-admin"])
    editor = _provision(db_session, username="editor-action-test", groups=["t1:editor"])
    path = "/v1.0/m8flow/celery/control/revoke"
    # Super-admins pass every check by policy; for anyone else an unknown verb grants nothing.
    assert allow_uri(reader, "Write", path, session=db_session) is True
    for verb in ("POST", "create", "Create", "write", "Write"):
        assert allow_uri(editor, verb, path, session=db_session) is False
    # The editor's read-only grant on /processes: with the role fallback off (it ignores the
    # action by design), the grant alone decides, and an unknown verb is not a read.
    assert allow_uri(editor, "GET", "/v1.0/processes", session=db_session, group_fallback=False) is True
    for verb in ("Frobnicate", "Write", ""):
        assert allow_uri(editor, verb, "/v1.0/processes", session=db_session, group_fallback=False) is False


def test_celery_control_routes_need_create(client, db_session):
    """Control routes are POSTs, so the grant names "create"; there is no "write" action."""
    from m8flow_backend.authorization import _method_to_action

    admin = _provision(db_session, username="admin-action-test", groups=["super-admin"])
    assert _method_to_action("POST") == "create"
    for path in ("/v1.0/m8flow/celery/control/revoke", "/v1.0/m8flow/celery/control/rate-limit"):
        assert allow_uri(admin, "POST", path, session=db_session) is True


def _provision(db_session, *, username: str, groups: list[str], tenant_id: str = "t1"):
    from m8flow_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(db_session, username=username, service=_SERVICE, service_id=username)
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    identity.import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(user)
    return user


def _headers(client, user, *, tenant_id: str = "t1"):
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return {"Authorization": f"Bearer {encode_auth_token(user=user)}"}


@pytest.mark.parametrize("method,path", CELERY_ROUTES)
def test_unauthenticated_is_401(client, method, path):
    assert _call(client, method, path).status_code == 401


@pytest.mark.parametrize("role", ["editor", "reviewer", "tenant-admin"])
def test_tenant_roles_are_forbidden_on_every_route(client, db_session, role):
    user = _provision(db_session, username=f"u-{role}", groups=[f"t1:{role}"])
    headers = _headers(client, user)
    for method, path in CELERY_ROUTES:
        response = _call(client, method, path, headers=headers)
        assert response.status_code == 403, (role, method, path, response.get_json())
        assert response.get_json()["error_code"] == "permission_denied", (role, path)


def test_super_admin_passes_the_gate_on_every_route(client, db_session):
    user = _provision(db_session, username="root", groups=["super-admin"])
    headers = _headers(client, user)
    for method, path in CELERY_ROUTES:
        # Monitoring, history and control are all off in unit tests; that is not an
        # authorization denial.
        response = _call(client, method, path, headers=headers)
        assert response.status_code not in (401,), (method, path)
        assert response.get_json().get("error_code") not in ("permission_denied", "forbidden"), (method, path)


@pytest.mark.parametrize("role", ["editor", "tenant-admin"])
def test_permissions_check_matches_what_the_routes_enforce(client, db_session, role):
    """The designer shows the Celery page and its actions from POST /permissions-check.
    It must not report access via the group fallback that the routes turn off."""
    user = _provision(db_session, username=f"u-{role}", groups=[f"t1:{role}"])
    response = client.post(
        "/v1.0/permissions-check",
        json={"requests_to_check": {"/m8flow/celery/overview": ["GET"], "/m8flow/celery/control/revoke": ["POST"]}},
        headers=_headers(client, user),
    )
    assert response.status_code == 200
    results = response.get_json()["results"]
    assert results["/m8flow/celery/overview"]["GET"] is False
    assert results["/m8flow/celery/control/revoke"]["POST"] is False


def test_permissions_check_allows_super_admin(client, db_session):
    user = _provision(db_session, username="root", groups=["super-admin"])
    response = client.post(
        "/v1.0/permissions-check",
        json={"requests_to_check": {"/m8flow/celery/overview": ["GET"], "/m8flow/celery/control/revoke": ["POST"]}},
        headers=_headers(client, user),
    )
    results = response.get_json()["results"]
    assert results["/m8flow/celery/overview"]["GET"] is True
    assert results["/m8flow/celery/control/revoke"]["POST"] is True
