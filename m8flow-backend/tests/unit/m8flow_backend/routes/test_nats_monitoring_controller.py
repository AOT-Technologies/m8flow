"""Authorization and scoping tests for the NATS monitoring endpoints.

The audit table deliberately does not inherit ``M8fTenantScopedMixin`` (see the model),
so none of the automatic tenant filtering in ``tenant_scoping_patch`` applies to it. That
makes the controller and query service the *only* thing standing between a tenant-admin and
another tenant's event history — so these tests carry more weight than usual.

Tests cover:
- 401 for unauthenticated callers on every endpoint
- 403 for an authenticated non-super-admin on broker-wide state
- non-super-admins pinned to their active tenant, and unable to opt out with allTenants
- super-admins able to cross tenants, but only by asking explicitly
- payload inspection gated on both the env flag and super-admin
- limit/page validation and server-side clamping
- 503 propagated when the broker is unreachable
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask, g

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.routes import nats_monitoring_controller as controller  # noqa: E402

TENANT = "tenant-acme"
OTHER_TENANT = "tenant-globex"


@pytest.fixture
def app():
    return Flask(__name__)  # NOSONAR - unit test, no HTTP server or CSRF involved


@pytest.fixture(autouse=True)
def stub_services(monkeypatch):
    """Replace both services with recorders, so these tests are about authorization."""
    calls: dict[str, dict] = {}

    class FakeAudit:
        @staticmethod
        def list_events(**kwargs):
            calls["list_events"] = kwargs
            return {"results": [], "pagination": {}}

        @staticmethod
        def summary(**kwargs):
            calls["summary"] = kwargs
            return {"byOutcome": {}}

        @staticmethod
        def get_event(event_id, **kwargs):
            calls["get_event"] = {"event_id": event_id, **kwargs}
            return {"eventId": event_id, "streamSeq": 42}

        @staticmethod
        def per_tenant():
            calls["per_tenant"] = {}
            return []

    class FakeMonitoring:
        @staticmethod
        def overview():
            calls["overview"] = {}
            return {"healthy": True}

        @staticmethod
        def streams():
            calls["streams"] = {}
            return {"streams": []}

        @staticmethod
        def get_messages(stream_name, **kwargs):
            calls["get_messages"] = {"stream_name": stream_name, **kwargs}
            return [{"seq": 42}]

    monkeypatch.setattr(controller, "NatsEventAuditQueryService", FakeAudit)
    monkeypatch.setattr(controller, "NatsMonitoringService", FakeMonitoring)
    monkeypatch.setattr(controller, "get_tenant_id", lambda: TENANT)
    monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: False)
    return calls


def _as(app, query: str = "", *, user=object(), super_admin: bool = False):
    """Request context for a caller with the given identity."""
    ctx = app.test_request_context(f"/?{query}")
    ctx.push()
    if user is not None:
        g.user = user
    g._m8flow_super_admin_request = super_admin
    return ctx


def _status(response) -> int:
    return response.status_code


BROKER_ENDPOINTS = [
    ("overview", lambda: controller.overview()),
    ("streams", lambda: controller.streams()),
    ("tenants", lambda: controller.tenants()),
    ("stream_messages", lambda: controller.stream_messages("M8FLOW_EVENTS")),
]

ALL_ENDPOINTS = BROKER_ENDPOINTS + [
    ("list_events", lambda: controller.list_events()),
    ("events_summary", lambda: controller.events_summary()),
    ("get_event", lambda: controller.get_event("evt-1")),
]


class TestUnauthenticated:
    @pytest.mark.parametrize("name,call", ALL_ENDPOINTS, ids=[n for n, _ in ALL_ENDPOINTS])
    def test_every_endpoint_401s_without_a_user(self, app, name, call):
        ctx = _as(app, user=None)
        try:
            assert _status(call()) == 401
        finally:
            ctx.pop()


class TestBrokerStateIsSuperAdminOnly:
    """/varz and /jsz are reported per account, not per tenant, so there is no honest
    way to show them to a tenant-admin."""

    @pytest.mark.parametrize(
        "name,call", BROKER_ENDPOINTS, ids=[n for n, _ in BROKER_ENDPOINTS]
    )
    def test_403_for_an_authenticated_non_super_admin(self, app, name, call):
        ctx = _as(app, super_admin=False)
        try:
            assert _status(call()) == 403
        finally:
            ctx.pop()

    @pytest.mark.parametrize(
        "name,call",
        [e for e in BROKER_ENDPOINTS if e[0] != "stream_messages"],
        ids=["overview", "streams", "tenants"],
    )
    def test_200_for_a_super_admin(self, app, name, call):
        ctx = _as(app, super_admin=True)
        try:
            assert _status(call()) == 200
        finally:
            ctx.pop()


class TestEventHistoryTenantScoping:
    def test_a_non_super_admin_is_pinned_to_the_active_tenant(self, app, stub_services):
        ctx = _as(app, super_admin=False)
        try:
            controller.list_events()
        finally:
            ctx.pop()

        assert stub_services["list_events"]["tenant_id"] == TENANT
        assert stub_services["list_events"]["all_tenants"] is False

    def test_a_non_super_admin_cannot_opt_into_all_tenants(self, app, stub_services):
        """The dangerous one: allTenants must be ignored, not honoured."""
        ctx = _as(app, "allTenants=true", super_admin=False)
        try:
            controller.list_events()
        finally:
            ctx.pop()

        assert stub_services["list_events"]["all_tenants"] is False
        assert stub_services["list_events"]["tenant_id"] == TENANT

    def test_a_non_super_admin_cannot_name_another_tenant(self, app, stub_services):
        ctx = _as(app, f"tenantId={OTHER_TENANT}", super_admin=False)
        try:
            controller.list_events()
        finally:
            ctx.pop()

        assert stub_services["list_events"]["tenant_id"] == TENANT

    def test_a_super_admin_defaults_to_their_active_tenant(self, app, stub_services):
        """Cross-tenant is never implicit, even for a super-admin."""
        ctx = _as(app, super_admin=True)
        try:
            controller.list_events()
        finally:
            ctx.pop()

        assert stub_services["list_events"]["all_tenants"] is False
        assert stub_services["list_events"]["tenant_id"] == TENANT

    def test_a_super_admin_can_ask_for_all_tenants(self, app, stub_services):
        ctx = _as(app, "allTenants=true", super_admin=True)
        try:
            controller.list_events()
        finally:
            ctx.pop()

        assert stub_services["list_events"]["all_tenants"] is True

    def test_a_super_admin_can_inspect_a_named_tenant(self, app, stub_services):
        ctx = _as(app, f"tenantId={OTHER_TENANT}", super_admin=True)
        try:
            controller.list_events()
        finally:
            ctx.pop()

        assert stub_services["list_events"]["tenant_id"] == OTHER_TENANT
        assert stub_services["list_events"]["all_tenants"] is False

    def test_summary_uses_the_same_scoping(self, app, stub_services):
        ctx = _as(app, "allTenants=true", super_admin=False)
        try:
            controller.events_summary()
        finally:
            ctx.pop()

        assert stub_services["summary"]["all_tenants"] is False
        assert stub_services["summary"]["tenant_id"] == TENANT

    def test_get_event_uses_the_same_scoping(self, app, stub_services):
        ctx = _as(app, "allTenants=true", super_admin=False)
        try:
            controller.get_event("evt-1")
        finally:
            ctx.pop()

        assert stub_services["get_event"]["all_tenants"] is False
        assert stub_services["get_event"]["tenant_id"] == TENANT

    def test_no_active_tenant_is_passed_through_as_none(self, app, stub_services, monkeypatch):
        """The query service turns this into a 400; the controller must not invent a tenant."""
        monkeypatch.setattr(
            controller, "get_tenant_id", lambda: (_ for _ in ()).throw(RuntimeError())
        )
        ctx = _as(app, super_admin=False)
        try:
            controller.list_events()
        finally:
            ctx.pop()

        assert stub_services["list_events"]["tenant_id"] is None
        assert stub_services["list_events"]["all_tenants"] is False


class TestPayloadInspectionGating:
    def test_stream_messages_403s_when_inspection_is_disabled(self, app):
        ctx = _as(app, super_admin=True)
        try:
            assert _status(controller.stream_messages("M8FLOW_EVENTS")) == 403
        finally:
            ctx.pop()

    def test_stream_messages_works_for_super_admin_when_enabled(
        self, app, monkeypatch, stub_services
    ):
        monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: True)
        ctx = _as(app, super_admin=True)
        try:
            assert _status(controller.stream_messages("M8FLOW_EVENTS")) == 200
        finally:
            ctx.pop()

        assert stub_services["get_messages"]["stream_name"] == "M8FLOW_EVENTS"

    def test_include_payload_403s_when_inspection_is_disabled(self, app):
        ctx = _as(app, "includePayload=true", super_admin=True)
        try:
            assert _status(controller.get_event("evt-1")) == 403
        finally:
            ctx.pop()

    def test_include_payload_403s_for_a_non_super_admin_even_when_enabled(
        self, app, monkeypatch
    ):
        monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: True)
        ctx = _as(app, "includePayload=true", super_admin=False)
        try:
            assert _status(controller.get_event("evt-1")) == 403
        finally:
            ctx.pop()

    def test_event_without_include_payload_never_touches_nats(self, app, stub_services):
        ctx = _as(app, super_admin=True)
        try:
            assert _status(controller.get_event("evt-1")) == 200
        finally:
            ctx.pop()

        assert "get_messages" not in stub_services

    def test_include_payload_reads_by_the_stored_stream_sequence(
        self, app, monkeypatch, stub_services
    ):
        """The row stores a pointer; the payload is fetched from NATS, never from the DB."""
        monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: True)
        ctx = _as(app, "includePayload=true", super_admin=True)
        try:
            assert _status(controller.get_event("evt-1")) == 200
        finally:
            ctx.pop()

        assert stub_services["get_messages"]["start_seq"] == 42
        assert stub_services["get_messages"]["limit"] == 1


class TestParameterHandling:
    def test_non_integer_page_is_a_400(self, app):
        ctx = _as(app, "page=banana", super_admin=False)
        try:
            assert _status(controller.list_events()) == 400
        finally:
            ctx.pop()

    def test_filters_are_forwarded(self, app, stub_services):
        ctx = _as(
            app,
            "outcome=rejected_auth&processIdentifier=g%2Fp&username=alice&worker=consumer"
            "&failuresOnly=true&since=100&until=200&page=3&perPage=10",
            super_admin=False,
        )
        try:
            controller.list_events()
        finally:
            ctx.pop()

        forwarded = stub_services["list_events"]
        assert forwarded["outcome"] == "rejected_auth"
        assert forwarded["process_identifier"] == "g/p"
        assert forwarded["username"] == "alice"
        assert forwarded["worker"] == "consumer"
        assert forwarded["failures_only"] is True
        assert forwarded["since_in_seconds"] == 100
        assert forwarded["until_in_seconds"] == 200
        assert forwarded["page"] == 3
        assert forwarded["per_page"] == 10

    def test_message_limit_is_forwarded_for_the_service_to_clamp(
        self, app, monkeypatch, stub_services
    ):
        monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: True)
        ctx = _as(app, "limit=100000&startSeq=5", super_admin=True)
        try:
            controller.stream_messages("M8FLOW_EVENTS")
        finally:
            ctx.pop()

        assert stub_services["get_messages"]["limit"] == 100000
        assert stub_services["get_messages"]["start_seq"] == 5


class TestBrokerErrorsPropagate:
    def test_503_is_returned_not_swallowed(self, app, monkeypatch):
        from spiffworkflow_backend.exceptions.api_error import ApiError

        class Down:
            @staticmethod
            def overview():
                raise ApiError(
                    error_code="nats_monitoring_unavailable",
                    message="broker unreachable",
                    status_code=503,
                )

        monkeypatch.setattr(controller, "NatsMonitoringService", Down)
        ctx = _as(app, super_admin=True)
        try:
            assert _status(controller.overview()) == 503
        finally:
            ctx.pop()
