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


def test_versioned_document_read_and_cas_write(monkeypatch):
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            return _response(
                payload={"data": {"data": {"field": "value"}, "metadata": {"version": 4}}}
            )
        return _response(payload={})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="root-token", mount="kv")

    document, version = vault.get_versioned_document("tenant/path")
    assert document == {"field": "value"}
    assert version == 4

    vault.put_document("tenant/path", {"field": "next"}, cas=version)
    assert calls[1][2]["json"] == {
        "data": {"field": "next"},
        "options": {"cas": 4},
    }


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


def test_read_policy_returns_policy_rules_and_none_when_missing(monkeypatch):
    responses = [
        _response(payload={"name": "tenant-policy", "rules": 'path "kv/*" {}'}),
        _response(status_code=404),
    ]
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        return responses.pop(0)

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="root-token")

    assert vault.read_policy("tenant-policy") == 'path "kv/*" {}'
    assert vault.read_policy("missing") is None
    assert calls == [
        ("GET", "http://vault:8200/v1/sys/policy/tenant-policy"),
        ("GET", "http://vault:8200/v1/sys/policy/missing"),
    ]


def test_delete_tree_removes_only_leaf_documents_under_tenant_root(monkeypatch):
    calls: list[tuple[str, str]] = []
    listings = {
        "http://vault:8200/v1/kv/metadata/m8flow/tenants/t1/secrets": [
            "configuration-variable/",
            "legacy-key",
        ],
        "http://vault:8200/v1/kv/metadata/m8flow/tenants/t1/secrets/configuration-variable": [
            "abc-uuid",
        ],
    }

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        if method == "LIST":
            names = listings.get(url)
            return _response(status_code=404) if names is None else _response(
                payload={"data": {"keys": names}}
            )
        return _response(status_code=204)

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="tenant-token", mount="kv")
    vault.delete_tree("m8flow/tenants/t1/secrets")

    deleted = [url for method, url in calls if method == "DELETE"]
    assert deleted == [
        "http://vault:8200/v1/kv/metadata/m8flow/tenants/t1/secrets/configuration-variable/abc-uuid",
        "http://vault:8200/v1/kv/metadata/m8flow/tenants/t1/secrets/legacy-key",
    ]


def test_delete_tree_empty_tenant_root_does_not_delete_root_metadata(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        return _response(status_code=404)

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="tenant-token", mount="kv")
    vault.delete_tree("m8flow/tenants/t1/secrets")

    assert calls == [
        ("LIST", "http://vault:8200/v1/kv/metadata/m8flow/tenants/t1/secrets")
    ]
