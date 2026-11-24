"""Reading a configuration variable's value by name (used by the NATS notification worker).

Values come from the default database secret provider here; with Vault enabled the same
calls go to Vault, which the provider tests cover.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from m8flow_backend.identity import ensure_tenant, ensure_user
from m8flow_backend.models.named_value import NamedValueModel
from m8flow_backend.secrets import add_secret, delete_configuration_value, named_values

TENANT = "tenant-a"
OTHER_TENANT = "tenant-b"


@pytest.fixture
def user(db_session):
    for tenant in (TENANT, OTHER_TENANT):
        ensure_tenant(db_session, tenant_id=tenant, slug=tenant, name=tenant)
    return ensure_user(
        db_session,
        username="dana",
        service="https://example.test/realms/m8flow",
        service_id="dana",
    )


def _create(db_session, user, name, value, *, sensitive, tenant=TENANT):
    created = named_values.create_named_value(
        db_session,
        tenant_id=tenant,
        body={"name": name, "value": value, "is_sensitive": sensitive},
        user_id=user.id,
    )
    db_session.commit()
    return created


def test_a_sensitive_value_is_read_from_the_secret_provider(db_session, user):
    _create(db_session, user, "NATS_SMTP_PASSWORD", "s3cret", sensitive=True)

    row = db_session.query(NamedValueModel).filter_by(name="NATS_SMTP_PASSWORD").one()
    assert row.value is None  # never stored in the catalog row
    assert named_values.value_by_name(db_session, tenant_id=TENANT, name="NATS_SMTP_PASSWORD") == "s3cret"


def test_a_standard_value_is_read_from_the_row_as_text(db_session, user):
    _create(db_session, user, "NATS_SMTP_STARTTLS", True, sensitive=False)
    _create(db_session, user, "NATS_SMTP_PORT", 2525, sensitive=False)

    assert named_values.value_by_name(db_session, tenant_id=TENANT, name="NATS_SMTP_STARTTLS") == "True"
    assert named_values.value_by_name(db_session, tenant_id=TENANT, name="NATS_SMTP_PORT") == "2525"


def test_names_match_case_insensitively(db_session, user):
    _create(db_session, user, "nats_smtp_host", "smtp.example.test", sensitive=True)

    assert named_values.value_by_name(db_session, tenant_id=TENANT, name="NATS_SMTP_HOST") == "smtp.example.test"
    # names_present answers with the spelling the caller asked for.
    assert named_values.names_present(
        db_session, tenant_id=TENANT, names=("NATS_SMTP_HOST", "NATS_SMTP_PORT")
    ) == {"NATS_SMTP_HOST"}


def test_another_tenants_variable_is_never_returned(db_session, user):
    _create(db_session, user, "NATS_SMTP_HOST", "other.example.test", sensitive=True, tenant=OTHER_TENANT)

    assert named_values.value_by_name(db_session, tenant_id=TENANT, name="NATS_SMTP_HOST") is None
    assert named_values.names_present(db_session, tenant_id=TENANT, names=("NATS_SMTP_HOST",)) == set()


def test_a_missing_variable_or_provider_value_reads_as_none(db_session, user):
    created = _create(db_session, user, "NATS_SMTP_HOST", "smtp.example.test", sensitive=True)
    assert named_values.value_by_name(db_session, tenant_id=TENANT, name="NATS_SMTP_PORT") is None

    row = db_session.get(NamedValueModel, created["id"])
    delete_configuration_value(db_session, tenant_id=TENANT, variable_id=row.provider_key)
    db_session.commit()

    assert named_values.value_by_name(db_session, tenant_id=TENANT, name="NATS_SMTP_HOST") is None
    # Still present: the caller must report it as unreadable, not missing.
    assert named_values.names_present(db_session, tenant_id=TENANT, names=("NATS_SMTP_HOST",)) == {"NATS_SMTP_HOST"}


def test_an_unconfigured_standard_variable_reads_as_none(db_session, user):
    db_session.add(
        NamedValueModel(
            id=str(uuid4()),
            m8f_tenant_id=TENANT,
            name="NATS_SMTP_USERNAME",
            is_sensitive=False,
            value=None,
            is_configured=False,
        )
    )
    db_session.commit()

    assert named_values.value_by_name(db_session, tenant_id=TENANT, name="NATS_SMTP_USERNAME") is None


def test_a_row_backfilled_from_a_legacy_secret_reads_that_secret(db_session, user):
    add_secret(db_session, tenant_id=TENANT, key="LEGACY_SMTP_HOST", value="legacy.example.test", user_id=user.id)
    db_session.add(
        NamedValueModel(
            id=str(uuid4()),
            m8f_tenant_id=TENANT,
            name="NATS_SMTP_HOST",
            is_sensitive=True,
            value=None,
            is_configured=True,
            provider_key="LEGACY_SMTP_HOST",
        )
    )
    db_session.commit()

    assert named_values.value_by_name(db_session, tenant_id=TENANT, name="NATS_SMTP_HOST") == "legacy.example.test"
