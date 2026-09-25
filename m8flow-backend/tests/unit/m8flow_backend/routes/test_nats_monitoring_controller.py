"""Scoping and gating tests for the NATS monitoring controller, called directly.

These stub the route-level YAML gate open (``allow_uri`` -> True) so they exercise the
controller's own logic: super-admin-only broker state, event-history tenant scoping (kept
correct even though the YAML grant is super-admin only today), payload-inspection gating
and parameter handling. The real super-admin-only YAML enforcement is covered end to end
in test_nats_monitoring_permissions.py.
"""

from __future__ import annotations

import pytest
from flask import Flask, g

from m8flow_backend.errors import ApiError
from m8flow_backend.routes import nats_monitoring_controller as controller
from m8flow_backend.services import nats_event_audit_query_service as query_service_module

TENANT = "tenant-acme"
OTHER_TENANT = "tenant-globex"


@pytest.fixture
def app():
    return Flask(__name__)  # NOSONAR - unit test, no HTTP server or CSRF involved


@pytest.fixture(autouse=True)
def stub_services(monkeypatch):
    monkeypatch.setattr("m8flow_backend.authorization.decorators.allow_uri", lambda *_a, **_k: True)
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
    monkeypatch.setattr(controller, "current_tenant_id_or_none", lambda: TENANT)
    monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: False)
    return calls


def _as(app, query: str = "", *, user=object(), super_admin: bool = False):
    """Request context for a caller with the given identity."""
    ctx = app.test_request_context(f"/?{query}")
    ctx.push()
    if user is not None:
        g.user = user
    g._test_super_admin = super_admin
    return ctx


@pytest.fixture(autouse=True)
def super_admin_from_g(monkeypatch):
    monkeypatch.setattr(controller, "is_super_admin_request", lambda: bool(getattr(g, "_test_super_admin", False)))


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


@pytest.mark.parametrize("enabled", [True, False])
def test_event_list_reports_whether_payload_inspection_is_enabled(app, monkeypatch, enabled):
    monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: enabled)
    ctx = _as(app, super_admin=False)
    try:
        response = controller.list_events()
        assert _status(response) == 200
        assert response.get_json()["messageInspectionEnabled"] is enabled
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
        monkeypatch.setattr(controller, "current_tenant_id_or_none", lambda: None)
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

    def test_include_payload_works_for_a_non_super_admin_when_enabled(
        self, app, monkeypatch, stub_services
    ):
        """With the YAML gate stubbed open, a non-super-admin's payload read stays safe:
        the row was already tenant-filtered by `_audit_scope()` before the payload fetch.
        (Today the YAML grant is super-admin only, so this is defence in depth.)"""
        monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: True)
        ctx = _as(app, "includePayload=true", super_admin=False)
        try:
            assert _status(controller.get_event("evt-1")) == 200
        finally:
            ctx.pop()

        assert stub_services["get_messages"]["start_seq"] == 42
        assert stub_services["get_messages"]["limit"] == 1

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

    def test_include_payload_cannot_reach_another_tenants_event(
        self, app, monkeypatch, stub_services
    ):
        """`includePayload=true` must not become a way around the tenant filter.

        A cross-tenant id 404s inside `NatsEventAuditQueryService.get_event` (verified against
        a real database in test_nats_event_audit_query_service.py). What is asserted here is
        the *ordering* the controller depends on: that lookup runs before the payload branch,
        so the 404 propagates unchanged and NATS is never read. If the branches were ever
        reordered — payload fetched from the requested streamSeq before the row was
        authorized — this fails.
        """
        class Scoped:
            @staticmethod
            def get_event(event_id, **kwargs):
                raise ApiError(
                    error_code="nats_event_not_found",
                    message=f"No NATS event history for id '{event_id}'.",
                    status_code=404,
                )

        monkeypatch.setattr(controller, "NatsEventAuditQueryService", Scoped)
        monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: True)
        ctx = _as(app, "includePayload=true", super_admin=False)
        try:
            assert _status(controller.get_event("globex-only")) == 404
        finally:
            ctx.pop()

        assert "get_messages" not in stub_services, "payload was fetched for an unauthorized row"

    def test_include_payload_404s_the_same_way_for_an_id_that_does_not_exist(
        self, app, monkeypatch, stub_services
    ):
        """Same response either way, so the flag cannot be used to probe for foreign ids."""
        class Missing:
            @staticmethod
            def get_event(event_id, **kwargs):
                raise ApiError(
                    error_code="nats_event_not_found",
                    message=f"No NATS event history for id '{event_id}'.",
                    status_code=404,
                )

        monkeypatch.setattr(controller, "NatsEventAuditQueryService", Missing)
        monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: True)
        ctx = _as(app, "includePayload=true", super_admin=False)
        try:
            assert _status(controller.get_event("no-such-id")) == 404
        finally:
            ctx.pop()


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


