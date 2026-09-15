from __future__ import annotations

import pytest
from m8flow_bpmn_core.errors import ServiceTaskExecutionError
from m8flow_bpmn_core.services.service_tasks import (
    ServiceTaskCommandDefinition,
    ServiceTaskContext,
    ServiceTaskParameterDefinition,
    ServiceTaskRegistry,
    ServiceTaskRequest,
    ServiceTaskResult,
)

from m8flow_backend.connectors.runtime import (
    ProfileInjectingServiceTaskRegistry,
    wrap_registry_for_connector_profiles,
)
from m8flow_backend.connectors.service import create_profile, deactivate_profile
from m8flow_backend.identity import ensure_tenant, ensure_user
from m8flow_backend.secrets import add_secret, build_host_service_task_registry
from m8flow_backend.secrets.runtime import (
    SecretResolvingServiceTaskRegistry,
    wrap_registry_for_secret_sentinels,
)

_HTTP_PARAMS = (
    ServiceTaskParameterDefinition(name="url"),
    ServiceTaskParameterDefinition(name="basic_auth_username"),
    ServiceTaskParameterDefinition(name="basic_auth_password"),
    ServiceTaskParameterDefinition(name="headers"),
)


class _RecordingConnector:
    connector_key = "http"

    def __init__(self) -> None:
        self.last_request: ServiceTaskRequest | None = None

    def list_commands(self):
        return (
            ServiceTaskCommandDefinition(
                connector_key="http",
                command_name="GetRequestV2",
                parameters=_HTTP_PARAMS,
            ),
        )

    def execute(self, request: ServiceTaskRequest) -> ServiceTaskResult:
        self.last_request = request
        return ServiceTaskResult(payload={"ok": True})


def _request(*, parameters, tenant_id="t1"):
    return ServiceTaskRequest(
        operation_id="http/GetRequestV2",
        parameters=parameters,
        context=ServiceTaskContext(tenant_id=tenant_id),
    )


def _composed(fake: _RecordingConnector) -> ServiceTaskRegistry:
    registry = wrap_registry_for_connector_profiles(
        wrap_registry_for_secret_sentinels(ServiceTaskRegistry())
    )
    registry.register_connector(fake)
    return registry


def _seed_profile(
    db_session,
    monkeypatch,
    *,
    tenant_id="t1",
    profile_name="default",
    username="api-user",
    password="from-profile",
):
    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id, name=tenant_id)
    user = ensure_user(
        db_session,
        username="integrator",
        service="https://example.test/realms/m8flow",
        service_id="integrator",
    )
    profile = create_profile(
        db_session,
        tenant_id=tenant.id,
        body={
            "connector_type": "http",
            "profile_name": profile_name,
            "display_name": profile_name,
            "config": {
                "basic_auth_username": username,
                "basic_auth_password": password,
            },
        },
        user_id=user.id,
    )
    db_session.flush()
    monkeypatch.setattr("m8flow_backend.db.current_session", lambda: db_session)
    return tenant, user, profile


def test_task_without_a_profile_is_passed_through_untouched(db_session, monkeypatch):
    _seed_profile(db_session, monkeypatch)
    fake = _RecordingConnector()
    registry = wrap_registry_for_connector_profiles(ServiceTaskRegistry())
    registry.register_connector(fake)
    original = {"url": "https://example.test", "basic_auth_password": "M8FLOW_SECRET:API_TOKEN"}

    registry.execute(_request(parameters=original))

    assert fake.last_request is not None
    assert fake.last_request.parameters is original


def test_inject_fills_blank_basic_auth(db_session, monkeypatch):
    _seed_profile(db_session, monkeypatch)
    fake = _RecordingConnector()
    registry = _composed(fake)

    registry.execute(
        _request(
            parameters={
                "m8flow_profile": "default",
                "url": "https://example.test",
                "basic_auth_username": "",
                "basic_auth_password": "  ",
            }
        )
    )

    assert fake.last_request is not None
    params = fake.last_request.parameters
    assert params["basic_auth_username"] == "api-user"
    assert params["basic_auth_password"] == "from-profile"
    assert params["url"] == "https://example.test"
    assert "m8flow_profile" not in params


