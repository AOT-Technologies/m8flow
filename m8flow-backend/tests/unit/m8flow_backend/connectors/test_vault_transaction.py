from __future__ import annotations

import importlib
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from m8flow_backend.connectors import service
from m8flow_backend.identity import ensure_tenant, ensure_user


@contextmanager
def _cleanup_session_scope():
    # Vault cleanup only needs a session-shaped object in these tests. The
    # service uses it to preserve PostgreSQL tenant context when applicable.
    yield SimpleNamespace(bind=None)


def _install_vault_document_store(monkeypatch, documents):
    def set_document(
        _session, *, tenant_id, configuration_id, values, user_id,
        replace_existing=False,
    ):
        key = (tenant_id, str(configuration_id))
        if key in documents and not replace_existing:
            raise AssertionError("unexpected Vault document overwrite")
        documents[key] = dict(values)

    def get_document(_session, *, tenant_id, configuration_id):
        return documents.get((tenant_id, str(configuration_id)))

    def delete_document(_session, *, tenant_id, configuration_id):
        documents.pop((tenant_id, str(configuration_id)), None)

    monkeypatch.setattr(service, "set_connector_configuration", set_document)
    monkeypatch.setattr(service, "get_connector_configuration", get_document)
    monkeypatch.setattr(service, "delete_connector_configuration", delete_document)
    monkeypatch.setattr(service, "delete_secret", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "session_scope", _cleanup_session_scope)


def _create_profile(db_session, tenant_id: str, user_id: int):
    return service.create_profile(
        db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        body={
            "connector_type": "http",
            "profile_name": "vault-test",
            "display_name": "Vault test",
            "config": {"basic_auth_password": "initial-secret"},
        },
    )


def _tenant_and_user(db_session):
    tenant = ensure_tenant(
        db_session, tenant_id="vault-transaction-tenant", name="Vault test", slug="vault-transaction"
    )
    user = ensure_user(
        db_session,
        username="vault-transaction-user",
        service="https://example.test/realms/m8flow",
        service_id="vault-transaction-user",
    )
    db_session.commit()
    return tenant.id, user.id


def test_profile_update_uses_new_vault_key_and_cleans_old_key_after_commit(
    db_session, monkeypatch
):
    documents = {}
    _install_vault_document_store(monkeypatch, documents)
    tenant_id, user_id = _tenant_and_user(db_session)
    profile = _create_profile(db_session, tenant_id, user_id)
    old_key = profile.provider_key
    db_session.commit()

    updated = service.update_profile(
        db_session,
        tenant_id=tenant_id,
        profile_id=profile.id,
        user_id=user_id,
        body={"config": {"basic_auth_password": "replacement-secret"}},
    )
    new_key = updated.provider_key

    assert new_key != old_key
    assert documents[(tenant_id, old_key)] == {"basic_auth_password": "initial-secret"}
    assert documents[(tenant_id, new_key)] == {"basic_auth_password": "replacement-secret"}

    db_session.commit()

    assert (tenant_id, old_key) not in documents
    assert documents[(tenant_id, new_key)] == {"basic_auth_password": "replacement-secret"}


def test_profile_update_rollback_preserves_old_vault_document_and_removes_staged_one(
    db_session, monkeypatch
):
    documents = {}
    _install_vault_document_store(monkeypatch, documents)
    tenant_id, user_id = _tenant_and_user(db_session)
    profile = _create_profile(db_session, tenant_id, user_id)
    old_key = profile.provider_key
    db_session.commit()

    service.update_profile(
        db_session,
        tenant_id=tenant_id,
        profile_id=profile.id,
        user_id=user_id,
        body={"config": {"basic_auth_password": "uncommitted-secret"}},
    )
    staged_key = db_session.get(type(profile), profile.id).provider_key
    assert staged_key != old_key
    assert (tenant_id, staged_key) in documents

    db_session.rollback()
    db_session.expire_all()

    persisted = db_session.get(type(profile), profile.id)
    assert persisted.provider_key == old_key
    assert documents[(tenant_id, old_key)] == {"basic_auth_password": "initial-secret"}
    assert (tenant_id, staged_key) not in documents


