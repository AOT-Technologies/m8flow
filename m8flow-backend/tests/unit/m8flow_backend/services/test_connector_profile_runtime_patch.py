"""The runtime injection patch."""

from __future__ import annotations

import pytest

from m8flow_backend.services import connector_profile_runtime_patch as patch


class _FakeDelegate:
    """Stands in for upstream's ServiceTaskDelegate."""

    calls: list[tuple[str, dict, object]] = []

    @classmethod
    def call_connector(cls, operator_identifier, bpmn_params, spiff_task):
        cls.calls.append((operator_identifier, bpmn_params, spiff_task))
        return "{}"


_ORIGINAL_FAKE_CALL_CONNECTOR = _FakeDelegate.call_connector.__func__


@pytest.fixture
def delegate(monkeypatch):
    """Apply the patch against a fake delegate, then undo it."""
    import spiffworkflow_backend.services.service_task_service as sts

    _FakeDelegate.calls = []
    # ``patch.apply`` assigns directly to the fake class. Restore the original
    # method before each test so one test cannot wrap the previous test's
    # already-patched method.
    monkeypatch.setattr(
        _FakeDelegate,
        "call_connector",
        classmethod(_ORIGINAL_FAKE_CALL_CONNECTOR),
    )
    monkeypatch.setattr(sts, "ServiceTaskDelegate", _FakeDelegate, raising=False)
    monkeypatch.setattr(patch, "_PATCHED", False)
    patch.reset_catalogue_cache()
    yield _FakeDelegate
    patch.reset_catalogue_cache()


@pytest.fixture
def resolved(monkeypatch):
    """Control what a profile resolves to, without a database."""
    store: dict[tuple[str, str], dict] = {}

    from m8flow_backend.services import connector_profile_service as service

    def fake_resolve(connector_type, profile_name):
        try:
            return store[(connector_type, profile_name)]
        except KeyError:
            raise service.ConnectorProfileError(
                f"No '{profile_name}' profile.", status_code=404
            ) from None

    monkeypatch.setattr(
        service.ConnectorProfileService, "resolve_for_runtime", fake_resolve
    )
    return store


def _catalogue(monkeypatch, mapping):
    """Pin the operator -> declared parameter names catalogue."""
    monkeypatch.setattr(
        patch,
        "declared_parameter_names",
        lambda operator: mapping.get(operator),
    )


def test_profile_capable_task_without_a_profile_is_rejected(delegate, resolved):
    """Connector credentials must always come from an explicit profile."""
    from m8flow_backend.services.connector_profile_service import ConnectorProfileError

    patch.apply()
    with pytest.raises(ConnectorProfileError, match="profile must be selected"):
        delegate.call_connector("smtp/SendHTMLEmail", {}, "task")

    assert delegate.calls == []


def test_blank_profile_value_is_rejected(delegate, resolved):
    from m8flow_backend.services.connector_profile_service import ConnectorProfileError

    patch.apply()
    params = {"m8flow_profile": {"value": "   ", "type": "str"}}

    with pytest.raises(ConnectorProfileError, match="profile must be selected"):
        delegate.call_connector("smtp/SendHTMLEmail", params, "task")

    assert delegate.calls == []


def test_profile_values_are_injected(delegate, resolved, monkeypatch):
    patch.apply()
    resolved[("smtp", "smtp-production")] = {
        "smtp_host": "smtp.prod",
        "smtp_password": "pw",
    }
    _catalogue(monkeypatch, {"smtp/SendHTMLEmail": frozenset({"smtp_host", "smtp_password", "email_to"})})

    delegate.call_connector(
        "smtp/SendHTMLEmail",
        {
            "m8flow_profile": {"value": "smtp-production", "type": "str"},
            "email_to": {"value": "a@b.com", "type": "str"},
        },
        "task",
    )

    _, params, _ = delegate.calls[0]
    assert params["smtp_host"] == {"value": "smtp.prod", "type": "any"}
    assert params["smtp_password"] == {"value": "pw", "type": "any"}
    # The marker itself must not reach the proxy: it is not a connector param.
    assert "m8flow_profile" not in params
    # The author's own value survives.
    assert params["email_to"]["value"] == "a@b.com"


