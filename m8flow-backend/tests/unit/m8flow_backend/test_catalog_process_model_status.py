"""Process model publish lifecycle (M8F-508).

Covers the status field itself, the allowed transitions, and the two places
that rebuild process_model.json from scratch and would otherwise silently
drop it (metadata edits and copies).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from m8flow_backend import catalog
from m8flow_backend.errors import ApiError

VALID_BPMN = Path(__file__).resolve().parents[2] / "fixtures" / "invoice_approval_poc.bpmn"


def _seed_model(tmp_path, monkeypatch, *, tenant_id: str = "t1", meta: dict | None = None) -> str:
    root = tmp_path / "bpmn" / tenant_id
    model_dir = root / "finance" / "invoice-approval"
    model_dir.mkdir(parents=True)
    (model_dir / "invoice-approval.bpmn").write_text(
        VALID_BPMN.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (model_dir / "process_model.json").write_text(
        json.dumps(meta if meta is not None else {"display_name": "Invoice Approval"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))
    return "finance/invoice-approval"


def _stored_meta(tmp_path, model_id: str, *, tenant_id: str = "t1") -> dict:
    path = tmp_path / "bpmn" / tenant_id / model_id / "process_model.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_model_predating_the_status_field_reads_as_published(tmp_path, monkeypatch):
    """Models written before this feature were all startable. Reading them as
    draft would make every existing model refuse to start on upgrade."""
    model_id = _seed_model(tmp_path, monkeypatch)
    assert (
        catalog.process_model_status(tenant_id="t1", process_model_identifier=model_id) == "published"
    )


def test_unknown_stored_status_falls_back_to_published(tmp_path, monkeypatch):
    model_id = _seed_model(
        tmp_path, monkeypatch, meta={"display_name": "Invoice Approval", "status": "bogus"}
    )
    assert (
        catalog.process_model_status(tenant_id="t1", process_model_identifier=model_id) == "published"
    )


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        ("draft", "published"),
        ("published", "paused"),
        ("published", "draft"),
        ("paused", "published"),
        ("paused", "draft"),
    ],
)
def test_allowed_transitions(tmp_path, monkeypatch, current, requested):
    model_id = _seed_model(
        tmp_path, monkeypatch, meta={"display_name": "Invoice Approval", "status": current}
    )
    identity = catalog.update_process_model_metadata(
        tenant_id="t1", process_model_identifier=model_id, status=requested
    )
    assert identity["status"] == requested
    assert _stored_meta(tmp_path, model_id)["status"] == requested


def test_draft_cannot_go_straight_to_paused(tmp_path, monkeypatch):
    model_id = _seed_model(
        tmp_path, monkeypatch, meta={"display_name": "Invoice Approval", "status": "draft"}
    )
    with pytest.raises(ApiError) as exc_info:
        catalog.update_process_model_metadata(
            tenant_id="t1", process_model_identifier=model_id, status="paused"
        )
    assert exc_info.value.error_code == "invalid_status_transition"
    assert _stored_meta(tmp_path, model_id)["status"] == "draft"


def test_unknown_requested_status_is_rejected(tmp_path, monkeypatch):
    model_id = _seed_model(tmp_path, monkeypatch)
    with pytest.raises(ApiError) as exc_info:
        catalog.update_process_model_metadata(
            tenant_id="t1", process_model_identifier=model_id, status="archived"
        )
    assert exc_info.value.error_code == "invalid_status"


def test_restating_current_status_is_a_noop_not_an_error(tmp_path, monkeypatch):
    model_id = _seed_model(
        tmp_path, monkeypatch, meta={"display_name": "Invoice Approval", "status": "published"}
    )
    identity = catalog.update_process_model_metadata(
        tenant_id="t1", process_model_identifier=model_id, status="published"
    )
    assert identity["status"] == "published"


def test_renaming_preserves_status(tmp_path, monkeypatch):
    """The metadata payload is rebuilt from scratch on every write — without
    explicit carry-forward a rename would silently unpublish the model."""
    model_id = _seed_model(
        tmp_path, monkeypatch, meta={"display_name": "Invoice Approval", "status": "published"}
    )
    identity = catalog.update_process_model_metadata(
        tenant_id="t1", process_model_identifier=model_id, display_name="Invoice Approval v2"
    )
    assert identity["display_name"] == "Invoice Approval v2"
    assert identity["status"] == "published"
    assert _stored_meta(tmp_path, model_id)["status"] == "published"


def test_copy_of_published_model_starts_as_draft(tmp_path, monkeypatch, db_session):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user

    model_id = _seed_model(
        tmp_path, monkeypatch, meta={"display_name": "Invoice Approval", "status": "published"}
    )
    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(
        db_session, username="copier", service="https://example.test/realms/m8flow", service_id="copier"
    )
    ensure_membership(db_session, user, tenant)
    ensure_v1_role(db_session, tenant_id="t1", role_name="admin", user_ids=(user.id,))
    db_session.commit()
    catalog.copy_process_model(
        db_session,
        tenant_id="t1",
        source_identifier=model_id,
        leaf_id="invoice-approval-copy",
        display_name="Invoice Approval Copy",
        user_id=user.id,
    )
    assert (
        catalog.process_model_status(
            tenant_id="t1", process_model_identifier="finance/invoice-approval-copy"
        )
        == "draft"
    )


def test_newly_created_model_is_explicitly_draft(tmp_path, monkeypatch, db_session):
    """The published default only covers models that predate the field — a
    model created from here on must land in draft."""
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user

    _seed_model(tmp_path, monkeypatch)
    (tmp_path / "bpmn" / "t1" / "finance" / "process_group.json").write_text(
        json.dumps({"display_name": "Finance"}), encoding="utf-8"
    )
    tenant = ensure_tenant(db_session, tenant_id="t1", slug="t1")
    user = ensure_user(
        db_session, username="creator", service="https://example.test/realms/m8flow", service_id="creator"
    )
    ensure_membership(db_session, user, tenant)
    ensure_v1_role(db_session, tenant_id="t1", role_name="admin", user_ids=(user.id,))
    db_session.commit()

    identity = catalog.create_process_model(
        db_session,
        tenant_id="t1",
        group_id="finance",
        leaf_id="brand-new",
        display_name="Brand New",
        user_id=user.id,
    )
    assert identity["status"] == "draft"
    assert _stored_meta(tmp_path, "finance/brand-new")["status"] == "draft"


def test_list_model_rows_carries_status(tmp_path, monkeypatch):
    _seed_model(
        tmp_path, monkeypatch, meta={"display_name": "Invoice Approval", "status": "paused"}
    )
    rows = catalog.list_model_rows(tenant_id="t1")
    assert [row["status"] for row in rows] == ["paused"]
