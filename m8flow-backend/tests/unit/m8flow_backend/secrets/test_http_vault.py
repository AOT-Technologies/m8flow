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


def test_write_approle_requires_secret_id_binding(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "m8flow_backend.secrets.http.requests.request",
        lambda method, url, **kwargs: calls.append((method, url, kwargs))
        or _response(payload={}),
    )
    vault = HttpVault(addr="http://vault:8200", token="admin-token")

    vault.write_approle(
        "tenant-role",
        mount="approle",
        token_policies=["tenant-policy"],
        bind_secret_id=True,
        secret_id_num_uses=1,
        secret_id_ttl="10m",
        token_ttl="10m",
        token_max_ttl="30m",
        token_period=0,
    )

    assert calls[0][0:2] == (
        "POST",
        "http://vault:8200/v1/auth/approle/role/tenant-role",
    )
    assert calls[0][2]["json"]["bind_secret_id"] is True
    assert calls[0][2]["json"]["secret_id_num_uses"] == 1
    assert calls[0][2]["json"]["token_period"] == 0


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


def test_approle_login_exposes_conservative_token_cache_deadline(monkeypatch):
    import time

    def fake_request(method, url, **kwargs):
        assert url.endswith("/auth/approle/login")
        return _response(
            payload={"auth": {"client_token": "cached-token", "lease_duration": 600}}
        )

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    before = time.monotonic()
    vault = HttpVault(addr="http://vault:8200", mount="kv")
    tenant_vault = vault.login_approle(role_id="role", secret_id="secret", mount="approle")

    assert tenant_vault.token_cache_deadline is not None
    assert before + 560 < tenant_vault.token_cache_deadline <= before + 600


@pytest.mark.parametrize(
    ("lease_duration", "expected_deadline"),
    [
        (None, None),
        (0, None),
        (-5, None),
        ("not-a-duration", None),
        (1, 1000.0),
        (2, 1001.0),
    ],
)
def test_approle_lease_edge_cases_produce_safe_cache_deadlines(
    monkeypatch, lease_duration, expected_deadline
):
    monkeypatch.setattr("m8flow_backend.secrets.http.time.monotonic", lambda: 1000.0)

    def fake_request(method, url, **kwargs):
        assert url.endswith("/auth/approle/login")
        auth = {"client_token": "short-lived-token"}
        if lease_duration is not None:
            auth["lease_duration"] = lease_duration
        return _response(payload={"auth": auth})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    broker = HttpVault(addr="http://vault:8200")
    tenant_store = broker.login_approle(role_id="role", secret_id="secret", mount="approle")

    assert tenant_store.token_cache_deadline == expected_deadline


def test_cache_identity_includes_all_vault_connection_settings():
    base = HttpVault(
        addr="http://vault:8200", namespace="team-a", mount="kv", approle_mount="approle", verify=True
    )
    variants = [
        HttpVault(addr="http://other-vault:8200", namespace="team-a", mount="kv", approle_mount="approle", verify=True),
        HttpVault(addr="http://vault:8200", namespace="team-b", mount="kv", approle_mount="approle", verify=True),
        HttpVault(addr="http://vault:8200", namespace="team-a", mount="other-kv", approle_mount="approle", verify=True),
        HttpVault(addr="http://vault:8200", namespace="team-a", mount="kv", approle_mount="other-approle", verify=True),
        HttpVault(addr="http://vault:8200", namespace="team-a", mount="kv", approle_mount="approle", verify="/tmp/ca.pem"),
    ]

    assert all(variant.cache_identity != base.cache_identity for variant in variants)


def test_store_for_tenant_reuses_reconciled_role_id(monkeypatch):
    calls: list[str] = []

    def fake_request(method, url, **kwargs):
        calls.append(url)
        if url.endswith("/secret-id"):
            return _response(
                payload={
                    "data": {
                        "secret_id": "one-use-secret",
                        "secret_id_accessor": "one-use-accessor",
                    }
                }
            )
        if url.endswith("/login"):
            return _response(
                payload={"auth": {"client_token": "tenant-token", "lease_duration": 600}}
            )
        pytest.fail(f"Unexpected Vault request: {method} {url}")

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    broker = HttpVault(addr="http://vault:8200", token="broker-token")

    tenant_store = broker.store_for_tenant("tenant-a", role_name="role-a", role_id="known-role-id")

    assert tenant_store.token_cache_deadline is not None
    assert calls == [
        "http://vault:8200/v1/auth/approle/role/role-a/secret-id",
        "http://vault:8200/v1/auth/approle/login",
    ]


