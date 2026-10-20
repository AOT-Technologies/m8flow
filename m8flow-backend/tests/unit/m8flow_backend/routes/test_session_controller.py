"""``GET /v1.0/m8flow/session`` -- the provider-neutral session description
(authProvider-analysis redesign). Additive endpoint; nothing existing calls it.
"""
from __future__ import annotations

from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, TokenInvalid
from m8flow_backend.integrations.auth.base.models import TenantRef, VerifiedClaims


class _Provider:
    def __init__(self, *, master: bool = False, invalid: bool = False, unavailable: bool = False):
        self.master = master
        self.invalid = invalid
        self.unavailable = unavailable
        self.tokens: list[str] = []

    def verify_token(self, token: str) -> VerifiedClaims:
        self.tokens.append(token)
        if self.invalid:
            raise TokenInvalid("nope")
        if self.unavailable:
            raise ProviderUnavailable("jwks down")
        return VerifiedClaims(
            subject="editor-sub",
            issuer="https://example.test/realms/m8flow",
            username="editor",
            email="editor@example.test",
            active_tenant_ref=TenantRef(id="t1", alias="acme"),
        )

    def is_master_issuer(self, claims):
        return self.master


def _install(monkeypatch, provider):
    monkeypatch.setattr("m8flow_backend.routes.session_controller.get_auth_provider", lambda: provider)


def test_session_requires_a_token(client, monkeypatch):
    _install(monkeypatch, _Provider())
    response = client.get("/v1.0/m8flow/session")
    assert response.status_code == 401
    assert response.get_json()["error_code"] == "not_authenticated"


def test_session_rejects_an_invalid_token(client, monkeypatch):
    _install(monkeypatch, _Provider(invalid=True))
    client.set_cookie("access_token", "bad")
    response = client.get("/v1.0/m8flow/session")
    assert response.status_code == 401


def test_session_reports_an_idp_outage_as_503_not_401(client, monkeypatch):
    _install(monkeypatch, _Provider(unavailable=True))
    client.set_cookie("access_token", "good")
    response = client.get("/v1.0/m8flow/session")
    assert response.status_code == 503
    assert response.get_json()["error_code"] == "identity_provider_unavailable"


def test_session_describes_the_cookie_session(client, monkeypatch):
    provider = _Provider()
    _install(monkeypatch, provider)
    client.set_cookie("access_token", "cookie-token")
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, "t1")
    response = client.get("/v1.0/m8flow/session")
    assert response.status_code == 200
    body = response.get_json()
    assert body["username"] == "editor"
    assert body["subject"] == "editor-sub"
    assert body["trust_domain"] == "shared"
    assert body["is_platform_session"] is False
    assert body["selected_tenant"] == "t1"
    assert body["token_active_tenant"] == {"id": "t1", "alias": "acme", "name": None}
    assert body["switch_mode"] == "remint"
    assert set(body["capabilities"]) == {
        "user_admin",
        "tenant_admin",
        "group_admin",
        "role_admin",
        "directory_admin",
        "provisioning",
    }
    assert provider.tokens == ["cookie-token"]


def test_session_prefers_bearer_and_reports_platform_sessions(client, monkeypatch):
    provider = _Provider(master=True)
    _install(monkeypatch, provider)
    client.set_cookie("access_token", "cookie-token")
    response = client.get("/v1.0/m8flow/session", headers={"Authorization": "Bearer header-token"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["is_platform_session"] is True
    assert body["trust_domain"] == "platform"
    assert body["selected_tenant"] is None
    assert provider.tokens == ["header-token"]
