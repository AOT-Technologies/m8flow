# m8flow-backend/tests/unit/m8flow_backend/services/test_process_model_service_patch.py
from __future__ import annotations

import json
import os

import pytest
from flask import Flask, g

from m8flow_backend.tenancy import clear_tenant_context, get_context_tenant_id
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.exceptions.process_entity_not_found_error import ProcessEntityNotFoundError
from spiffworkflow_backend.services.file_system_service import FileSystemService
from spiffworkflow_backend.services.process_model_service import ProcessModelService


@pytest.fixture(autouse=True)
def _isolate_process_model_service_patch():
    from m8flow_backend.services import process_model_service_patch as pmp

    pmp.reset()
    clear_tenant_context()
    yield
    pmp.reset()
    clear_tenant_context()


def _write_minimal_process_group(dir_path: str) -> None:
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, FileSystemService.PROCESS_GROUP_JSON_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"display_name": "G", "description": ""}, f)


def _write_minimal_process_model(dir_path: str) -> None:
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, FileSystemService.PROCESS_MODEL_JSON_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"display_name": "M", "description": ""}, f)


@pytest.fixture()
def tenant_bpmn_tree(tmp_path):
    """<base>/abil/abil/ + model test, and <base>/other/foo/ group only."""
    base = tmp_path / "bpmn_specs"
    base.mkdir(parents=True, exist_ok=True)
    abil_root = base / "abil"
    abil_root.mkdir()
    _write_minimal_process_group(str(abil_root / "abil"))
    _write_minimal_process_model(str(abil_root / "abil" / "test"))
    other_root = base / "other"
    other_root.mkdir()
    _write_minimal_process_group(str(other_root / "foo"))
    return str(base)


@pytest.fixture()
def patched_services(app: Flask, tenant_bpmn_tree: str, monkeypatch):
    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "1")
    app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = tenant_bpmn_tree
    from m8flow_backend.services import file_system_service_patch as fsp
    from m8flow_backend.services import process_model_service_patch as pmp

    fsp._PATCHED = False
    fsp._ORIGINALS.clear()
    pmp.reset()
    with app.app_context():
        fsp.apply()
        pmp.apply()
        yield


