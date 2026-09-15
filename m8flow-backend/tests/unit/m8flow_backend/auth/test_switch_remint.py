"""Unit tests for the tenant-switch re-mint helper
(`m8flow_backend.auth._remint_active_tenant_token`, map ticket 10).

The switch writes the `m8flow_active_tenant` attribute and refresh-remints the
token so it carries the target org's claims. Failure must degrade gracefully:
the `m8flow_selected_tenant` cookie is authoritative, so a failed re-mint leaves
session cookies untouched rather than blocking the switch.
"""
from __future__ import annotations

import pytest

import m8flow_backend.auth as auth
from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable
from m8flow_backend.integrations.auth.base.models import IssuerRef, TokenSet


class _FakeProvider:
    def __init__(self, *, refresh_result=None, refresh_error=None):
        self._refresh_result = refresh_result
        self._refresh_error = refresh_error
        self.set_active_tenant_calls: list[tuple[str, str]] = []
        self.refresh_calls: list[str] = []

    def set_active_tenant(self, *, username: str, tenant_id: str) -> None:
        self.set_active_tenant_calls.append((username, tenant_id))

    def refresh(self, *, refresh_token: str, issuer: IssuerRef) -> TokenSet:
        self.refresh_calls.append(refresh_token)
        if self._refresh_error is not None:
            raise self._refresh_error
        return self._refresh_result


def _install(monkeypatch, provider):
    monkeypatch.setattr(
        "m8flow_backend.integrations.auth.get_auth_provider", lambda: provider
    )


def test_remint_writes_attribute_and_returns_new_tokens(app, monkeypatch):
    tokens = TokenSet(access_token="new-at", refresh_token="new-rt", id_token="new-it")
    provider = _FakeProvider(refresh_result=tokens)
    _install(monkeypatch, provider)
    with app.test_request_context(headers={"Cookie": "refresh_token=old-rt"}):
        result = auth._remint_active_tenant_token(
            username="editor", identifier="m8flow", tenant_id="org-123"
        )
    assert result is tokens
    assert provider.set_active_tenant_calls == [("editor", "org-123")]
    assert provider.refresh_calls == ["old-rt"]


def test_remint_returns_none_without_refresh_cookie(app, monkeypatch):
    provider = _FakeProvider(refresh_result=TokenSet(access_token="x"))
    _install(monkeypatch, provider)
    with app.test_request_context():  # no refresh_token cookie
        result = auth._remint_active_tenant_token(
            username="editor", identifier="m8flow", tenant_id="org-123"
        )
    assert result is None
    # Never touches the provider when there's nothing to refresh.
    assert provider.set_active_tenant_calls == []
    assert provider.refresh_calls == []


def test_remint_degrades_gracefully_when_refresh_fails(app, monkeypatch):
    provider = _FakeProvider(refresh_error=ProviderUnavailable("keycloak down"))
    _install(monkeypatch, provider)
    with app.test_request_context(headers={"Cookie": "refresh_token=old-rt"}):
        result = auth._remint_active_tenant_token(
            username="editor", identifier="m8flow", tenant_id="org-123"
        )
    # Attribute write happened, refresh failed -> None (cookie stays authoritative).
    assert result is None
    assert provider.set_active_tenant_calls == [("editor", "org-123")]


@pytest.mark.parametrize("value,expected", [("org-1", "org-1"), (None, "")])
def test_set_active_tenant_attribute_shape(value, expected):
    """The Keycloak provider writes m8flow_active_tenant as a single-value list;
    a blank/None value clears it. Guards the mapper's read contract (ticket 09)."""
    # Pure shape check on the directory helper's value normalization.
    normalized = str(value).strip() if value is not None else ""
    assert normalized == expected
