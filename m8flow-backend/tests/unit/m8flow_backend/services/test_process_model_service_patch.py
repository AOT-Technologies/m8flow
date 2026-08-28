# m8flow-backend/tests/unit/m8flow_backend/services/test_process_model_service_patch.py
from __future__ import annotations

import json
import os

import pytest
from flask import Flask, g

from m8flow_backend.canonical_db import set_canonical_db
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.models.process_model_bpmn_version import ProcessModelBpmnVersionModel  # noqa: F401
from m8flow_backend.tenancy import clear_tenant_context, get_context_tenant_id
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.exceptions.process_entity_not_found_error import ProcessEntityNotFoundError
from spiffworkflow_backend.models.db import add_listeners, db
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
def app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        set_canonical_db(db)
        db.create_all()
        add_listeners()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def tenant_bpmn_tree(tmp_path):
    """<base>/<tenant_id>/<group_path>/... tree with one stale non-live tenant root."""
    base = tmp_path / "bpmn_specs"
    base.mkdir(parents=True, exist_ok=True)
    abil_root = base / "tenant-abil-id"
    abil_root.mkdir()
    _write_minimal_process_group(str(abil_root / "abil"))
    _write_minimal_process_model(str(abil_root / "abil" / "test"))
    other_root = base / "tenant-other-id"
    other_root.mkdir()
    _write_minimal_process_group(str(other_root / "foo"))
    stale_root = base / "stale-tenant"
    stale_root.mkdir()
    _write_minimal_process_group(str(stale_root / "legacy"))
    _write_minimal_process_model(str(stale_root / "legacy" / "test"))
    return str(base)


@pytest.fixture()
def live_tenants(app: Flask):
    with app.app_context():
        db.session.add_all(
            [
                M8flowTenantModel(
                    id="tenant-abil-id",
                    name="Abil",
                    slug="abil",
                    created_by="test",
                    modified_by="test",
                ),
                M8flowTenantModel(
                    id="tenant-other-id",
                    name="Other",
                    slug="other",
                    created_by="test",
                    modified_by="test",
                ),
            ]
        )
        db.session.commit()


@pytest.fixture()
def patched_services(app: Flask, tenant_bpmn_tree: str, live_tenants, monkeypatch):
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
        assert getattr(g, "m8flow_tenant_id", None) == "tenant-abil-id"
        assert getattr(g, "_m8flow_bpmn_root_tenant", None) == "tenant-abil-id"
        assert get_context_tenant_id() == "tenant-abil-id"


