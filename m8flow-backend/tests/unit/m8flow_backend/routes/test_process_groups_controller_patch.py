# m8flow-backend/tests/unit/m8flow_backend/routes/test_process_groups_controller_patch.py
from __future__ import annotations

import pytest
from flask import Flask, g, jsonify, make_response


@pytest.fixture(autouse=True)
def _reset_patch():
    from m8flow_backend.routes import process_groups_controller_patch as patch

    patch.reset()
    yield
    patch.reset()


@pytest.fixture()
def app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def _install_tenant_name_lookup(monkeypatch) -> None:
    """Patch the controller's tenant-name lookup so tests don't need a DB session."""
    from m8flow_backend.routes import process_groups_controller_patch as patch

    name_by_id = {"abil": "Abil Co.", "other": "Other Inc."}

    def fake_lookup(tenant_ids):
        return {tid: name_by_id[tid] for tid in tenant_ids if tid in name_by_id}

    monkeypatch.setattr(patch, "_tenant_name_map", fake_lookup, raising=True)


def test_resolve_tenant_filter_from_request_reads_tenantId(app) -> None:
    from m8flow_backend.routes import process_groups_controller_patch as patch

    with app.test_request_context("/process-groups?tenantId=abil"):
        assert patch._resolve_tenant_filter_from_request() == "abil"


def test_resolve_tenant_filter_from_request_reads_snake_case(app) -> None:
    from m8flow_backend.routes import process_groups_controller_patch as patch

    with app.test_request_context("/process-groups?tenant_id=other"):
        assert patch._resolve_tenant_filter_from_request() == "other"


def test_resolve_tenant_filter_returns_none_when_absent(app) -> None:
    from m8flow_backend.routes import process_groups_controller_patch as patch

    with app.test_request_context("/process-groups"):
        assert patch._resolve_tenant_filter_from_request() is None


def test_enrich_results_uses_g_tenant_map(app, monkeypatch) -> None:
    from m8flow_backend.routes import process_groups_controller_patch as patch

    _install_tenant_name_lookup(monkeypatch)

    payload = {
        "results": [{"id": "abil"}, {"id": "other"}, {"id": "no-tenant"}],
        "pagination": {"count": 3, "total": 3, "pages": 1},
    }

    with app.test_request_context("/process-groups"):
        response = make_response(jsonify(payload), 200)
        g._m8flow_process_group_tenant_map = {"abil": "abil", "other": "other"}
        enriched = patch._enrich_results_with_tenant_info(response)
        data = enriched.get_json()
        by_id = {item["id"]: item for item in data["results"]}
        assert by_id["abil"]["tenantId"] == "abil"
        assert by_id["abil"]["tenantName"] == "Abil Co."
        assert by_id["other"]["tenantId"] == "other"
        assert by_id["other"]["tenantName"] == "Other Inc."
        assert "tenantId" not in by_id["no-tenant"]


def test_enrich_passthrough_when_no_tenant_map(app) -> None:
    from m8flow_backend.routes import process_groups_controller_patch as patch

    payload = {"results": [{"id": "abil"}], "pagination": {}}
    with app.test_request_context("/process-groups"):
        response = make_response(jsonify(payload), 200)
        enriched = patch._enrich_results_with_tenant_info(response)
        data = enriched.get_json()
        assert "tenantId" not in data["results"][0]


def test_enrich_single_response_uses_g_tenant_id(app, monkeypatch) -> None:
    from m8flow_backend.routes import process_groups_controller_patch as patch

    _install_tenant_name_lookup(monkeypatch)

    payload = {"id": "abil", "display_name": "Abil"}
    with app.test_request_context("/process-groups/abil"):
        response = make_response(jsonify(payload), 200)
        g.m8flow_tenant_id = "abil"
        enriched = patch._enrich_single_process_group_response(response)
        data = enriched.get_json()
        assert data["tenantId"] == "abil"
        assert data["tenantName"] == "Abil Co."


def test_enrich_single_response_passthrough_when_no_tenant(app) -> None:
    from m8flow_backend.routes import process_groups_controller_patch as patch

    payload = {"id": "abil"}
    with app.test_request_context("/process-groups/abil"):
        response = make_response(jsonify(payload), 200)
        enriched = patch._enrich_single_process_group_response(response)
        data = enriched.get_json()
        assert "tenantId" not in data
