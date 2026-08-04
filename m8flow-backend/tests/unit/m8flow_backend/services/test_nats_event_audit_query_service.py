"""Tenant-isolation and query tests for NatsEventAuditQueryService.

``NatsEventAuditModel`` deliberately does not inherit ``M8fTenantScopedMixin`` — the
automatic filtering in ``tenant_scoping_patch`` would silently reduce the cross-tenant views
this feature exists to provide down to whichever tenant a super-admin had selected. The cost
of that choice is that **this service is the only thing enforcing tenant isolation on this
table**, so these tests are the safety net for it.

Tests cover:
- reads are constrained to one tenant unless all_tenants is asked for explicitly
- a missing tenant fails closed with 400 rather than returning everything
- another tenant's event is a 404, not a 403, so ids cannot be probed
- summary and per-tenant aggregation, including un-attributable rows
- filters, pagination, page-size cap, and rejection of unknown outcomes
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from flask import Flask

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from m8flow_backend.models.nats_event_audit import (  # noqa: E402
    NatsEventAuditModel,
    NatsEventOutcome,
    NatsEventWorker,
)
from m8flow_backend.services.nats_event_audit_query_service import (  # noqa: E402
    MAX_PAGE_SIZE,
    NatsEventAuditQueryService as Q,
)
from spiffworkflow_backend.exceptions.api_error import ApiError  # noqa: E402
from spiffworkflow_backend.models.db import add_listeners, db  # noqa: E402

ACME = "tenant-acme"
GLOBEX = "tenant-globex"


@pytest.fixture
def app():
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        add_listeners()
        yield app
        db.session.remove()
        db.drop_all()


def _tenant(tenant_id: str, slug: str) -> M8flowTenantModel:
    tenant = M8flowTenantModel(
        id=tenant_id,
        name=slug.title(),
        slug=slug,
        status=TenantStatus.ACTIVE,
        created_by="admin",
        modified_by="admin",
    )
    db.session.add(tenant)
    db.session.commit()
    return tenant


def _row(**kwargs) -> NatsEventAuditModel:
    defaults = {
        "worker": NatsEventWorker.consumer.value,
        "outcome": NatsEventOutcome.instantiated.value,
        "completed_at_in_seconds": 1000,
    }
    row = NatsEventAuditModel(**{**defaults, **kwargs})
    db.session.add(row)
    db.session.commit()
    return row


@pytest.fixture
def seeded(app):
    """Two tenants plus one un-attributable row."""
    _tenant(ACME, "acme")
    _tenant(GLOBEX, "globex")

    _row(tenant_id=ACME, event_id="acme-ok", process_identifier="g/p", username="alice")
    _row(
        tenant_id=ACME,
        event_id="acme-bad",
        outcome=NatsEventOutcome.rejected_auth.value,
        error_message="invalid api_key",
        process_identifier="g/p",
        username="bob",
    )
    _row(
        tenant_id=ACME,
        event_id="acme-queued",
        outcome=NatsEventOutcome.queued.value,
        completed_at_in_seconds=None,
    )
    _row(tenant_id=GLOBEX, event_id="globex-ok", username="carol")
    _row(
        tenant_id=None,
        event_id=None,
        outcome=NatsEventOutcome.invalid_payload.value,
        error_message="malformed subject",
    )
    return app


class TestTenantIsolation:
    def test_a_tenant_sees_only_its_own_events(self, seeded):
        result = Q.list_events(tenant_id=ACME)

        ids = {r["eventId"] for r in result["results"]}
        assert ids == {"acme-ok", "acme-bad", "acme-queued"}
        assert result["pagination"]["total"] == 3

    def test_another_tenants_events_are_not_reachable(self, seeded):
        result = Q.list_events(tenant_id=GLOBEX)

        assert {r["eventId"] for r in result["results"]} == {"globex-ok"}

    def test_all_tenants_returns_everything_including_unattributed(self, seeded):
        result = Q.list_events(tenant_id=None, all_tenants=True)

        assert result["pagination"]["total"] == 5
        assert any(r["tenantId"] is None for r in result["results"])

    def test_no_tenant_and_no_all_tenants_fails_closed(self, seeded):
        """The dangerous default: this must refuse, not return every tenant's rows."""
        with pytest.raises(ApiError) as exc:
            Q.list_events(tenant_id=None)

        assert exc.value.status_code == 400
        assert exc.value.error_code == "tenant_context_required"

    def test_summary_is_tenant_scoped(self, seeded):
        acme = Q.summary(tenant_id=ACME)
        globex = Q.summary(tenant_id=GLOBEX)

        assert acme["total"] == 3
        assert acme["instantiated"] == 1
        assert acme["failed"] == 1
        assert acme["queued"] == 1
        assert globex["total"] == 1

    def test_summary_fails_closed_without_a_tenant(self, seeded):
        with pytest.raises(ApiError) as exc:
            Q.summary(tenant_id=None)
        assert exc.value.status_code == 400


class TestGetEvent:
    def test_returns_the_tenants_own_event(self, seeded):
        event = Q.get_event("acme-ok", tenant_id=ACME)

        assert event["eventId"] == "acme-ok"
        assert event["processIdentifier"] == "g/p"

    def test_another_tenants_event_is_a_404_not_a_403(self, seeded):
        """A 403 would confirm the id exists, which is a probing oracle."""
        with pytest.raises(ApiError) as exc:
            Q.get_event("globex-ok", tenant_id=ACME)

        assert exc.value.status_code == 404

    def test_an_unknown_event_is_the_same_404(self, seeded):
        with pytest.raises(ApiError) as exc:
            Q.get_event("does-not-exist", tenant_id=ACME)

        assert exc.value.status_code == 404

    def test_a_super_admin_can_read_across_tenants(self, seeded):
        event = Q.get_event("globex-ok", tenant_id=None, all_tenants=True)

        assert event["tenantId"] == GLOBEX