def test_an_author_typed_value_wins_over_the_profile(delegate, resolved, monkeypatch):
    """A value the author typed is deliberate and must not be overwritten."""
    patch.apply()
    resolved[("smtp", "prod")] = {"smtp_host": "from-profile"}
    _catalogue(monkeypatch, {"smtp/SendHTMLEmail": frozenset({"smtp_host"})})

    delegate.call_connector(
        "smtp/SendHTMLEmail",
        {
            "m8flow_profile": {"value": "prod", "type": "str"},
            "smtp_host": {"value": "typed-by-hand", "type": "str"},
        },
        "task",
    )

    assert delegate.calls[0][1]["smtp_host"]["value"] == "typed-by-hand"


@pytest.mark.parametrize("blank", [None, "", "   ", {"value": None}, {"value": ""}])
def test_a_blank_parameter_is_filled_from_the_profile(
    delegate, resolved, monkeypatch, blank
):
    patch.apply()
    resolved[("smtp", "prod")] = {"smtp_host": "from-profile"}
    _catalogue(monkeypatch, {"smtp/SendHTMLEmail": frozenset({"smtp_host"})})

    delegate.call_connector(
        "smtp/SendHTMLEmail",
        {"m8flow_profile": {"value": "prod", "type": "str"}, "smtp_host": blank},
        "task",
    )

    assert delegate.calls[0][1]["smtp_host"]["value"] == "from-profile"


def test_a_parameter_the_operator_does_not_declare_is_not_injected(
    delegate, resolved, monkeypatch
):
    """The proxy calls command(**params), so an undeclared name is fatal.

    n8n is the real case: TriggerWorkflow accepts neither base_url nor api_key,
    even though the profile holds both for the API operators.
    """
    patch.apply()
    resolved[("n8n", "main")] = {
        "base_url": "http://n8n:5678",
        "api_key": "k",
        "auth_header_value": "v",
    }
    _catalogue(monkeypatch, {"n8n/TriggerWorkflow": frozenset({"webhook_url", "auth_header_value"})})

    delegate.call_connector(
        "n8n/TriggerWorkflow",
        {"m8flow_profile": {"value": "main", "type": "str"}},
        "task",
    )

    _, params, _ = delegate.calls[0]
    assert "base_url" not in params
    assert "api_key" not in params
    assert params["auth_header_value"]["value"] == "v"


def test_injection_applies_to_in_process_http_operators(
    delegate, resolved, monkeypatch
):
    """http/* runs in-process, bypassing the proxy.

    The patch wraps call_connector above that branch, so profiles must still
    apply to those operators.
    """
    patch.apply()
    resolved[("http", "api")] = {"basic_auth_username": "u", "basic_auth_password": "p"}
    _catalogue(
        monkeypatch,
        {"http/GetRequest": frozenset({"url", "basic_auth_username", "basic_auth_password"})},
    )

    delegate.call_connector(
        "http/GetRequest",
        {
            "m8flow_profile": {"value": "api", "type": "str"},
            "url": {"value": "https://x", "type": "str"},
        },
        "task",
    )

    _, params, _ = delegate.calls[0]
    assert params["basic_auth_username"]["value"] == "u"
    assert params["basic_auth_password"]["value"] == "p"


def test_everything_is_injected_when_the_catalogue_is_unavailable(
    delegate, resolved, monkeypatch
):
    """An unreachable proxy must not silently drop credentials.

    With no catalogue there is nothing to filter against, so the profile is
    applied in full and the proxy decides. Dropping values here would look like
    a mysterious auth failure instead.
    """
    patch.apply()
    resolved[("smtp", "prod")] = {"smtp_host": "h", "smtp_password": "pw"}
    _catalogue(monkeypatch, {})  # returns None for any operator

    delegate.call_connector(
        "smtp/SendHTMLEmail",
        {"m8flow_profile": {"value": "prod", "type": "str"}},
        "task",
    )

    _, params, _ = delegate.calls[0]
    assert params["smtp_host"]["value"] == "h"
    assert params["smtp_password"]["value"] == "pw"


