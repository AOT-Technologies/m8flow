from __future__ import annotations

from types import SimpleNamespace

from m8flow_backend.identity import ensure_tenant
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.routes import keycloak_controller


class _DirectoryAdmin:
    def __init__(self):
        self.deleted = []

    def delete_tenant(self, tenant_ref):
        self.deleted.append(tenant_ref)


def _invoke_delete(app, db_session, *, slug, monkeypatch, admin):
    monkeypatch.setattr(
        keycloak_controller, "get_auth_provider", lambda: SimpleNamespace(directory_admin=admin)
    )
    monkeypatch.setattr(keycloak_controller, "user_has_permission", lambda *_a, **_k: True)
    with app.test_request_context(f"/tenant-realms/{slug}", method="DELETE"):
        from flask import g

        g.user = SimpleNamespace(username="operator", groups=[])
        g.db_session = db_session
        result = keycloak_controller.delete_tenant_realm(slug)
        if result[1] >= 400:
            g.m8flow_rollback_session = True
        return result


def test_tenant_delete_cleans_vault_only_after_database_commit(app, db_session, monkeypatch):
    tenant = ensure_tenant(
        db_session, tenant_id="tenant-vault-cleanup", name="Cleanup", slug="cleanup"
    )
    tenant_id = tenant.id
    db_session.commit()
    admin = _DirectoryAdmin()
    cleaned = []

    def cleanup_vault(vault_tenant_id):
        assert db_session.get(M8flowTenantModel, vault_tenant_id) is None
        cleaned.append(vault_tenant_id)

    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.delete_tenant_vault_data", cleanup_vault
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provider.resolved_secret_backend_kind", lambda: "vault"
    )

    body, status = _invoke_delete(
        app, db_session, slug="cleanup", monkeypatch=monkeypatch, admin=admin
    )

    assert status == 202
    assert body["tenant_id"] == tenant_id
    assert body["vault_cleanup_pending"] is True
    assert cleaned == [tenant_id]
    assert admin.deleted[0].id == tenant_id


def test_database_delete_failure_preserves_vault_data_and_tenant(app, db_session, monkeypatch):
    tenant = ensure_tenant(
        db_session, tenant_id="tenant-vault-db-fail", name="Cleanup fail", slug="cleanup-fail"
    )
    tenant_id = tenant.id
    db_session.commit()
    admin = _DirectoryAdmin()
    cleanup_calls = []
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.delete_tenant_vault_data",
        lambda tenant_id: cleanup_calls.append(tenant_id),
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provider.resolved_secret_backend_kind", lambda: "vault"
    )
    class _FailingDatabaseSession:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def commit(self):
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("delete", {}, RuntimeError("simulated FK restriction"))

    monkeypatch.setattr(
        keycloak_controller, "db", SimpleNamespace(session=_FailingDatabaseSession())
    )
    body, status = _invoke_delete(
        app, db_session, slug="cleanup-fail", monkeypatch=monkeypatch, admin=admin
    )

    assert status == 409
    assert "Vault credentials and secrets were left intact" in body["detail"]
    assert cleanup_calls == []
    assert db_session.get(M8flowTenantModel, tenant_id) is not None


def test_vault_cleanup_failure_returns_operator_action_with_tenant_id(
    app, db_session, monkeypatch
):
    from m8flow_backend.secrets.provisioning import TenantVaultCleanupError

    tenant = ensure_tenant(
        db_session, tenant_id="tenant-vault-unavailable", name="Vault unavailable", slug="vault-unavailable"
    )
    tenant_id = tenant.id
    db_session.commit()
    admin = _DirectoryAdmin()

    def fail_cleanup(_tenant_id):
        raise TenantVaultCleanupError("Vault unavailable")

    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.delete_tenant_vault_data", fail_cleanup
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provider.resolved_secret_backend_kind", lambda: "vault"
    )

    body, status = _invoke_delete(
        app, db_session, slug="vault-unavailable", monkeypatch=monkeypatch, admin=admin
    )

    assert status == 202
    assert body["tenant_id"] == tenant_id
    assert body["vault_cleanup_pending"] is True
    assert db_session.get(M8flowTenantModel, tenant_id) is None