class TestFilters:
    def test_by_outcome(self, seeded):
        result = Q.list_events(tenant_id=ACME, outcome=NatsEventOutcome.rejected_auth.value)

        assert {r["eventId"] for r in result["results"]} == {"acme-bad"}

    def test_failures_only_excludes_success_and_queued(self, seeded):
        result = Q.list_events(tenant_id=ACME, failures_only=True)

        assert {r["eventId"] for r in result["results"]} == {"acme-bad"}

    def test_by_username(self, seeded):
        result = Q.list_events(tenant_id=ACME, username="bob")

        assert {r["eventId"] for r in result["results"]} == {"acme-bad"}

    def test_by_event_id(self, seeded):
        result = Q.list_events(tenant_id=ACME, event_id="acme-ok")

        assert len(result["results"]) == 1

    def test_an_unknown_outcome_is_rejected(self, seeded):
        with pytest.raises(ApiError) as exc:
            Q.list_events(tenant_id=ACME, outcome="not-a-real-outcome")

        assert exc.value.status_code == 400
        assert exc.value.error_code == "invalid_outcome"

    def test_date_range_filters_on_queued_time(self, app):
        """Filtering on completion would hide in-flight rows and make the backlog look
        empty, which is the opposite of useful."""
        _tenant(ACME, "acme")
        row = _row(
            tenant_id=ACME,
            event_id="in-flight",
            outcome=NatsEventOutcome.queued.value,
            completed_at_in_seconds=None,
        )
        queued_at = row.created_at_in_seconds

        assert Q.list_events(tenant_id=ACME, since_in_seconds=queued_at)["pagination"]["total"] == 1
        assert (
            Q.list_events(tenant_id=ACME, since_in_seconds=queued_at + 10)["pagination"]["total"]
            == 0
        )


class TestPagination:
    def test_pages_results_and_reports_totals(self, app):
        _tenant(ACME, "acme")
        for i in range(7):
            _row(tenant_id=ACME, event_id=f"e{i}")

        page1 = Q.list_events(tenant_id=ACME, page=1, per_page=3)
        page3 = Q.list_events(tenant_id=ACME, page=3, per_page=3)

        assert len(page1["results"]) == 3
        assert len(page3["results"]) == 1
        assert page1["pagination"]["total"] == 7
        assert page1["pagination"]["pages"] == 3

    def test_per_page_is_capped(self, seeded):
        result = Q.list_events(tenant_id=ACME, per_page=100_000)

        assert result["pagination"]["perPage"] == MAX_PAGE_SIZE

    def test_newest_first(self, app):
        _tenant(ACME, "acme")
        _row(tenant_id=ACME, event_id="older")
        _row(tenant_id=ACME, event_id="newer")

        result = Q.list_events(tenant_id=ACME)

        assert result["results"][0]["eventId"] == "newer"


class TestSummaryCounts:
    def test_counts_suppressed_duplicate_deliveries(self, app):
        _tenant(ACME, "acme")
        _row(tenant_id=ACME, event_id="a", duplicate_count=3)
        _row(tenant_id=ACME, event_id="b", duplicate_count=2)

        assert Q.summary(tenant_id=ACME)["duplicateDeliveries"] == 5

    def test_duplicate_total_is_zero_not_none_when_there_are_none(self, app):
        _tenant(ACME, "acme")
        _row(tenant_id=ACME, event_id="a")

        assert Q.summary(tenant_id=ACME)["duplicateDeliveries"] == 0


class TestPerTenant:
    def test_groups_counts_by_tenant_and_resolves_slugs(self, seeded):
        rows = {entry["tenantId"]: entry for entry in Q.per_tenant()}

        assert rows[ACME]["tenantSlug"] == "acme"
        assert rows[ACME]["queued"] == 1
        assert rows[ACME]["instantiated"] == 1
        assert rows[ACME]["failed"] == 1
        assert rows[ACME]["total"] == 3
        assert rows[GLOBEX]["tenantSlug"] == "globex"

    def test_surfaces_unattributable_rows_rather_than_dropping_them(self, seeded):
        rows = {entry["tenantId"]: entry for entry in Q.per_tenant()}

        assert None in rows, "a malformed-subject row must still be visible somewhere"
        assert rows[None]["tenantSlug"] == "(unattributed)"
        assert rows[None]["failed"] == 1

    def test_orders_worst_backlog_first(self, app):
        _tenant(ACME, "acme")
        _tenant(GLOBEX, "globex")
        _row(tenant_id=GLOBEX, event_id="g1", outcome=NatsEventOutcome.queued.value)
        _row(tenant_id=GLOBEX, event_id="g2", outcome=NatsEventOutcome.queued.value)
        _row(tenant_id=ACME, event_id="a1", outcome=NatsEventOutcome.queued.value)

        assert [e["tenantId"] for e in Q.per_tenant()] == [GLOBEX, ACME]

    def test_reports_last_activity(self, seeded):
        rows = {entry["tenantId"]: entry for entry in Q.per_tenant()}

        assert rows[ACME]["lastActivityInSeconds"] > 0