def test_super_admin_is_process_model_identifier_locks_tenant(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        assert ProcessModelService.is_process_model_identifier("abil/test") is True
        assert g.m8flow_tenant_id == "tenant-abil-id"
        assert getattr(g, "_m8flow_bpmn_root_tenant", None) == "tenant-abil-id"


def test_super_admin_is_process_group_identifier_locks_tenant(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        assert ProcessModelService.is_process_group_identifier("abil") is True
        assert g.m8flow_tenant_id == "tenant-abil-id"
        assert getattr(g, "_m8flow_bpmn_root_tenant", None) == "tenant-abil-id"


def test_super_admin_get_process_group_locks_tenant(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        group = ProcessModelService.get_process_group("abil")
        assert group.id == "abil"
        assert g.m8flow_tenant_id == "tenant-abil-id"
        assert getattr(g, "_m8flow_bpmn_root_tenant", None) == "tenant-abil-id"


def test_super_admin_unknown_model_no_tenant_lock(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        with pytest.raises(ProcessEntityNotFoundError):
            ProcessModelService.get_process_model("nope/nope")
        assert getattr(g, "m8flow_tenant_id", None) is None


def test_super_admin_ignores_stale_tenant_root_without_live_tenant(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True

        with pytest.raises(ProcessEntityNotFoundError):
            ProcessModelService.get_process_model("legacy/test")
        assert getattr(g, "m8flow_tenant_id", None) is None


def test_non_super_admin_no_cross_tenant_scan(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    with app.test_request_context("/"):
        g.m8flow_tenant_id = "tenant-other-id"
        assert ProcessModelService.is_process_model_identifier("abil/test") is False


def test_super_admin_preset_tenant_skips_scan_other_tenant_model(
    app: Flask, tenant_bpmn_tree: str, patched_services,
) -> None:
    """When g.m8flow_tenant_id is already set, resolver must not override to another tenant."""
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_tenant_context_exempt_request = True
        g.m8flow_tenant_id = "tenant-other-id"

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
    def __init__(
        self,
        group_id: str,
        *,
        process_groups: list["_FakeGroup"] | None = None,
        process_models: list["_FakeModel"] | None = None,
    ) -> None:
        self.id = group_id
        self.process_groups = process_groups or []
        self.process_models = process_models or []

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"_FakeGroup({self.id!r})"


class _FakeModel:
    def __init__(self, model_id: str) -> None:
        self.id = model_id


@pytest.fixture()
def stub_upstream_services(app: Flask, tenant_bpmn_tree: str, live_tenants, monkeypatch):
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

    groups_by_root = {
        "tenant-abil-id": [
            _FakeGroup(
                "abil",
                process_groups=[
                    _FakeGroup(
                        "abil/hr",
                        process_models=[_FakeModel("abil/hr/onboarding")],
                    )
                ],
                process_models=[_FakeModel("abil/test")],
            )
        ],
        "tenant-other-id": [_FakeGroup("other")],
    }
    models_by_root = {
        "tenant-abil-id": [_FakeModel("abil/test")],
        "tenant-other-id": [],
    }

    def fake_groups(cls, process_group_id=None, user=None):
        root = getattr(g, "_m8flow_bpmn_root_tenant", None) or getattr(g, "m8flow_tenant_id", None)
        return list(groups_by_root.get(root, []))

    def fake_models(
        cls,
        user=None,
        process_group_id=None,
        recursive=False,
        filter_runnable_by_user=False,
        filter_runnable_as_extension=False,
        include_files=False,
    ):
        root = getattr(g, "_m8flow_bpmn_root_tenant", None) or getattr(g, "m8flow_tenant_id", None)
        return list(models_by_root.get(root, []))

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
        assert tenant_ids == {"tenant-abil-id", "tenant-other-id"}
        tenant_map = getattr(g, "_m8flow_process_group_tenant_map", {})
        model_map = getattr(g, "_m8flow_process_model_tenant_map", {})
        assert tenant_map.get("abil") == "tenant-abil-id"
        assert tenant_map.get("other") == "tenant-other-id"
        assert tenant_map.get("abil/hr") == "tenant-abil-id"
        assert model_map.get("abil/test") == "tenant-abil-id"
        assert model_map.get("abil/hr/onboarding") == "tenant-abil-id"


def test_super_admin_get_process_groups_honors_tenant_filter(
    app: Flask, stub_upstream_services,
) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        g._m8flow_global_request = True
        g._m8flow_tenant_context_exempt_request = True
        g._m8flow_process_tenant_filter = "tenant-abil-id"

        groups = ProcessModelService.get_process_groups_for_api()
        group_ids = [getattr(group, "id", None) for group in groups]
        assert group_ids == ["abil"]


def test_non_super_admin_get_process_groups_stamps_current_tenant(
    app: Flask, stub_upstream_services,
) -> None:
    with app.test_request_context("/"):
        g.m8flow_tenant_id = "tenant-abil-id"
        g._m8flow_bpmn_root_tenant = "tenant-abil-id"
        groups = ProcessModelService.get_process_groups_for_api()
        for group in groups:
            assert getattr(group, "tenant_id", None) == "tenant-abil-id"


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
            assert getattr(m, "tenant_id", None) == "tenant-abil-id"
        model_map = getattr(g, "_m8flow_process_model_tenant_map", {})
        assert model_map.get("abil/test") == "tenant-abil-id"
