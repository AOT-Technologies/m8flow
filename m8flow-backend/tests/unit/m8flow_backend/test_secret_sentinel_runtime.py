from __future__ import annotations

import pytest
from m8flow_bpmn_core.errors import ServiceTaskExecutionError
from m8flow_bpmn_core.services.service_tasks import (
    ServiceTaskCommandDefinition,
    ServiceTaskContext,
    ServiceTaskRegistry,
    ServiceTaskRequest,
    ServiceTaskResult,
)

from m8flow_backend.identity import ensure_tenant, ensure_user
from m8flow_backend.secrets import add_secret, resolve_possibly_secret_value
from m8flow_backend.secrets.runtime import wrap_registry_for_secret_sentinels


class _RecordingConnector:
    connector_key = "http"

    def __init__(self) -> None:
        self.last_request: ServiceTaskRequest | None = None

    def list_commands(self):
        return (
            ServiceTaskCommandDefinition(connector_key="http", command_name="GetRequestV2"),
        )

    def execute(self, request: ServiceTaskRequest) -> ServiceTaskResult:
        self.last_request = request
        return ServiceTaskResult(payload={"ok": True})


def _request(*, parameters, tenant_id="t1", task_data=None):
    return ServiceTaskRequest(
        operation_id="http/GetRequestV2",
        parameters=parameters,
        context=ServiceTaskContext(tenant_id=tenant_id),
        task_data=task_data,
    )


def _seed(db_session, monkeypatch, *, tenant_id="t1", key="SMTP_PASSWORD", value="s3cret"):
    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id, name=tenant_id)
    user = ensure_user(
        db_session,
        username="integrator",
        service="https://example.test/realms/m8flow",
        service_id="integrator",
    )
    add_secret(db_session, tenant_id=tenant.id, key=key, value=value, user_id=user.id)
    db_session.flush()
    monkeypatch.setattr("m8flow_backend.db.current_session", lambda: db_session)
    return tenant, user


def test_execute_replaces_m8flow_secret_and_leaves_spiff_secret(db_session, monkeypatch):
    _seed(db_session, monkeypatch)
    fake = _RecordingConnector()
    registry = wrap_registry_for_secret_sentinels(ServiceTaskRegistry())
    registry.register_connector(fake)

    registry.execute(
        _request(
            parameters={
                "password": "M8FLOW_SECRET:SMTP_PASSWORD",
                "legacy": "SPIFF_SECRET:SMTP_PASSWORD",
                "nested": {"token": "Bearer M8FLOW_SECRET:SMTP_PASSWORD"},
                "list": ["M8FLOW_SECRET:SMTP_PASSWORD"],
            },
            task_data={"leak": "M8FLOW_SECRET:SMTP_PASSWORD"},
        )
    )

    assert fake.last_request is not None
    assert fake.last_request.parameters["password"] == "s3cret"
    assert fake.last_request.parameters["legacy"] == "SPIFF_SECRET:SMTP_PASSWORD"
    assert fake.last_request.parameters["nested"]["token"] == "Bearer s3cret"
    assert fake.last_request.parameters["list"] == ["s3cret"]
    assert fake.last_request.task_data == {"leak": "M8FLOW_SECRET:SMTP_PASSWORD"}


def test_execute_fails_closed_when_secret_is_missing(db_session, monkeypatch):
    _seed(db_session, monkeypatch)
    fake = _RecordingConnector()
    registry = wrap_registry_for_secret_sentinels(ServiceTaskRegistry())
    registry.register_connector(fake)

    with pytest.raises(ServiceTaskExecutionError, match="MISSING_KEY"):
        registry.execute(_request(parameters={"password": "M8FLOW_SECRET:MISSING_KEY"}))
    assert fake.last_request is None


def test_list_helper_leaves_missing_sentinel_in_place(db_session):
    ensure_tenant(db_session, tenant_id="t1", slug="t1", name="t1")
    left = resolve_possibly_secret_value(db_session, tenant_id="t1", value="M8FLOW_SECRET:NOPE")
    assert left == "M8FLOW_SECRET:NOPE"


def test_execute_fails_closed_without_tenant_context(db_session, monkeypatch):
    _seed(db_session, monkeypatch)
    fake = _RecordingConnector()
    registry = wrap_registry_for_secret_sentinels(ServiceTaskRegistry())
    registry.register_connector(fake)

    with pytest.raises(ServiceTaskExecutionError, match="tenant context"):
        registry.execute(
            ServiceTaskRequest(
                operation_id="http/GetRequestV2",
                parameters={"password": "M8FLOW_SECRET:SMTP_PASSWORD"},
            )
        )
    assert fake.last_request is None