def test_super_admin_get_process_model_resolves_tenant_and_locks_context(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        pm = ProcessModelService.get_process_model("abil/test")
        assert pm.id == "abil/test"
        assert getattr(g, "m8flow_tenant_id", None) == "abil"
        assert get_context_tenant_id() == "abil"


def test_super_admin_is_process_model_identifier_locks_tenant(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        assert ProcessModelService.is_process_model_identifier("abil/test") is True
        assert g.m8flow_tenant_id == "abil"


def test_super_admin_is_process_group_identifier_locks_tenant(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        assert ProcessModelService.is_process_group_identifier("abil") is True
        assert g.m8flow_tenant_id == "abil"


def test_super_admin_get_process_group_locks_tenant(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        group = ProcessModelService.get_process_group("abil")
        assert group.id == "abil"
        assert g.m8flow_tenant_id == "abil"


def test_super_admin_unknown_model_no_tenant_lock(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        with pytest.raises(ProcessEntityNotFoundError):
            ProcessModelService.get_process_model("nope/nope")
        assert getattr(g, "m8flow_tenant_id", None) is None


def test_non_super_admin_no_cross_tenant_scan(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g.m8flow_tenant_id = "other"
        assert ProcessModelService.is_process_model_identifier("abil/test") is False


def test_super_admin_preset_tenant_skips_scan_other_tenant_model(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    """When g.m8flow_tenant_id is already set, resolver must not override to another tenant."""
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True
        g.m8flow_tenant_id = "other"

        with pytest.raises(ProcessEntityNotFoundError):
            ProcessModelService.get_process_model("abil/test")


def test_super_admin_process_model_mutators_are_forbidden(app: Flask, patched_services) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        with pytest.raises(ApiError) as exc:
            ProcessModelService.process_model_delete("abil/test")
        assert exc.value.error_code == "forbidden"

        with pytest.raises(ApiError) as exc:
            ProcessModelService.process_group_delete("abil")
        assert exc.value.error_code == "forbidden"


class _FakeGroup:
    def __init__(self, group_id: str) -> None:
        self.id = group_id

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"_FakeGroup({self.id!r})"


class _FakeModel:
    def __init__(self, model_id: str) -> None:
        self.id = model_id


@pytest.fixture()
def stub_upstream_services(app: Flask, tenant_bpmn_tree: str, monkeypatch):
    """Patch upstream ProcessModelService methods to return per-tenant fakes.

    Each call to the original ``get_process_groups_for_api`` / ``get_process_models_for_api``
    receives whatever tenant context was active and is expected to return that tenant's
    items.  We simulate this by reading ``g.m8flow_tenant_id`` and returning a fixed
    mapping.
    """
    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "1")
    app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = tenant_bpmn_tree
    from m8flow_backend.services import process_model_service_patch as pmp

    pmp.reset()

    groups_by_tenant = {
        "abil": [_FakeGroup("abil")],
        "other": [_FakeGroup("other")],
    }
    models_by_tenant = {
        "abil": [_FakeModel("abil/test")],
        "other": [],
    }

    def fake_groups(cls, process_group_id=None, user=None):
        tid = getattr(g, "m8flow_tenant_id", None)
        return list(groups_by_tenant.get(tid, []))

    def fake_models(
        cls,
        user=None,
        process_group_id=None,
        recursive=False,
        filter_runnable_by_user=False,
        filter_runnable_as_extension=False,
        include_files=False,
    ):
        tid = getattr(g, "m8flow_tenant_id", None)
        return list(models_by_tenant.get(tid, []))

    monkeypatch.setattr(
        ProcessModelService,
        "get_process_groups_for_api",
        classmethod(fake_groups),
        raising=False,
    )
    monkeypatch.setattr(
        ProcessModelService,
        "get_process_models_for_api",
        classmethod(fake_models),
        raising=False,
    )

    with app.app_context():
        pmp.apply()
        yield
    pmp.reset()


def test_super_admin_get_process_groups_for_api_merges_across_tenants(
    app: Flask, stub_upstream_services,
) -> None:
    """Regression: super-admin must see process groups from every tenant on disk.

    Before the file_system_service_patch fix, the cross-tenant loop in
    ``patched_get_process_groups_for_api`` ran but every iteration resolved to the
    empty ``__m8flow_global__`` subdir because the global-request short-circuit fired
    inside ``_tenant_bpmn_root``. After the fix, both tenants' groups appear.
    """
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_global_request = True
        g._m8flow_tenant_context_exempt_request = True

        groups = ProcessModelService.get_process_groups_for_api()
        group_ids = sorted(getattr(group, "id", None) for group in groups)
        assert group_ids == ["abil", "other"]
        tenant_ids = {getattr(group, "tenant_id", None) for group in groups}
        assert tenant_ids == {"abil", "other"}
        tenant_map = getattr(g, "_m8flow_process_group_tenant_map", {})
        assert tenant_map.get("abil") == "abil"
        assert tenant_map.get("other") == "other"


def test_super_admin_get_process_groups_honors_tenant_filter(
    app: Flask, stub_upstream_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_global_request = True
        g._m8flow_tenant_context_exempt_request = True
        g._m8flow_process_tenant_filter = "abil"

        groups = ProcessModelService.get_process_groups_for_api()
        group_ids = [getattr(group, "id", None) for group in groups]
        assert group_ids == ["abil"]


def test_non_super_admin_get_process_groups_stamps_current_tenant(
    app: Flask, stub_upstream_services,
) -> None:
    with app.test_request_context("/"):
        g.m8flow_tenant_id = "abil"
        groups = ProcessModelService.get_process_groups_for_api()
        for group in groups:
            assert getattr(group, "tenant_id", None) == "abil"


def test_super_admin_get_process_models_merges_and_stamps_tenant(
    app: Flask, stub_upstream_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_global_request = True
        g._m8flow_tenant_context_exempt_request = True

        models = ProcessModelService.get_process_models_for_api(user=None, recursive=True)
        model_ids = [getattr(m, "id", None) for m in models]
        assert "abil/test" in model_ids
        for m in models:
            assert getattr(m, "tenant_id", None) == "abil"
        model_map = getattr(g, "_m8flow_process_model_tenant_map", {})
        assert model_map.get("abil/test") == "abil"