def test_profile_update_commit_failure_preserves_database_reference_and_vault_secret(
    db_session, monkeypatch
):
    documents = {}
    _install_vault_document_store(monkeypatch, documents)
    tenant_id, user_id = _tenant_and_user(db_session)
    profile = _create_profile(db_session, tenant_id, user_id)
    old_key = profile.provider_key
    db_session.commit()

    service.update_profile(
        db_session,
        tenant_id=tenant_id,
        profile_id=profile.id,
        user_id=user_id,
        body={"config": {"basic_auth_password": "replacement-secret"}},
    )
    staged_key = db_session.get(type(profile), profile.id).provider_key
    assert staged_key != old_key

    def fail_commit():
        db_session.rollback()
        raise RuntimeError("simulated database commit failure")

    original_commit = db_session.commit
    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated database commit failure"):
        db_session.commit()
    monkeypatch.setattr(db_session, "commit", original_commit)
    db_session.expire_all()

    persisted = db_session.get(type(profile), profile.id)
    assert persisted.provider_key == old_key
    assert documents[(tenant_id, old_key)] == {"basic_auth_password": "initial-secret"}
    assert (tenant_id, staged_key) not in documents


def test_profile_delete_only_removes_vault_document_after_commit(db_session, monkeypatch):
    documents = {}
    _install_vault_document_store(monkeypatch, documents)
    tenant_id, user_id = _tenant_and_user(db_session)
    profile = _create_profile(db_session, tenant_id, user_id)
    provider_key = profile.provider_key
    db_session.commit()

    service.delete_profile(db_session, tenant_id=tenant_id, profile_id=profile.id)
    assert (tenant_id, provider_key) in documents

    db_session.rollback()
    assert (tenant_id, provider_key) in documents

    service.delete_profile(db_session, tenant_id=tenant_id, profile_id=profile.id)
    db_session.commit()
    assert (tenant_id, provider_key) not in documents


def test_profile_delete_commit_failure_preserves_database_row_and_vault_secret(
    db_session, monkeypatch
):
    documents = {}
    _install_vault_document_store(monkeypatch, documents)
    tenant_id, user_id = _tenant_and_user(db_session)
    profile = _create_profile(db_session, tenant_id, user_id)
    profile_id = profile.id
    provider_key = profile.provider_key
    db_session.commit()

    service.delete_profile(db_session, tenant_id=tenant_id, profile_id=profile_id)
    assert (tenant_id, provider_key) in documents

    def fail_commit():
        db_session.rollback()
        raise RuntimeError("simulated database commit failure")

    original_commit = db_session.commit
    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated database commit failure"):
        db_session.commit()
    monkeypatch.setattr(db_session, "commit", original_commit)
    db_session.expire_all()

    assert db_session.get(type(profile), profile_id) is not None
    assert documents[(tenant_id, provider_key)] == {"basic_auth_password": "initial-secret"}


def test_secret_cleanup_listeners_are_idempotent_across_module_reload(
    db_session, monkeypatch
):
    importlib.reload(service)
    importlib.reload(service)
    cleanup_calls = []
    monkeypatch.setattr(
        service,
        "_run_connector_secret_cleanup",
        lambda pending, *, message: cleanup_calls.append((pending, message)),
    )
    bind = db_session.get_bind()

    committed_session = Session(bind=bind)
    committed_pending = {("tenant-a", "document", "retired-key")}
    committed_session.info[service._RETIRED_SECRET_CLEANUP_KEY] = committed_pending.copy()
    committed_session.execute(text("SELECT 1"))
    committed_session.commit()
    committed_session.close()

    assert cleanup_calls == [
        (committed_pending, "Could not clean up retired connector secret")
    ]

    cleanup_calls.clear()
    rolled_back_session = Session(bind=bind)
    rolled_back_pending = {("tenant-a", "document", "staged-key")}
    rolled_back_session.info[service._STAGED_SECRET_CLEANUP_KEY] = rolled_back_pending.copy()
    rolled_back_session.execute(text("SELECT 1"))
    rolled_back_session.rollback()
    rolled_back_session.close()

    assert cleanup_calls == [
        (rolled_back_pending, "Could not clean up staged connector secret after rollback")
    ]
