from __future__ import annotations

import base64

from flask import Flask

import m8flow_backend.services.tenant_context_middleware as tenant_context_module


def test_resolve_tenant_id_prefers_selected_tenant_cookie_for_shared_realm(monkeypatch) -> None:
    app = Flask(__name__)
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-users")
    monkeypatch.setattr(
        tenant_context_module.AuthorizationService,
        "should_disable_auth_for_request",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        tenant_context_module,
        "_tenant_from_jwt_claim_cached",
        lambda *, allow_decode: None,
    )
    monkeypatch.setattr(tenant_context_module, "_tenant_from_context_var", lambda: None)

    with app.test_request_context(
        "/v1.0/tasks",
        environ_overrides={
            "HTTP_COOKIE": "authentication_identifier=shared-users; m8flow_selected_tenant=tenant-a-id"
        },
    ):
        assert tenant_context_module._resolve_tenant_id() == "tenant-a-id"


def test_resolve_tenant_id_does_not_treat_configured_admin_realm_as_tenant(monkeypatch) -> None:
    app = Flask(__name__)
    monkeypatch.setenv("M8FLOW_KEYCLOAK_MASTER_REALM", "ops-admin")
    monkeypatch.setattr(
        tenant_context_module.AuthorizationService,
        "should_disable_auth_for_request",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(
        tenant_context_module,
        "_tenant_from_jwt_claim_cached",
        lambda *, allow_decode: None,
    )
    monkeypatch.setattr(tenant_context_module, "_tenant_from_context_var", lambda: None)

    state = base64.b64encode(
        bytes(str({"authentication_identifier": "ops-admin"}), "utf-8")
    ).decode("utf-8")

    with app.test_request_context(
        f"/v1.0/login_return?state={state}",
        environ_overrides={"HTTP_COOKIE": "m8flow_selected_tenant=tenant-a-id"},
    ):
        assert tenant_context_module._resolve_tenant_id() is None