class TestPayloadStreamIsNotCallerControlled:
    """The stream a payload is read from must come from the row, not the request.

    An audit row records a bare JetStream sequence, which identifies a message only *within
    the stream it was published to*. Authorizing the row and then letting the caller name
    the stream pairs an authorized sequence with an unauthorized stream: a tenant-admin
    could ask for their own event at sequence N against the notifications stream and get
    whatever message sits at position N there -- another tenant's. The tenant filter on the
    row does not constrain that second lookup, so the stream is derived server-side.
    """

    @staticmethod
    def _row(worker: str, monkeypatch, seq: int = 42):
        class Audit:
            @staticmethod
            def get_event(event_id, **kwargs):
                return {"eventId": event_id, "streamSeq": seq, "worker": worker}

        monkeypatch.setattr(controller, "NatsEventAuditQueryService", Audit)
        monkeypatch.setattr(controller, "nats_message_inspection_enabled", lambda: True)

    def test_a_caller_supplied_stream_name_is_ignored(self, app, monkeypatch, stub_services):
        """The regression guard: this is the cross-tenant read the parameter allowed."""
        self._row("consumer", monkeypatch)
        ctx = _as(app, "includePayload=true&streamName=M8FLOW_NOTIFICATIONS", super_admin=False)
        try:
            assert _status(controller.get_event("my-own-event")) == 200
        finally:
            ctx.pop()

        assert stub_services["get_messages"]["stream_name"] == "M8FLOW_EVENTS", (
            "payload was read from a stream named by the caller, pairing an authorized "
            "sequence with an unauthorized stream"
        )

    def test_the_events_stream_is_used_for_a_consumer_row(self, app, monkeypatch, stub_services):
        self._row("consumer", monkeypatch)
        ctx = _as(app, "includePayload=true", super_admin=True)
        try:
            controller.get_event("evt-1")
        finally:
            ctx.pop()

        assert stub_services["get_messages"]["stream_name"] == "M8FLOW_EVENTS"

    def test_the_notifications_stream_is_used_for_a_notification_row(
        self, app, monkeypatch, stub_services
    ):
        """Deriving from the worker must actually distinguish the streams, or the fix
        would quietly read the wrong one for notification events."""
        self._row("notification_worker", monkeypatch)
        ctx = _as(app, "includePayload=true", super_admin=True)
        try:
            controller.get_event("evt-1")
        finally:
            ctx.pop()

        assert stub_services["get_messages"]["stream_name"] == "M8FLOW_NOTIFICATIONS"

    def test_the_sequence_still_comes_from_the_row(self, app, monkeypatch, stub_services):
        """Guard the other half of the pointer while we are here."""
        self._row("consumer", monkeypatch, seq=7)
        ctx = _as(app, "includePayload=true&startSeq=999", super_admin=False)
        try:
            controller.get_event("evt-1")
        finally:
            ctx.pop()

        assert stub_services["get_messages"]["start_seq"] == 7

    def test_stream_names_follow_configuration(self, app, monkeypatch, stub_services):
        """Deployments may rename their streams; the resolver must not hardcode defaults."""
        monkeypatch.setattr(query_service_module, "nats_events_stream_name", lambda: "RENAMED_EVENTS")
        self._row("consumer", monkeypatch)
        ctx = _as(app, "includePayload=true", super_admin=True)
        try:
            controller.get_event("evt-1")
        finally:
            ctx.pop()

        assert stub_services["get_messages"]["stream_name"] == "RENAMED_EVENTS"
