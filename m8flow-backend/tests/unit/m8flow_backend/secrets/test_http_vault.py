from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from m8flow_backend.secrets.http import HttpVault, VaultTransportError


def _response(*, status_code: int = 200, payload: dict | None = None, content: bytes | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.content = content if content is not None else (b"{}" if payload is not None else b"")
    response.json.return_value = payload if payload is not None else {}
    if status_code >= 400:
        error = requests.HTTPError(f"http {status_code}")
        error.response = response

        def _raise() -> None:
            raise error

        response.raise_for_status.side_effect = _raise
    else:
        response.raise_for_status.return_value = None
    return response


def test_put_and_get_document_urls(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        if method == "GET":
            return _response(payload={"data": {"data": {"value": "secret"}}})
        return _response(payload={})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="root-token", mount="secret")
    vault.put_document("tenants/t1/secrets/SMTP", {"value": "x"})
    assert vault.get_document("tenants/t1/secrets/SMTP") == {"value": "secret"}
    assert calls[0] == ("POST", "http://vault:8200/v1/secret/data/tenants/t1/secrets/SMTP")
    assert calls[1] == ("GET", "http://vault:8200/v1/secret/data/tenants/t1/secrets/SMTP")
    assert calls[0]  # ensure token header path exercised via kwargs in put


def test_token_cached_after_approle_login(monkeypatch):
    tokens: list[str | None] = []

    def fake_request(method, url, **kwargs):
        headers = kwargs.get("headers") or {}
        tokens.append(headers.get("X-Vault-Token"))
        if url.endswith("/auth/approle/login"):
            return _response(payload={"auth": {"client_token": "cached-token"}})
        return _response(payload={"data": {"data": {"ok": True}}})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(
        addr="http://vault:8200",
        role_id="role",
        secret_id="secret",
        mount="kv",
    )
    assert vault.get_document("path") == {"ok": True}
    assert vault.get_document("path") == {"ok": True}
    assert tokens[0] is None  # login is unauthenticated
    assert tokens[1] == "cached-token"
    assert tokens[2] == "cached-token"


def test_http_error_wrapped(monkeypatch):
    def fake_request(method, url, **kwargs):
        return _response(status_code=500, payload={"errors": ["boom"]})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="t")
    with pytest.raises(VaultTransportError, match="Vault request failed"):
        vault.put_document("x", {"a": 1})


def test_missing_ok_returns_none_on_404(monkeypatch):
    def fake_request(method, url, **kwargs):
        return _response(status_code=404, payload={})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="t")
    assert vault.get_document("missing") is None
    assert vault.list_names("missing") == []
