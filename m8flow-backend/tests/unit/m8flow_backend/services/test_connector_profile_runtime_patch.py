"""The service-task side of connector profiles.

Two guarantees matter most here:

* a task with no ``m8flow_profile`` parameter reaches the connector exactly as
  before, which is what keeps every existing process model and shipped template
  working;
* a profile only ever fills parameters the chosen operation actually declares,
  because the proxy builds each command with ``command(**params)``.
"""

import pytest

from m8flow_backend.services import connector_profile_runtime_patch as runtime_patch
from m8flow_backend.services.connector_profile_service import ConnectorProfileError


@pytest.fixture(autouse=True)
def _reset_patch_state():
    runtime_patch._PATCHED = False
    runtime_patch.reset_catalogue_cache()
    yield
    runtime_patch._PATCHED = False
    runtime_patch.reset_catalogue_cache()


@pytest.fixture()
def delegate(monkeypatch):
    """Patch the delegate and capture what reaches the original call."""
    from spiffworkflow_backend.services.service_task_service import ServiceTaskDelegate

    calls: list[dict] = []

    def fake_call_connector(cls, operator_identifier, bpmn_params, spiff_task):
        calls.append(
            {
                "operator": operator_identifier,
                "params": bpmn_params,
                "task": spiff_task,
            }
        )
        return "{}"

    monkeypatch.setattr(
        ServiceTaskDelegate,
        "call_connector",
        classmethod(fake_call_connector),
        raising=False,
    )
    runtime_patch.apply()
    return ServiceTaskDelegate, calls


def _catalogue(monkeypatch, operators):
    monkeypatch.setattr(
        runtime_patch, "declared_parameter_names", lambda operator_id: operators.get(operator_id)
    )


def _profile(monkeypatch, values):
    from m8flow_backend.services.connector_profile_service import ConnectorProfileService

    monkeypatch.setattr(
        ConnectorProfileService,
        "resolve_for_runtime",
        classmethod(lambda cls, connector_type, profile_name: values),
    )


def test_task_without_a_profile_is_passed_through_untouched(delegate, monkeypatch):
    ServiceTaskDelegate, calls = delegate
    original_params = {
        "smtp_host": {"value": "M8FLOW_SECRET:SMTP_HOST", "type": "any"},
        "email_to": {"value": "a@example.com", "type": "any"},
    }

    ServiceTaskDelegate.call_connector("smtp/SendHTMLEmail", original_params, None)

    assert calls[0]["params"] is original_params


def test_profile_fills_only_empty_parameters(delegate, monkeypatch):
    ServiceTaskDelegate, calls = delegate
    _catalogue(
        monkeypatch,
        {"smtp/SendHTMLEmail": frozenset({"smtp_host", "smtp_user", "smtp_password", "email_to"})},
    )
    _profile(
        monkeypatch,
        {"smtp_host": "smtp.example.com", "smtp_user": "svc", "smtp_password": "hunter2"},
    )

    ServiceTaskDelegate.call_connector(
        "smtp/SendHTMLEmail",
        {
            "m8flow_profile": {"value": "smtp-staging", "type": "any"},
            "smtp_host": {"value": "  ", "type": "any"},
            "smtp_user": {"value": "author-override", "type": "any"},
            "email_to": {"value": "a@example.com", "type": "any"},
        },
        None,
    )

    sent = calls[0]["params"]
    assert "m8flow_profile" not in sent
    assert sent["smtp_host"]["value"] == "smtp.example.com"
    # An explicit value in the diagram wins over the profile.
    assert sent["smtp_user"]["value"] == "author-override"
    assert sent["smtp_password"]["value"] == "hunter2"
    assert sent["email_to"]["value"] == "a@example.com"


def test_a_field_the_operation_does_not_declare_is_not_injected(delegate, monkeypatch):
    ServiceTaskDelegate, calls = delegate
    # n8n's TriggerWorkflow takes neither base_url nor api_key.
    _catalogue(monkeypatch, {"n8n/TriggerWorkflow": frozenset({"webhook_url", "payload"})})
    _profile(monkeypatch, {"base_url": "https://n8n.example.com", "api_key": "k"})

    ServiceTaskDelegate.call_connector(
        "n8n/TriggerWorkflow",
        {
            "m8flow_profile": {"value": "n8n-prod", "type": "any"},
            "webhook_url": {"value": "https://n8n.example.com/hook", "type": "any"},
        },
        None,
    )

    sent = calls[0]["params"]
    assert set(sent) == {"webhook_url"}


def test_everything_is_injected_when_the_catalogue_is_unavailable(delegate, monkeypatch):
    ServiceTaskDelegate, calls = delegate
    _catalogue(monkeypatch, {})  # returns None for any operator
    _profile(monkeypatch, {"token": "xoxb-1"})

    ServiceTaskDelegate.call_connector(
        "slack/PostMessage",
        {"m8flow_profile": {"value": "slack-prod", "type": "any"}},
        None,
    )

    assert calls[0]["params"]["token"]["value"] == "xoxb-1"


def test_a_missing_profile_fails_the_task_rather_than_calling_without_credentials(
    delegate, monkeypatch
):
    ServiceTaskDelegate, calls = delegate
    from m8flow_backend.services.connector_profile_service import ConnectorProfileService

    def raise_missing(cls, connector_type, profile_name):
        raise ConnectorProfileError("No such profile", status_code=404)

    monkeypatch.setattr(
        ConnectorProfileService, "resolve_for_runtime", classmethod(raise_missing)
    )

    with pytest.raises(ConnectorProfileError):
        ServiceTaskDelegate.call_connector(
            "smtp/SendHTMLEmail",
            {"m8flow_profile": {"value": "gone", "type": "any"}},
            None,
        )

    assert calls == []


def test_catalogue_keeps_the_last_good_answer_when_the_proxy_goes_quiet(monkeypatch):
    from spiffworkflow_backend.services.service_task_service import ServiceTaskService

    monkeypatch.setattr(
        ServiceTaskService,
        "available_connectors",
        staticmethod(lambda: [{"id": "smtp/SendHTMLEmail", "parameters": [{"id": "smtp_host"}]}]),
    )
    assert runtime_patch.declared_parameter_names("smtp/SendHTMLEmail") == frozenset({"smtp_host"})

    # An unreachable proxy returns [] rather than raising; that must not be read
    # as "this connector has no parameters".
    monkeypatch.setattr(ServiceTaskService, "available_connectors", staticmethod(list))
    runtime_patch._catalogue_fetched_at = -1e9  # force a refetch
    assert runtime_patch.declared_parameter_names("smtp/SendHTMLEmail") == frozenset({"smtp_host"})