def test_task_value_wins_over_profile(db_session, monkeypatch):
    _seed_profile(db_session, monkeypatch)
    fake = _RecordingConnector()
    registry = _composed(fake)

    registry.execute(
        _request(
            parameters={
                "m8flow_profile": "default",
                "url": "https://example.test",
                "basic_auth_username": "typed-by-hand",
            }
        )
    )

    params = fake.last_request.parameters
    assert params["basic_auth_username"] == "typed-by-hand"
    assert params["basic_auth_password"] == "from-profile"
    assert "m8flow_profile" not in params


def test_unknown_profile_fails_closed(db_session, monkeypatch):
    _seed_profile(db_session, monkeypatch)
    fake = _RecordingConnector()
    registry = _composed(fake)

    with pytest.raises(ServiceTaskExecutionError, match="does-not-exist"):
        registry.execute(_request(parameters={"m8flow_profile": "does-not-exist"}))
    assert fake.last_request is None


def test_inactive_profile_fails_closed(db_session, monkeypatch):
    tenant, _user, profile = _seed_profile(db_session, monkeypatch)
    deactivate_profile(db_session, tenant_id=tenant.id, profile_id=profile.id)
    db_session.flush()
    fake = _RecordingConnector()
    registry = _composed(fake)

    with pytest.raises(ServiceTaskExecutionError, match="inactive"):
        registry.execute(_request(parameters={"m8flow_profile": "default"}))
    assert fake.last_request is None


def test_undeclared_profile_fields_are_not_injected(db_session, monkeypatch):
    _seed_profile(db_session, monkeypatch)
    monkeypatch.setattr(
        "m8flow_backend.connectors.runtime.resolve_for_runtime",
        lambda *_args, **_kwargs: {
            "basic_auth_username": "u",
            "not_a_param": "dropped",
        },
    )
    fake = _RecordingConnector()
    registry = _composed(fake)

    registry.execute(_request(parameters={"m8flow_profile": "default", "url": "https://x"}))

    params = fake.last_request.parameters
    assert params["basic_auth_username"] == "u"
    assert "not_a_param" not in params
    assert "m8flow_profile" not in params


def test_sentinel_still_resolves_after_inject(db_session, monkeypatch):
    tenant, user, _profile = _seed_profile(db_session, monkeypatch)
    add_secret(db_session, tenant_id=tenant.id, key="API_URL", value="https://from-secret", user_id=user.id)
    db_session.flush()
    fake = _RecordingConnector()
    registry = _composed(fake)

    registry.execute(
        _request(
            parameters={
                "m8flow_profile": "default",
                "url": "M8FLOW_SECRET:API_URL",
            }
        )
    )

    params = fake.last_request.parameters
    assert params["url"] == "https://from-secret"
    assert params["basic_auth_password"] == "from-profile"
    assert "m8flow_profile" not in params


def test_profile_name_may_arrive_as_bpmn_entry(db_session, monkeypatch):
    _seed_profile(db_session, monkeypatch)
    fake = _RecordingConnector()
    registry = _composed(fake)

    registry.execute(
        _request(parameters={"m8flow_profile": {"value": "default", "type": "str"}})
    )

    assert fake.last_request.parameters["basic_auth_username"] == "api-user"
    assert "m8flow_profile" not in fake.last_request.parameters


def test_host_registry_factory_injects_then_resolves_sentinels():
    registry = build_host_service_task_registry()
    assert isinstance(registry, ProfileInjectingServiceTaskRegistry)
    assert isinstance(registry._inner, SecretResolvingServiceTaskRegistry)
