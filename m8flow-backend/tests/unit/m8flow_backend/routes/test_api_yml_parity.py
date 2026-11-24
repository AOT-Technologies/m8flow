from __future__ import annotations

from importlib import import_module
from pathlib import Path

import yaml

_HTTP = {"get", "post", "put", "patch", "delete"}
_SPEC = Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "api.yml"


def _operations() -> list[tuple[str, str, str]]:
    document = yaml.safe_load(_SPEC.read_text(encoding="utf-8"))
    ops = []
    for raw_path, item in (document.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            if method.lower() not in _HTTP or not isinstance(operation, dict):
                continue
            ops.append((method.upper(), raw_path, operation.get("operationId")))
    return ops


def test_connexion_app_builds_and_registers_every_operation(connexion_app):
    """create_app() calls add_api(api.yml); Connexion's resolver imports every
    operationId at registration time, so a FlaskApp that builds is proof every
    api.yml operation is wired to a real handler. The fixture builds it."""
    assert connexion_app is not None
    assert _operations(), "api.yml declares no operations"


def test_every_operation_id_resolves_to_a_callable():
    """Spec-driven guard mirroring what Connexion's Resolver does, but with a
    precise per-operation failure message (add_api's error is less specific)."""
    unresolved = []
    for method, raw_path, operation_id in _operations():
        if not isinstance(operation_id, str) or not operation_id.strip():
            unresolved.append(f"{method} {raw_path}: missing operationId")
            continue
        module_name, _, attr = operation_id.rpartition(".")
        try:
            view = getattr(import_module(module_name), attr, None)
        except Exception as exc:  # noqa: BLE001 - report which op failed
            unresolved.append(f"{method} {raw_path} ({operation_id}): import error {exc!r}")
            continue
        if not callable(view):
            unresolved.append(f"{method} {raw_path} ({operation_id}): not callable")
    assert not unresolved, "api.yml operationIds not resolvable:\n" + "\n".join(unresolved)


def test_every_openapi_operation_documents_the_api_version_header():
    document = yaml.safe_load(_SPEC.read_text(encoding="utf-8"))
    parameter_ref = "#/components/parameters/ApiVersion"
    parameter = document["components"]["parameters"]["ApiVersion"]

    assert parameter["name"] == "X-M8Flow-API-Version"
    assert parameter["in"] == "header"
    assert parameter["required"] is False
    assert parameter["schema"]["default"] == "1.0"

    missing = []
    for raw_path, path_item in document["paths"].items():
        path_parameters = path_item.get("parameters", [])
        if not any(item.get("$ref") == parameter_ref for item in path_parameters):
            missing.append(raw_path)

    assert not missing, "API version header is undocumented for paths:\n" + "\n".join(missing)


_TENANT_ROLE_ENUM = ["tenant-admin", "editor", "integrator", "reviewer", "submitter", "viewer"]


def test_tenant_role_enums_include_submitter():
    """Member-role path params and TenantMember.roles omitted submitter while
    group-role params and the service layer already accept it."""
    document = yaml.safe_load(_SPEC.read_text(encoding="utf-8"))
    paths = document["paths"]
    for raw_path in (
        "/tenants/{tenant_id}/members/{username}/roles/{role_name}",
        "/tenants/{tenant_id}/groups/{group_name}/roles/{role_name}",
    ):
        for method in ("put", "delete"):
            params = paths[raw_path][method]["parameters"]
            role_param = next(p for p in params if p.get("name") == "role_name")
            assert role_param["schema"]["enum"] == _TENANT_ROLE_ENUM, f"{method} {raw_path}"

    member_roles = document["components"]["schemas"]["TenantMember"]["properties"]["roles"]["items"]["enum"]
    assert member_roles == _TENANT_ROLE_ENUM