def test_minted_secret_id_is_limited_to_one_successful_login(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((url, kwargs.get("json")))
        if url.endswith("/secret-id"):
            return _response(payload={"data": {"secret_id": "one-use-secret"}})
        if url.endswith("/login"):
            return _response(
                payload={"auth": {"client_token": "tenant-token", "lease_duration": 600}}
            )
        pytest.fail(f"Unexpected Vault request: {method} {url}")

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    broker = HttpVault(addr="http://vault:8200", token="broker-token")

    broker.store_for_tenant("tenant-a", role_name="role-a", role_id="role-id")

    assert calls == [
        (
            "http://vault:8200/v1/auth/approle/role/role-a/secret-id",
            {"num_uses": 1},
        ),
        (
            "http://vault:8200/v1/auth/approle/login",
            {"role_id": "role-id", "secret_id": "one-use-secret"},
        ),
    ]


def test_store_for_tenant_cleans_up_secret_id_when_login_fails(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        if url.endswith("/secret-id"):
            return _response(
                payload={
                    "data": {
                        "secret_id": "one-use-secret",
                        "secret_id_accessor": "one-use-accessor",
                    }
                }
            )
        if url.endswith("/login"):
            return _response(status_code=400, payload={"errors": ["invalid SecretID"]})
        if url.endswith("/secret-id-accessor/destroy"):
            return _response(payload={})
        pytest.fail(f"Unexpected Vault request: {method} {url}")

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    broker = HttpVault(addr="http://vault:8200", token="broker-token")

    with pytest.raises(VaultTransportError, match="Vault request failed"):
        broker.store_for_tenant("tenant-a", role_name="role-a", role_id="role-id")

    assert [method for method, _url, _payload in calls] == ["POST", "POST", "POST"]
    assert calls[-1][1].endswith("/secret-id-accessor/destroy")
    assert calls[-1][2] == {"secret_id_accessor": "one-use-accessor"}


def test_store_for_tenant_destroys_secret_id_without_accessor_after_login_failure(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        if url.endswith("/secret-id"):
            return _response(payload={"data": {"secret_id": "one-use-secret"}})
        if url.endswith("/login"):
            return _response(status_code=400, payload={"errors": ["invalid SecretID"]})
        if url.endswith("/secret-id/destroy"):
            return _response(payload={})
        pytest.fail(f"Unexpected Vault request: {method} {url}")

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    broker = HttpVault(addr="http://vault:8200", token="broker-token")

    with pytest.raises(VaultTransportError, match="Vault request failed"):
        broker.store_for_tenant("tenant-a", role_name="role-a", role_id="role-id")

    assert calls[-1] == (
        "POST",
        "http://vault:8200/v1/auth/approle/role/role-a/secret-id/destroy",
        {"secret_id": "one-use-secret"},
    )


def test_store_for_tenant_preserves_login_error_if_secret_id_cleanup_fails(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("headers", {}).get("X-Vault-Token")))
        if url.endswith("/secret-id"):
            return _response(
                payload={
                    "data": {
                        "secret_id": "one-use-secret",
                        "secret_id_accessor": "one-use-accessor",
                    }
                }
            )
        if url.endswith("/login"):
            return _response(status_code=400, payload={"errors": ["invalid SecretID"]})
        if url.endswith("/secret-id-accessor/destroy"):
            return _response(status_code=500, payload={"errors": ["cleanup failed"]})
        pytest.fail(f"Unexpected Vault request: {method} {url}")

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    broker = HttpVault(addr="http://vault:8200", token="broker-token")

    with pytest.raises(VaultTransportError, match="Vault request failed"):
        broker.store_for_tenant("tenant-a", role_name="role-a", role_id="role-id")

    assert [url.rsplit("/", 1)[-1] for _method, url, _token in calls] == [
        "secret-id",
        "login",
        "destroy",
    ]


def test_http_error_wrapped(monkeypatch):
    def fake_request(method, url, **kwargs):
        return _response(status_code=500, payload={"errors": ["boom"]})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="t")
    with pytest.raises(VaultTransportError, match="Vault request failed"):
        vault.put_document("x", {"a": 1})


@pytest.mark.parametrize("status_code", [401, 403])
def test_authorization_failure_refreshes_token_and_retries_once(monkeypatch, status_code):
    calls = []
    refreshes = []

    def fake_request(method, url, **kwargs):
        calls.append(kwargs["headers"].get("X-Vault-Token"))
        if len(calls) == 1:
            return _response(status_code=status_code, payload={"errors": ["permission denied"]})
        return _response(payload={"data": {"data": {"refreshed": True}}})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="tenant-token")
    refreshed = HttpVault(addr="http://vault:8200", token="fresh-tenant-token")

    def refresh(rejected):
        refreshes.append(rejected)
        return refreshed

    vault.set_auth_failure_callback(refresh)

    assert vault.get_document("tenant/path") == {"refreshed": True}

    assert refreshes == [vault]
    assert calls == ["tenant-token", "fresh-tenant-token"]