def test_an_unknown_profile_surfaces_the_error(delegate, resolved, monkeypatch):
    """Failing loudly beats calling a live system with no credentials."""
    from m8flow_backend.services.connector_profile_service import ConnectorProfileError

    patch.apply()
    _catalogue(monkeypatch, {"smtp/SendHTMLEmail": frozenset({"smtp_host"})})

    with pytest.raises(ConnectorProfileError):
        delegate.call_connector(
            "smtp/SendHTMLEmail",
            {"m8flow_profile": {"value": "does-not-exist", "type": "str"}},
            "task",
        )
    assert delegate.calls == []


def test_secret_values_are_never_logged(delegate, resolved, monkeypatch, caplog):
    patch.apply()
    resolved[("smtp", "prod")] = {"smtp_password": "SuperSecret123"}
    _catalogue(monkeypatch, {"smtp/SendHTMLEmail": frozenset({"smtp_password"})})

    with caplog.at_level("INFO"):
        delegate.call_connector(
            "smtp/SendHTMLEmail",
            {"m8flow_profile": {"value": "prod", "type": "str"}},
            "task",
        )

    assert "SuperSecret123" not in caplog.text
    assert "smtp_password" in caplog.text


def test_applying_twice_does_not_double_wrap(delegate, resolved):
    patch.apply()
    patch.apply()

    delegate.call_connector("unknown/Operation", {}, "task")

    assert len(delegate.calls) == 1


# ------------------------------------------------------------- the catalogue


def test_catalogue_parses_operator_parameter_names(monkeypatch):
    import spiffworkflow_backend.services.service_task_service as sts

    patch.reset_catalogue_cache()
    monkeypatch.setattr(
        sts.ServiceTaskService,
        "available_connectors",
        staticmethod(
            lambda: [
                {"id": "smtp/SendHTMLEmail", "parameters": [{"id": "smtp_host"}, {"id": "email_to"}]},
                {"id": "slack/PostMessage", "parameters": [{"id": "token"}]},
            ]
        ),
    )

    assert patch.declared_parameter_names("smtp/SendHTMLEmail") == frozenset(
        {"smtp_host", "email_to"}
    )
    assert patch.declared_parameter_names("slack/PostMessage") == frozenset({"token"})
    assert patch.declared_parameter_names("nope/Nope") is None
    patch.reset_catalogue_cache()


def test_an_empty_catalogue_does_not_replace_a_good_one(monkeypatch):
    """An empty list means the proxy is unreachable, not that there are none."""
    import spiffworkflow_backend.services.service_task_service as sts

    patch.reset_catalogue_cache()
    monkeypatch.setattr(
        sts.ServiceTaskService,
        "available_connectors",
        staticmethod(lambda: [{"id": "smtp/Send", "parameters": [{"id": "smtp_host"}]}]),
    )
    assert patch.declared_parameter_names("smtp/Send") == frozenset({"smtp_host"})

    monkeypatch.setattr(patch, "_catalogue_fetched_at", 0.0)
    monkeypatch.setattr(
        sts.ServiceTaskService, "available_connectors", staticmethod(lambda: [])
    )

    assert patch.declared_parameter_names("smtp/Send") == frozenset({"smtp_host"})
    patch.reset_catalogue_cache()


def test_a_failing_catalogue_fetch_is_survivable(monkeypatch):
    import spiffworkflow_backend.services.service_task_service as sts

    patch.reset_catalogue_cache()

    def boom():
        raise RuntimeError("proxy down")

    monkeypatch.setattr(
        sts.ServiceTaskService, "available_connectors", staticmethod(boom)
    )

    assert patch.declared_parameter_names("smtp/Send") is None
    patch.reset_catalogue_cache()
