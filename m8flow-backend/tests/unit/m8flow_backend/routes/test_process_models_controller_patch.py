# m8flow-backend/tests/unit/m8flow_backend/routes/test_process_models_controller_patch.py
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask, g

from m8flow_backend.routes.process_models_controller_patch import prepare_process_model_create_body_for_upstream
from m8flow_backend.tenancy import clear_tenant_context
from spiffworkflow_backend.exceptions.api_error import ApiError


@pytest.fixture()
def app() -> Flask:
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    return flask_app


def test_prepare_super_admin_strips_m8f_and_locks_g(app, monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.routes.process_models_controller_patch.db.session.get",
        lambda model, pk: SimpleNamespace(id=pk, name="n", slug="s", created_by="u") if pk == "abil" else None,
    )

    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        out = prepare_process_model_create_body_for_upstream(
            {"display_name": "D", "description": "", "m8f_tenant_id": "abil"},
        )
        assert "m8f_tenant_id" not in out
        assert getattr(g, "m8flow_tenant_id", None) == "abil"
    clear_tenant_context()


def test_prepare_non_super_admin_pops_m8f_without_locking_g(app, monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.routes.process_models_controller_patch.db.session.get",
        lambda model, pk: SimpleNamespace(id=pk),
    )

    with app.test_request_context("/"):
        if hasattr(g, "m8flow_tenant_id"):
            delattr(g, "m8flow_tenant_id")
        out = prepare_process_model_create_body_for_upstream(
            {"display_name": "D", "m8f_tenant_id": "abil"},
        )
        assert "m8f_tenant_id" not in out
        assert getattr(g, "m8flow_tenant_id", None) is None


def test_prepare_super_admin_unknown_tenant_raises(app, monkeypatch) -> None:
    monkeypatch.setattr(
        "m8flow_backend.routes.process_models_controller_patch.db.session.get",
        lambda model, pk: None,
    )

    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        with pytest.raises(ApiError) as exc:
            prepare_process_model_create_body_for_upstream({"m8f_tenant_id": "nope"})
        assert exc.value.error_code == "tenant_not_found"
