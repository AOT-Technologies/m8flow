from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from m8flow_backend.identity import ensure_tenant
from m8flow_backend.models.named_value import NamedValueModel
from m8flow_backend.secrets import named_values


def _create_sensitive_value(db_session, *, tenant_id: str, provider_key: str):
    tenant = ensure_tenant(
        db_session, tenant_id=tenant_id, slug=tenant_id, name=tenant_id
    )
    row = NamedValueModel(
        id=str(uuid4()),
        m8f_tenant_id=tenant.id,
        name="SMTP_PASSWORD",
        is_sensitive=True,
        value=None,
        is_configured=True,
        provider_key=provider_key,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _install_secret_store(monkeypatch, db_session):
    configuration_values: dict[tuple[str, str], str] = {}
    legacy_values: dict[tuple[str, str], str] = {}

    def set_configuration_value(
        _session, *, tenant_id, variable_id, value, user_id
    ):
        del user_id
        configuration_values[(tenant_id, variable_id)] = value

    def delete_configuration_value(_session, *, tenant_id, variable_id):
        configuration_values.pop((tenant_id, variable_id), None)

    def delete_secret(_session, *, tenant_id, key):
        legacy_values.pop((tenant_id, key), None)

    @contextmanager
    def cleanup_session_scope():
        yield SimpleNamespace(bind=db_session.get_bind())

    monkeypatch.setattr(named_values, "set_configuration_value", set_configuration_value)
    monkeypatch.setattr(named_values, "delete_configuration_value", delete_configuration_value)
    monkeypatch.setattr(named_values, "delete_secret", delete_secret)
    monkeypatch.setattr(named_values, "session_scope", cleanup_session_scope)
    return configuration_values, legacy_values


def test_sensitive_named_value_update_rollback_preserves_legacy_secret_and_pointer(
    db_session, monkeypatch
):
    tenant_id = "named-value-rollback-tenant"
    row = _create_sensitive_value(
        db_session, tenant_id=tenant_id, provider_key="legacy_smtp_password"
    )
    configuration_values, legacy_values = _install_secret_store(monkeypatch, db_session)
    legacy_values[(tenant_id, "legacy_smtp_password")] = "committed-secret"

    named_values.update_named_value(
        db_session,
        tenant_id=tenant_id,
        variable_id=row.id,
        body={"value": "uncommitted-replacement"},
        user_id=1,
    )
    staged_provider_key = db_session.get(NamedValueModel, row.id).provider_key
    assert staged_provider_key.startswith("configuration-variable:")
    staged_configuration_id = staged_provider_key.removeprefix("configuration-variable:")
    assert configuration_values[(tenant_id, staged_configuration_id)] == "uncommitted-replacement"
    assert legacy_values[(tenant_id, "legacy_smtp_password")] == "committed-secret"

    def fail_commit():
        db_session.rollback()
        raise RuntimeError("simulated database commit failure")

    original_commit = db_session.commit
    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated database commit failure"):
        db_session.commit()
    monkeypatch.setattr(db_session, "commit", original_commit)
    db_session.expire_all()

    persisted = db_session.get(NamedValueModel, row.id)
    assert persisted.provider_key == "legacy_smtp_password"
    assert legacy_values[(tenant_id, "legacy_smtp_password")] == "committed-secret"
    assert (tenant_id, staged_configuration_id) not in configuration_values


def test_sensitive_named_value_update_retires_old_key_only_after_commit(
    db_session, monkeypatch
):
    tenant_id = "named-value-commit-tenant"
    row = _create_sensitive_value(
        db_session, tenant_id=tenant_id, provider_key="legacy_smtp_password"
    )
    configuration_values, legacy_values = _install_secret_store(monkeypatch, db_session)
    legacy_values[(tenant_id, "legacy_smtp_password")] = "committed-secret"

    named_values.update_named_value(
        db_session,
        tenant_id=tenant_id,
        variable_id=row.id,
        body={"value": "replacement-secret"},
        user_id=1,
    )
    staged_provider_key = db_session.get(NamedValueModel, row.id).provider_key
    staged_configuration_id = staged_provider_key.removeprefix(
        "configuration-variable:"
    )

    assert legacy_values[(tenant_id, "legacy_smtp_password")] == "committed-secret"
    assert configuration_values[(tenant_id, staged_configuration_id)] == "replacement-secret"

    db_session.commit()

    persisted = db_session.get(NamedValueModel, row.id)
    assert persisted.provider_key == staged_provider_key
    assert (tenant_id, "legacy_smtp_password") not in legacy_values
    assert configuration_values[(tenant_id, staged_configuration_id)] == "replacement-secret"
