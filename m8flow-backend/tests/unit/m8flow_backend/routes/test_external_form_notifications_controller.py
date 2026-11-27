"""Admin view of external-form notification delivery, and who may see it.

Until these endpoints existed, a failed notification could only be diagnosed from the
worker's stdout and could only be retried by editing the database. They expose delivery
status and a resend, so the tenant isolation and RBAC around them matter as much as the
behaviour: the responses carry recipient email addresses, and the resend writes.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, import_yaml, sync_groups
from m8flow_backend.models.external_form_request import ExternalFormRequestModel
from m8flow_backend.models.external_form_request import ExternalFormRequestStatus
from m8flow_backend.secrets import add_secret

TENANT = "t1"


def _login_user(client, db_session, *, username: str, groups: list[str], tenant_id: str = TENANT):
    from m8flow_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id, name=tenant_id)
    user = ensure_user(
        db_session,
        username=username,
        service="https://example.test/realms/m8flow",
        service_id=username,
    )
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    token = encode_auth_token(user=user)
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return user, {"Authorization": f"Bearer {token}"}


def _request_row(
    db_session,
    *,
    tenant_id: str = TENANT,
    status: str = "pending",
    reference_id: str = "ref-1",
    notified_at: int | None = None,
    last_error: str | None = None,
    process_instance_id: int = 601,
    created_at: int | None = 10,
):
    row = ExternalFormRequestModel(
        m8f_tenant_id=tenant_id,
        reference_id=reference_id,
        process_instance_id=process_instance_id,
        task_guid="task-guid-1",
        recipient_user_id=1,
        email="recipient@example.test",
        external_form_url="https://forms.example/f1",
        status=status,
        attempts=1,
        notified_at_in_seconds=notified_at,
        last_error=last_error,
        created_at=datetime.fromtimestamp(created_at, timezone.utc) if created_at is not None else None,
        updated_at=datetime.fromtimestamp(created_at, timezone.utc) if created_at is not None else None,
    )
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture
def _smtp_configured(db_session):
    user = ensure_user(
        db_session,
        username="smtp-owner",
        service="https://example.test/realms/m8flow",
        service_id="smtp-owner",
    )
    for key, value in (
        ("NATS_SMTP_HOST", "smtp.example.test"),
        ("NATS_SMTP_FROM_EMAIL", "noreply@example.test"),
    ):
        add_secret(db_session, tenant_id=TENANT, key=key, value=value, user_id=user.id)
    db_session.commit()


def test_smtp_status_reports_missing_keys_without_values(client, db_session):
    _, headers = _login_user(client, db_session, username="admin1", groups=["t1:tenant-admin"])

    response = client.get("/v1.0/m8flow/external-form-notifications/smtp-status", headers=headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["configured"] is False
    assert set(body["missing_required_keys"]) == {"NATS_SMTP_HOST", "NATS_SMTP_FROM_EMAIL"}
    assert "NATS_SMTP_PASSWORD" in body["optional_keys"]


def test_smtp_status_reports_configured(client, db_session, _smtp_configured):
    _, headers = _login_user(client, db_session, username="admin2", groups=["t1:tenant-admin"])

    body = client.get("/v1.0/m8flow/external-form-notifications/smtp-status", headers=headers).get_json()

    assert body["configured"] is True
    assert body["reason"] is None
    assert "smtp.example.test" not in str(body)


def test_notification_list_omits_the_reference_id(client, db_session):
    row = _request_row(db_session, status="failed", last_error="535 bad credentials")
    _, headers = _login_user(client, db_session, username="admin3", groups=["t1:tenant-admin"])

    response = client.get("/v1.0/m8flow/external-form-notifications", headers=headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"]["total"] == 1
    [payload] = body["results"]
    assert payload["id"] == row.id
    assert payload["status"] == "failed"
    assert payload["last_error"] == "535 bad credentials"
    # The reference id is the credential in the recipient's emailed link.
    assert "reference_id" not in payload
    assert row.reference_id not in str(body)


def test_notification_list_is_tenant_scoped(client, db_session):
    _request_row(db_session, reference_id="ref-mine")
    _request_row(db_session, tenant_id="t2", reference_id="ref-theirs")
    _, headers = _login_user(client, db_session, username="admin4", groups=["t1:tenant-admin"])

    body = client.get("/v1.0/m8flow/external-form-notifications", headers=headers).get_json()

    assert body["pagination"]["total"] == 1
    assert body["results"][0]["email"] == "recipient@example.test"


def test_notification_list_filters_by_status_and_instance(client, db_session):
    _request_row(db_session, reference_id="ref-a", status="failed", process_instance_id=601)
    _request_row(db_session, reference_id="ref-b", status="pending", process_instance_id=602)
    _, headers = _login_user(client, db_session, username="admin5", groups=["t1:tenant-admin"])

    by_status = client.get("/v1.0/m8flow/external-form-notifications?status=failed", headers=headers).get_json()
    assert [row["status"] for row in by_status["results"]] == ["failed"]

    by_instance = client.get(
        "/v1.0/m8flow/external-form-notifications?process_instance_id=602", headers=headers
    ).get_json()
    assert [row["process_instance_id"] for row in by_instance["results"]] == [602]


def test_notification_list_places_null_created_at_rows_last(client, db_session):
    known = _request_row(db_session, reference_id="ref-known", created_at=20)
    null_older_id = _request_row(db_session, reference_id="ref-null-older", created_at=None)
    null_newer_id = _request_row(db_session, reference_id="ref-null-newer", created_at=None)
    # HostBase fills timestamps for new ORM rows; emulate a legacy/partially
    # migrated row explicitly so the endpoint's NULL ordering is exercised.
    db_session.execute(
        text(
            "UPDATE m8flow_external_form_requests "
            "SET created_at = NULL, updated_at = NULL WHERE id IN (:older, :newer)"
        ),
        {"older": null_older_id.id, "newer": null_newer_id.id},
    )
    db_session.commit()
    _, headers = _login_user(client, db_session, username="admin-order", groups=["t1:tenant-admin"])

    body = client.get("/v1.0/m8flow/external-form-notifications", headers=headers).get_json()

    assert [row["id"] for row in body["results"]] == [known.id, null_newer_id.id, null_older_id.id]
    assert body["results"][1]["created_at"] is None


def test_resend_reissues_an_expired_parked_request(client, db_session):
    """M8F-575 issue 1: a parked request past its TTL answered 200 "requeued" and was never
    sent. Resend now issues a fresh link with a new expiry."""
    row = _request_row(db_session, status=ExternalFormRequestStatus.smtp_unconfigured.value)
    row.expires_at_in_seconds = 1
    db_session.commit()
    _, headers = _login_user(client, db_session, username="admin6", groups=["t1:tenant-admin"])

    response = client.post(f"/v1.0/m8flow/external-form-notifications/{row.id}/resend", headers=headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "pending"
    assert body["expires_at_in_seconds"] > int(time.time())
    # The new link's credential must never be handed to the admin.
    assert "reference_id" not in body
    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.pending.value
    assert row.attempts == 0
    assert row.reference_id != "ref-1"
    assert row.expires_at_in_seconds == body["expires_at_in_seconds"]


def test_resend_rejects_a_completed_request(client, db_session):
    row = _request_row(db_session, status=ExternalFormRequestStatus.completed.value)
    _, headers = _login_user(client, db_session, username="admin7", groups=["t1:tenant-admin"])

    response = client.post(f"/v1.0/m8flow/external-form-notifications/{row.id}/resend", headers=headers)

    assert response.status_code == 409
    assert response.get_json()["error_code"] == "external_form_request_not_resendable"


def test_resend_cannot_reach_another_tenants_request(client, db_session):
    row = _request_row(
        db_session,
        tenant_id="t2",
        reference_id="ref-other",
        status=ExternalFormRequestStatus.smtp_unconfigured.value,
    )
    _, headers = _login_user(client, db_session, username="admin8", groups=["t1:tenant-admin"])

    response = client.post(f"/v1.0/m8flow/external-form-notifications/{row.id}/resend", headers=headers)

    assert response.status_code == 404
    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.smtp_unconfigured.value


def test_a_non_admin_role_cannot_read_or_resend(client, db_session):
    """Recipient email addresses and a write are behind these routes, so the
    task-working roles must not reach them."""
    row = _request_row(db_session, status=ExternalFormRequestStatus.smtp_unconfigured.value)
    _, headers = _login_user(client, db_session, username="editor1", groups=["t1:editor"])

    assert client.get("/v1.0/m8flow/external-form-notifications", headers=headers).status_code == 403
    assert (
        client.get("/v1.0/m8flow/external-form-notifications/smtp-status", headers=headers).status_code == 403
    )
    resend = client.post(f"/v1.0/m8flow/external-form-notifications/{row.id}/resend", headers=headers)
    assert resend.status_code == 403
    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.smtp_unconfigured.value


def test_an_integrator_can_read_and_resend(client, db_session):
    """The role that owns the NATS_SMTP_* secrets is the one that fixes delivery."""
    row = _request_row(db_session, status=ExternalFormRequestStatus.smtp_unconfigured.value)
    _, headers = _login_user(client, db_session, username="integrator1", groups=["t1:integrator"])

    assert client.get("/v1.0/m8flow/external-form-notifications", headers=headers).status_code == 200
    resend = client.post(f"/v1.0/m8flow/external-form-notifications/{row.id}/resend", headers=headers)
    assert resend.status_code == 200


def test_a_viewer_can_read_but_not_resend(client, db_session):
    """Authorization rides on the tenant's secrets permission: `viewer` holds
    read-secrets but not manage-secrets, so it sees status and cannot resend."""
    row = _request_row(db_session, status=ExternalFormRequestStatus.smtp_unconfigured.value)
    _, headers = _login_user(client, db_session, username="viewer1", groups=["t1:viewer"])

    assert client.get("/v1.0/m8flow/external-form-notifications", headers=headers).status_code == 200
    resend = client.post(f"/v1.0/m8flow/external-form-notifications/{row.id}/resend", headers=headers)
    assert resend.status_code == 403
    db_session.expire_all()
    assert row.status == ExternalFormRequestStatus.smtp_unconfigured.value


def test_notification_list_reports_derived_status_fields(client, db_session):
    now = int(time.time())
    expired = _request_row(db_session, reference_id="ref-exp", status="notified", notified_at=now - 10)
    expired.expires_at_in_seconds = now - 1
    stuck = _request_row(db_session, reference_id="ref-stuck", status="sending", notified_at=now - 3600)
    done = _request_row(db_session, reference_id="ref-done", status="superseded")
    db_session.commit()
    _, headers = _login_user(client, db_session, username="admin9", groups=["t1:tenant-admin"])

    body = client.get("/v1.0/m8flow/external-form-notifications", headers=headers).get_json()

    by_id = {row["id"]: row for row in body["results"]}
    assert by_id[expired.id]["status"] == "notified"
    assert by_id[expired.id]["effective_status"] == "expired"
    assert by_id[expired.id]["resendable"] is True
    assert by_id[stuck.id]["stuck_sending"] is True
    assert by_id[stuck.id]["resendable"] is True
    assert by_id[done.id]["resendable"] is False
    # No work item exists for these rows, so the task name is unknown rather than an error.
    assert by_id[done.id]["task_name"] is None


@pytest.mark.parametrize(
    ("status", "notified_offset", "resendable", "stuck"),
    [
        ("pending", None, True, False),
        ("sending", -5, False, False),
        ("sending", -3600, True, True),
        ("notified", -5, True, False),
        ("failed", -5, True, False),
        ("smtp_unconfigured", None, True, False),
        ("expired", -5, True, False),
        ("submitted", -5, False, False),
        ("completed", -5, False, False),
        ("superseded", -5, False, False),
        ("cancelled", -5, False, False),
    ],
)
def test_admin_view_resend_and_stuck_rules(status, notified_offset, resendable, stuck):
    from types import SimpleNamespace

    from m8flow_backend.services.external_form_service import ExternalFormService

    now = 1_800_000_000
    row = ExternalFormRequestModel(
        id=1,
        process_instance_id=7,
        task_guid="g",
        email="r@example.test",
        status=status,
        attempts=0,
        notified_at_in_seconds=None if notified_offset is None else now + notified_offset,
        expires_at_in_seconds=now + 60,
    )
    work_item = SimpleNamespace(task_name="Approve", task_title="Approve request")

    view = ExternalFormService.admin_view(row, now, work_item)

    assert view["resendable"] is resendable
    assert view["stuck_sending"] is stuck
    assert view["effective_status"] == status
    assert view["task_title"] == "Approve request"


def test_status_filter_matches_the_effective_status(client, db_session):
    now = int(time.time())
    lapsed = _request_row(db_session, reference_id="ref-lapsed", status="notified", notified_at=now - 10)
    lapsed.expires_at_in_seconds = now - 1
    live = _request_row(db_session, reference_id="ref-live", status="notified", notified_at=now - 10)
    live.expires_at_in_seconds = now + 3600
    stored = _request_row(db_session, reference_id="ref-stored", status="expired")
    db_session.commit()
    _, headers = _login_user(client, db_session, username="admin10", groups=["t1:tenant-admin"])

    def ids(status):
        body = client.get(f"/v1.0/m8flow/external-form-notifications?status={status}", headers=headers).get_json()
        return {row["id"] for row in body["results"]}

    assert ids("expired") == {lapsed.id, stored.id}
    assert ids("notified") == {live.id}


def test_a_link_is_not_expired_during_its_expiry_second(db_session):
    """admin_view and the status filter share the public link check's rule
    (`expires_at < now`), so a link stays valid through its expiry second."""
    from m8flow_backend.services.external_form_service import ExternalFormService

    now = 1_800_000_000
    at_expiry = _request_row(db_session, reference_id="ref-edge", status="notified", notified_at=now - 10)
    at_expiry.expires_at_in_seconds = now
    lapsed = _request_row(db_session, reference_id="ref-lapsed-edge", status="failed", notified_at=now - 10)
    lapsed.expires_at_in_seconds = now - 1
    db_session.commit()

    assert ExternalFormService.admin_view(at_expiry, now)["effective_status"] == "notified"
    assert ExternalFormService.admin_view(lapsed, now)["effective_status"] == "expired"

    def filtered(status):
        query = db_session.query(ExternalFormRequestModel)
        return {row.id for row in ExternalFormService.filter_by_effective_status(query, status, now)}

    assert filtered("notified") == {at_expiry.id}
    assert filtered("expired") == {lapsed.id}
    assert filtered("failed") == set()


def test_status_filter_pages_over_the_effective_status(client, db_session):
    """`total` and `pages` count the same rows the filter returns, across page boundaries."""
    now = int(time.time())
    expected = set()
    for index in range(3):
        lapsed = _request_row(
            db_session, reference_id=f"ref-lapsed-{index}", status="notified", notified_at=now - 10, created_at=10 + index
        )
        lapsed.expires_at_in_seconds = now - 1
        expected.add(lapsed.id)
    expected.add(_request_row(db_session, reference_id="ref-stored-exp", status="expired", created_at=20).id)
    live = _request_row(db_session, reference_id="ref-still-live", status="notified", notified_at=now - 10)
    live.expires_at_in_seconds = now + 3600
    db_session.commit()
    _, headers = _login_user(client, db_session, username="admin11", groups=["t1:tenant-admin"])

    seen = set()
    for page in (1, 2):
        body = client.get(
            f"/v1.0/m8flow/external-form-notifications?status=expired&per_page=2&page={page}", headers=headers
        ).get_json()
        assert (body["pagination"]["total"], body["pagination"]["pages"]) == (4, 2)
        assert len(body["results"]) == 2
        seen |= {row["id"] for row in body["results"]}

    assert seen == expected
