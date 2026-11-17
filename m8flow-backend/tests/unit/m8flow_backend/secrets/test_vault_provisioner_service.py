from __future__ import annotations

import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


def _run_server(monkeypatch, reconcile):
    from m8flow_backend.vault_provisioner_service import ProvisionerHTTPServer

    monkeypatch.setenv("M8FLOW_VAULT_PROVISIONER_API_TOKEN", "test-api-token")
    monkeypatch.setattr(
        "m8flow_backend.vault_provisioner_service.reconcile_tenant_identity", reconcile
    )

    class _Vault:
        pass

    server = ProvisionerHTTPServer(("127.0.0.1", 0), _Vault())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _post(server, payload, token="test-api-token", path="/v1/tenant-identities/ensure"):
    body = json.dumps(payload).encode()
    request = Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}" if token else "",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        response = urlopen(request, timeout=2)
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())
    with response:
        return response.status, json.loads(response.read())


def test_provisioner_service_requires_internal_api_token(monkeypatch):
    server, thread = _run_server(monkeypatch, lambda *_a, **_k: pytest.fail("must not reconcile"))
    try:
        status, body = _post(server, {"tenant_id": "tenant-a"}, token="wrong")
        assert status == 401
        assert body == {"error": "unauthorized"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_provisioner_service_only_accepts_tenant_id_and_returns_identity(monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultIdentity

    calls = []

    def reconcile(tenant_id, *, control):
        calls.append((tenant_id, control))
        return TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name="policy-tenant-a",
            role_name="role-tenant-a",
            role_id="role-id-value",
        )

    server, thread = _run_server(monkeypatch, reconcile)
    try:
        status, body = _post(server, {"tenant_id": "tenant-a"})
        assert status == 200
        assert body == {
            "tenant_id": "tenant-a",
            "role_name": "role-tenant-a",
            "role_id": "role-id-value",
        }
        assert calls == [("tenant-a", server.vault)]

        status, body = _post(
            server,
            {"tenant_id": "tenant-a", "policy": 'path "*" { capabilities = ["root"] }'},
        )
        assert status == 400
        assert body == {"error": "invalid_tenant_id"}
        assert len(calls) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_provisioner_service_does_not_expose_vault_exception_details(monkeypatch):
    server, thread = _run_server(
        monkeypatch, lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("secret-token-value"))
    )
    try:
        status, body = _post(server, {"tenant_id": "tenant-a"})
        assert status == 503
        assert body == {"error": "provisioning_failed"}
        assert "secret-token-value" not in json.dumps(body)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_provisioner_login_mints_and_consumes_tenant_secret_id(monkeypatch):
    from types import SimpleNamespace

    from m8flow_backend.secrets.provisioning import TenantVaultIdentity

    events = []

    class _Vault:
        def mint_approle_secret_id(self, role_name, *, mount):
            events.append(("mint", role_name, mount))
            return SimpleNamespace(secret_id="one-use-secret", secret_id_accessor="accessor")

        def login_approle(self, *, role_id, secret_id, mount):
            events.append(("login", role_id, secret_id, mount))
            return SimpleNamespace(
                client_token="tenant-scoped-token", token_lease_duration=600
            )

        def destroy_approle_secret_id_accessor(self, *args, **kwargs):
            events.append(("destroy_accessor", args, kwargs))

    def reconcile(tenant_id, *, control):
        assert control is server.vault
        return TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name="policy-tenant-a",
            role_name="role-tenant-a",
            role_id="role-id-tenant-a",
        )

    monkeypatch.setattr("m8flow_backend.vault_provisioner_service.vault_approle_mount_point", lambda: "approle")
    server, thread = _run_server(monkeypatch, reconcile)
    server.vault = _Vault()
    try:
        status, body = _post(
            server,
            {"tenant_id": "tenant-a"},
            path="/v1/tenant-identities/login",
        )
        assert status == 200
        assert body == {
            "tenant_id": "tenant-a",
            "client_token": "tenant-scoped-token",
            "lease_duration": 600,
        }
        assert events == [
            ("mint", "role-tenant-a", "approle"),
            ("login", "role-id-tenant-a", "one-use-secret", "approle"),
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_provisioner_login_cleans_up_secret_id_when_vault_login_fails(monkeypatch):
    from types import SimpleNamespace

    from m8flow_backend.secrets.provisioning import TenantVaultIdentity

    cleanup = []

    class _Vault:
        def mint_approle_secret_id(self, role_name, *, mount):
            return SimpleNamespace(secret_id="secret", secret_id_accessor="accessor")

        def login_approle(self, **_kwargs):
            raise RuntimeError("do not return secret values")

        def destroy_approle_secret_id_accessor(self, role_name, *, mount, secret_id_accessor):
            cleanup.append((role_name, mount, secret_id_accessor))

    def reconcile(tenant_id, *, control):
        assert control is server.vault
        return TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name="policy-tenant-a",
            role_name="role-tenant-a",
            role_id="role-id-tenant-a",
        )

    monkeypatch.setattr("m8flow_backend.vault_provisioner_service.vault_approle_mount_point", lambda: "approle")
    server, thread = _run_server(monkeypatch, reconcile)
    server.vault = _Vault()
    try:
        status, body = _post(
            server,
            {"tenant_id": "tenant-a"},
            path="/v1/tenant-identities/login",
        )
        assert status == 503
        assert body == {"error": "tenant_login_failed"}
        assert cleanup == [("role-tenant-a", "approle", "accessor")]
        assert "secret" not in json.dumps(body)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
