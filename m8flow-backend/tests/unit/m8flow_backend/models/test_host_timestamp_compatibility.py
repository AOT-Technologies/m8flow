from datetime import UTC, datetime

from m8flow_backend.models.native import SecretModel


def test_native_datetime_is_persisted_without_legacy_epoch_columns(db_session):
    secret = SecretModel(
        key="legacy",
        value="value",
        m8f_tenant_id="tenant-a",
        created_at=datetime(2040, 1, 1, tzinfo=UTC),
        updated_at=datetime(2040, 1, 1, tzinfo=UTC),
    )

    db_session.add(secret)
    db_session.flush()

    assert secret.created_at == datetime(2040, 1, 1, tzinfo=UTC)
    assert secret.updated_at == datetime(2040, 1, 1, tzinfo=UTC)
    assert "created_at_in_seconds" not in secret.__table__.c
    assert "updated_at_in_seconds" not in secret.__table__.c


def test_native_datetime_is_not_exposed_as_legacy_epoch(db_session):
    created_at = datetime(2041, 2, 3, 4, 5, 6, tzinfo=UTC)
    secret = SecretModel(
        key="native",
        value="value",
        m8f_tenant_id="tenant-a",
        created_at=created_at,
        updated_at=created_at,
    )

    db_session.add(secret)
    db_session.flush()

    assert not hasattr(secret, "created_at_in_seconds")
    assert not hasattr(secret, "updated_at_in_seconds")


def test_missing_timestamps_keep_the_existing_host_default_behavior(db_session):
    secret = SecretModel(key="default", value="value", m8f_tenant_id="tenant-a")

    db_session.add(secret)
    db_session.flush()

    assert secret.created_at is not None
    assert secret.updated_at is not None
    assert secret.created_at.tzinfo is not None
    assert secret.updated_at.tzinfo is not None


def test_updating_native_datetime_uses_native_column(db_session):
    secret = SecretModel(
        key="update",
        value="value",
        m8f_tenant_id="tenant-a",
        created_at=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        updated_at=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
    )
    db_session.add(secret)
    db_session.flush()

    updated_at = datetime(2042, 3, 4, 5, 6, 7, tzinfo=UTC)
    secret.updated_at = updated_at
    db_session.flush()

    assert secret.updated_at == updated_at


def test_orm_update_refreshes_updated_at_when_the_caller_does_not_set_it(db_session):
    initial = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
    secret = SecretModel(
        key="automatic-update",
        value="value",
        m8f_tenant_id="tenant-a",
        created_at=initial,
        updated_at=initial,
    )
    db_session.add(secret)
    db_session.flush()

    secret.value = "changed"
    db_session.flush()

    assert secret.updated_at is not None
    assert secret.updated_at != initial


def test_host_models_declare_native_timestamp_columns():
    from m8flow_backend.connectors.configuration import ConnectorConfigurationModel
    from m8flow_backend.models.external_form_request import ExternalFormRequestModel
    from m8flow_backend.models.native import (
        ApiLogModel,
        M8flowNatsApiKeyModel,
        PkceCodeVerifierModel,
        ProcessInstanceFileDataModel,
        ProcessModelTemplateModel,
        RefreshTokenModel,
        SecretModel,
        ServiceAccountModel,
        TaskDraftDataModel,
        TaskInstructionsForEndUserModel,
        TemplateModel,
    )
    from m8flow_backend.models.tenant_invitation import M8flowTenantInvitationModel

    models_with_created_at = (
        SecretModel,
        PkceCodeVerifierModel,
        RefreshTokenModel,
        ServiceAccountModel,
        TaskDraftDataModel,
        TaskInstructionsForEndUserModel,
        ApiLogModel,
        ProcessInstanceFileDataModel,
        TemplateModel,
        ProcessModelTemplateModel,
        M8flowNatsApiKeyModel,
        ConnectorConfigurationModel,
        M8flowTenantInvitationModel,
        ExternalFormRequestModel,
    )

    for model in models_with_created_at:
        assert "created_at" in model.__table__.c

    for model in (
        SecretModel,
        RefreshTokenModel,
        TaskDraftDataModel,
        TemplateModel,
        ProcessModelTemplateModel,
        ConnectorConfigurationModel,
        M8flowTenantInvitationModel,
        ExternalFormRequestModel,
    ):
        assert "updated_at" in model.__table__.c

    for model in models_with_created_at:
        assert "created_at_in_seconds" not in model.__table__.c
    for model in (
        SecretModel,
        RefreshTokenModel,
        TaskDraftDataModel,
        TemplateModel,
        ProcessModelTemplateModel,
        ConnectorConfigurationModel,
        M8flowTenantInvitationModel,
        ExternalFormRequestModel,
    ):
        assert "updated_at_in_seconds" not in model.__table__.c