def test_repeated_forbidden_response_does_not_loop_token_refresh(monkeypatch):
    calls = []
    refreshes = []

    def fake_request(method, url, **kwargs):
        calls.append(kwargs["headers"].get("X-Vault-Token"))
        return _response(status_code=403, payload={"errors": ["permission denied"]})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="tenant-token")
    refreshed = HttpVault(addr="http://vault:8200", token="fresh-tenant-token")
    vault.set_auth_failure_callback(lambda _rejected: (refreshes.append(True) or refreshed))

    with pytest.raises(VaultTransportError, match="Vault request failed"):
        vault.get_document("tenant/path")

    assert calls == ["tenant-token", "fresh-tenant-token"]
    assert refreshes == [True]


def test_non_authorization_server_error_does_not_refresh_token(monkeypatch):
    calls = []
    refreshes = []

    def fake_request(method, url, **kwargs):
        calls.append(kwargs["headers"].get("X-Vault-Token"))
        return _response(status_code=500, payload={"errors": ["temporarily unavailable"]})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(addr="http://vault:8200", token="tenant-token")
    vault.set_auth_failure_callback(lambda _rejected: (refreshes.append(True) or vault))

    for _ in range(2):
        with pytest.raises(VaultTransportError, match="Vault request failed"):
            vault.get_document("tenant/path")

    assert calls == ["tenant-token", "tenant-token"]
    assert refreshes == []


def test_authorization_retry_preserves_request_and_namespace(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if len(calls) == 1:
            return _response(status_code=403, payload={"errors": ["stale policy"]})
        return _response(payload={"data": {"ok": True}})

    monkeypatch.setattr("m8flow_backend.secrets.http.requests.request", fake_request)
    vault = HttpVault(
        addr="http://vault:8200", token="old-token", namespace="team-a", mount="kv"
    )
    refreshed = HttpVault(
        addr="http://vault:8200", token="new-token", namespace="team-a", mount="kv"
    )
    vault.set_auth_failure_callback(lambda _rejected: refreshed)

    assert vault._json("POST", "http://vault:8200/v1/kv/data/path", payload={"data": {"x": "y"}}) == {
        "data": {"ok": True}
    }

    assert len(calls) == 2
    first_method, first_url, first_kwargs = calls[0]
    retry_method, retry_url, retry_kwargs = calls[1]
    assert (retry_method, retry_url) == (first_method, first_url)
    assert retry_kwargs["json"] == first_kwargs["json"] == {"data": {"x": "y"}}
    assert retry_kwargs["headers"]["X-Vault-Namespace"] == "team-a"
    assert retry_kwargs["headers"]["X-Vault-Token"] == "new-token"


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
