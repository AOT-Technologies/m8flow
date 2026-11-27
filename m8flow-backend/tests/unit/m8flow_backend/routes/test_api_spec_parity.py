from __future__ import annotations

import hashlib
import json
from importlib import import_module
from pathlib import Path

import pytest
import yaml

_HTTP = {"get", "post", "put", "patch", "delete"}
_SPEC_DIR = Path(__file__).resolve().parents[4] / "src" / "m8flow_backend"
_SPEC_FILES = ("api-v1.yml", "api-v2.yml")
# SHA-256 of the pre-versioning ``api.yml`` contract after removing
# documentation-only fields and deployment/version metadata. Keep this fixed
# so V1 cannot silently drift when V1 and V2 are edited together.
_LEGACY_V1_CONTRACT_SHA256 = "e2d16f6500c5183c42f38c55ebc0b8f20409c44d0d375a69728447100837d916"
_NON_CONTRACT_FIELDS = {"description", "summary", "externalDocs"}


def _document(spec_file: str) -> dict:
    return yaml.safe_load((_SPEC_DIR / spec_file).read_text(encoding="utf-8"))


def _contract_digest(document: dict) -> str:
    """Hash the OpenAPI wire contract while ignoring prose and version metadata."""

    def without_documentation(value):
        if isinstance(value, dict):
            return {
                key: without_documentation(item)
                for key, item in value.items()
                if key not in _NON_CONTRACT_FIELDS
            }
        if isinstance(value, list):
            return [without_documentation(item) for item in value]
        return value

    contract = without_documentation(document)
    contract.get("info", {}).pop("version", None)
    # Connexion supplies the mounted base path at runtime; it is deployment
    # metadata and differs by version, not part of the endpoint contract.
    contract.pop("servers", None)
    canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_v1_contract_matches_the_pre_versioning_api_baseline():
    """Protect existing V1 consumers from contract drift across releases.

    The baseline was calculated from the original ``api.yml`` before it was
    split into ``api-v1.yml`` and ``api-v2.yml``. To intentionally change the
    V1 contract, review compatibility first, then update the expected digest.
    """
    assert _contract_digest(_document("api-v1.yml")) == _LEGACY_V1_CONTRACT_SHA256


def _operations(spec_file: str) -> list[tuple[str, str, str]]:
    document = _document(spec_file)
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
    """The app registers both versioned specs and resolves all their operations."""
    assert connexion_app is not None
    for spec_file in _SPEC_FILES:
        assert _operations(spec_file), f"{spec_file} declares no operations"


def test_every_operation_id_resolves_to_a_callable():
    """Spec-driven guard mirroring what Connexion's Resolver does, but with a
    precise per-operation failure message (add_api's error is less specific)."""
    for spec_file in _SPEC_FILES:
        unresolved = []
        for method, raw_path, operation_id in _operations(spec_file):
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
        assert not unresolved, f"{spec_file} operationIds not resolvable:\n" + "\n".join(unresolved)


_TENANT_ROLE_ENUM = ["tenant-admin", "editor", "integrator", "reviewer", "submitter", "viewer"]


@pytest.mark.parametrize("spec_file", _SPEC_FILES)
def test_tenant_role_enums_include_submitter(spec_file):
    """Member-role path params and TenantMember.roles omitted submitter while
    group-role params and the service layer already accept it."""
    document = _document(spec_file)
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
