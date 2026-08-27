from __future__ import annotations

import pytest
from flask import Flask
from flask import g

from m8flow_backend.routes.workflow_write_guard import enforce_super_admin_workflow_write_tenant
from m8flow_backend.services import tenant_context_middleware


@pytest.fixture()
def app() -> Flask:
    flask_app = Flask(__name__)

    @flask_app.post("/workflow-write", endpoint="process_model_create")
    def workflow_write():
        return "ok"

    @flask_app.get("/workflow-read", endpoint="process_model_show")
    def workflow_read():
        return "ok"

    return flask_app


def test_super_admin_workflow_write_requires_concrete_tenant(app: Flask) -> None:
    from spiffworkflow_backend.exceptions.api_error import ApiError

    with app.test_request_context("/workflow-write", method="POST"):
        g._m8flow_super_admin_request = True

        with pytest.raises(ApiError, match="Select a tenant") as exc_info:
            enforce_super_admin_workflow_write_tenant()

    assert exc_info.value.error_code == "tenant_required"
    assert exc_info.value.status_code == 400


def test_super_admin_workflow_write_allows_selected_tenant(app: Flask) -> None:
    with app.test_request_context("/workflow-write", method="POST"):
        g._m8flow_super_admin_request = True
        g.m8flow_tenant_id = "tenant-a"

        assert enforce_super_admin_workflow_write_tenant() is None


def test_workflow_read_is_not_blocked_for_super_admin_without_tenant(app: Flask) -> None:
    with app.test_request_context("/workflow-read", method="GET"):
        g._m8flow_super_admin_request = True

        assert enforce_super_admin_workflow_write_tenant() is None


def test_master_super_admin_header_precedes_master_realm_global_resolution(monkeypatch, app: Flask) -> None:
    monkeypatch.setattr(tenant_context_middleware, "_tenant_from_jwt_claim_cached", lambda *, allow_decode: None)
    monkeypatch.setattr(tenant_context_middleware, "_is_master_super_admin_request", lambda: True)

    with app.test_request_context("/workflow-write", headers={"X-M8Flow-Tenant-Id": "tenant-a"}):
        g._m8flow_decoded_token = {"iss": "http://localhost:7002/realms/master"}

        resolution = tenant_context_middleware._resolve_tenant_details()

    assert resolution["tenant_id"] == "tenant-a"
    assert resolution["source"] == "request_header"
