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


def _post(server, payload, token="test-api-token"):
    body = json.dumps(payload).encode()
    request = Request(
        f"http://127.0.0.1:{server.server_address[1]}/v1/tenant-identities/ensure",
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
