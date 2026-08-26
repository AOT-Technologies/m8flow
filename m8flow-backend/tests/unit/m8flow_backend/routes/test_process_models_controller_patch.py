# m8flow-backend/tests/unit/m8flow_backend/routes/test_process_models_controller_patch.py
from __future__ import annotations

import pytest
from flask import Flask, g

from m8flow_backend.routes.process_models_controller_patch import prepare_process_model_create_body_for_upstream
from m8flow_backend.tenancy import clear_tenant_context


@pytest.fixture()
def app() -> Flask:
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    return flask_app


def test_prepare_super_admin_pops_m8f_without_mutating_request_tenant(app) -> None:
    with app.test_request_context("/"):
        g._m8flow_super_admin_request = True
        out = prepare_process_model_create_body_for_upstream(
            {"display_name": "D", "description": "", "m8f_tenant_id": "abil"},
        )
        assert out == {"display_name": "D", "description": ""}
        assert getattr(g, "m8flow_tenant_id", None) is None
    clear_tenant_context()


def test_prepare_non_super_admin_pops_m8f_without_locking_g(app) -> None:
    with app.test_request_context("/"):
        if hasattr(g, "m8flow_tenant_id"):
            delattr(g, "m8flow_tenant_id")
        out = prepare_process_model_create_body_for_upstream(
            {"display_name": "D", "m8f_tenant_id": "abil"},
        )
        assert "m8f_tenant_id" not in out
        assert getattr(g, "m8flow_tenant_id", None) is None
