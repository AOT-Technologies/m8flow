"""Versioned publishing: Save changes the working copy, Publish snapshots it as
the next live version, Revert restores a version into the working copy."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from m8flow_backend import catalog, identity
from m8flow_backend.errors import ApiError

BPMN = Path(__file__).resolve().parents[2] / "fixtures" / "invoice_approval_poc.bpmn"
MODEL = "finance/invoice-approval"
ORIGINAL = BPMN.read_bytes().decode("utf-8")  # raw: the fixture is CRLF


@pytest.fixture
def actor(db_session, tmp_path, monkeypatch):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path / "bpmn"))
    for tenant_id in ("t1", "t2"):
        identity.ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = identity.ensure_user(
        db_session, username="editor", service="https://example.test/realms/m8flow", service_id="editor-1"
    )
    identity.ensure_membership(db_session, user, identity.ensure_tenant(db_session, tenant_id="t1", slug="t1"))
    identity.sync_groups(db_session, user=user, group_identifiers=["t1:editor"], tenant_id="t1")
    ensure_v1_role(db_session, tenant_id="t1", role_name="admin", user_ids=(user.id,))
    db_session.flush()
    return user


def _model_dir(tmp_path, tenant_id: str = "t1") -> Path:
    return tmp_path / "bpmn" / tenant_id / MODEL


def _seed(tmp_path, *, status: str | None, tenant_id: str = "t1") -> None:
    model_dir = _model_dir(tmp_path, tenant_id)
    model_dir.mkdir(parents=True)
    (model_dir / "invoice-approval.bpmn").write_bytes(BPMN.read_bytes())
    (model_dir / "invoice-schema.json").write_text('{"title": "v1"}', encoding="utf-8")
    meta = {"display_name": "Invoice", "primary_file_name": "invoice-approval.bpmn"}
    if status:
        meta["status"] = status
    (model_dir / "process_model.json").write_text(json.dumps(meta), encoding="utf-8")


def _edit_bpmn(db_session, user, marker: str) -> str:
    xml = ORIGINAL.replace("</bpmn:definitions>", f"<!-- {marker} --></bpmn:definitions>")
    catalog.update_file({"id": MODEL}, "invoice-approval.bpmn", xml.encode(), tenant_id="t1")
    return xml


def _state(db_session) -> dict:
    row = {"tenant_id": "t1", "id": MODEL, "status": catalog.process_model_status(tenant_id="t1", process_model_identifier=MODEL)}
    return catalog.attach_publish_state(db_session, [row])[0]


def _publish(db_session):
    """What POST .../publish does."""
    row = catalog.publish_version(db_session, tenant_id="t1", process_model_identifier=MODEL, published_by="editor")
    catalog.update_process_model_metadata(tenant_id="t1", process_model_identifier=MODEL, status="published")
    return row


@pytest.fixture
def in_request(app, db_session):
    """update_file resolves the current user and session from the request."""
    from flask import g

    with app.test_request_context():
        g.db_session = db_session
        yield


def test_publish_snapshots_once_and_save_only_changes_the_working_copy(tmp_path, db_session, actor, in_request, monkeypatch):
    _seed(tmp_path, status="draft")
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)

    assert _publish(db_session).version == 1
    assert _publish(db_session).version == 1  # unchanged working copy: no new version
    assert _state(db_session) == {**_state(db_session), "published_version": 1, "has_unpublished_changes": False}

    edited = _edit_bpmn(db_session, actor, "v2")
    assert _state(db_session)["has_unpublished_changes"] is True
    name, live_xml, _dmn = catalog.read_published_primary_bpmn(db_session, tenant_id="t1", process_model_identifier=MODEL)
    assert name == "invoice-approval.bpmn" and live_xml == ORIGINAL

    assert _publish(db_session).version == 2
    assert _state(db_session)["has_unpublished_changes"] is False
    assert catalog.read_published_primary_bpmn(db_session, tenant_id="t1", process_model_identifier=MODEL)[1] == edited


def test_forms_come_from_the_live_version(tmp_path, db_session, actor, in_request, monkeypatch):
    _seed(tmp_path, status="draft")
    _publish(db_session)
    (_model_dir(tmp_path) / "invoice-schema.json").write_text('{"title": "draft"}', encoding="utf-8")
    (_model_dir(tmp_path) / "new-schema.json").write_text("{}", encoding="utf-8")

    def read(name):
        return catalog.read_published_file(db_session, tenant_id="t1", process_model_identifier=MODEL, file_name=name)

    assert read("invoice-schema.json") == b'{"title": "v1"}'
    assert read("new-schema.json") is None


def test_revert_restores_files_into_the_working_copy_only(tmp_path, db_session, actor, in_request, monkeypatch):
    _seed(tmp_path, status="draft")
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)
    _publish(db_session)
    _edit_bpmn(db_session, actor, "v2")
    (_model_dir(tmp_path) / "extra.md").write_text("added after v1", encoding="utf-8")
    _publish(db_session)

    identity_row = catalog.revert_to_version(
        db_session, tenant_id="t1", process_model_identifier=MODEL, version=1, user_id=actor.id
    )

    assert identity_row["status"] == "published"
    assert not (_model_dir(tmp_path) / "extra.md").exists()
    assert (_model_dir(tmp_path) / "invoice-approval.bpmn").read_bytes().decode("utf-8") == ORIGINAL
    assert _state(db_session) == {**_state(db_session), "published_version": 2, "has_unpublished_changes": True}
    versions = catalog.list_versions(db_session, tenant_id="t1", process_model_identifier=MODEL)
    assert [(v["version"], v["is_live"], v["published_by"]) for v in versions] == [(2, True, "editor"), (1, False, "editor")]
    assert all(v["created_at"] for v in versions)

    with pytest.raises(ApiError) as missing:
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=MODEL, version=9, user_id=actor.id)
    assert missing.value.status_code == 404


def test_first_edit_of_a_model_published_before_versioning_keeps_the_old_one_live(
    tmp_path, db_session, actor, in_request, monkeypatch
):
    _seed(tmp_path, status=None)  # no status: reads as published (pre-versioning model)
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)

    _edit_bpmn(db_session, actor, "first edit")

    baseline = catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL)
    assert baseline.version == 1 and baseline.published_by is None
    assert catalog.read_published_primary_bpmn(db_session, tenant_id="t1", process_model_identifier=MODEL)[1] == ORIGINAL
    assert _state(db_session)["has_unpublished_changes"] is True


def test_draft_edits_and_copies_create_no_versions(tmp_path, db_session, actor, in_request, monkeypatch):
    _seed(tmp_path, status="draft")
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)
    _edit_bpmn(db_session, actor, "draft edit")
    assert catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL) is None

    _publish(db_session)
    catalog.copy_process_model(
        db_session, tenant_id="t1", source_identifier=MODEL, leaf_id="copy", display_name=None, user_id=actor.id
    )
    assert catalog.latest_version(db_session, tenant_id="t1", process_model_identifier="finance/copy") is None


def test_versions_are_tenant_scoped_and_deleted_with_the_model(tmp_path, db_session, actor, in_request):
    _seed(tmp_path, status="draft")
    _seed(tmp_path, status="draft", tenant_id="t2")
    _publish(db_session)

    assert catalog.list_versions(db_session, tenant_id="t2", process_model_identifier=MODEL) == []
    assert catalog.latest_version(db_session, tenant_id="t2", process_model_identifier=MODEL) is None

    catalog.delete_versions(db_session, tenant_id="t1", process_model_identifier=MODEL)
    db_session.flush()
    assert catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL) is None


def test_corrupt_version_without_primary_file_is_a_clear_error(tmp_path, db_session, actor, in_request):
    _seed(tmp_path, status="draft")
    _publish(db_session).primary_file_name = "missing.bpmn"
    db_session.flush()
    (_model_dir(tmp_path) / "extra.md").write_text("working copy", encoding="utf-8")

    with pytest.raises(ApiError) as start:
        catalog.read_published_primary_bpmn(db_session, tenant_id="t1", process_model_identifier=MODEL)
    with pytest.raises(ApiError) as revert:
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=MODEL, version=1, user_id=actor.id)

    for refused in (start, revert):
        assert (refused.value.status_code, refused.value.error_code) == (500, "corrupt_process_model_version")
    assert (_model_dir(tmp_path) / "extra.md").exists()  # revert aborted before touching the working copy


def test_concurrent_publish_returns_the_winner_or_conflicts(tmp_path, db_session, actor, in_request, monkeypatch):
    from m8flow_backend.models.process_model_version import ProcessModelVersionModel

    _seed(tmp_path, status="draft")
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)
    v1 = _publish(db_session)
    _edit_bpmn(db_session, actor, "v2")
    winner = ProcessModelVersionModel(
        m8f_tenant_id="t1",
        process_model_identifier=MODEL,
        version=2,
        primary_file_name=v1.primary_file_name,
        files=v1.files,
        content_digest=catalog.working_digest(tenant_id="t1", process_model_identifier=MODEL),
        published_by="reviewer",
    )
    db_session.add(winner)
    db_session.flush()

    real_latest = catalog.latest_version

    def race():
        """The loser read the latest version before the winner committed v2."""
        calls = iter([v1])
        monkeypatch.setattr(
            catalog, "latest_version", lambda *a, **k: next(calls, None) or real_latest(*a, **k)
        )

    race()
    assert _publish(db_session) is winner  # same content: the winner's row is ours

    winner.content_digest = "someone-saved-in-between"
    db_session.flush()
    race()
    with pytest.raises(ApiError) as conflict:
        _publish(db_session)
    assert conflict.value.status_code == 409
    assert catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL) is winner


def test_ids_escaping_the_tenant_root_are_rejected(tmp_path, db_session, actor, in_request):
    """`..:t2:...` decodes to `../t2/...`: t1 must not read or overwrite t2's model."""
    from m8flow_backend.models.process_model_version import ProcessModelVersionModel

    _seed(tmp_path, status="draft", tenant_id="t2")
    escaping = f"../t2/{MODEL}"
    # A t1 row under the escaping id: unguarded, revert would write it into t2's model.
    db_session.add(
        ProcessModelVersionModel(
            m8f_tenant_id="t1",
            process_model_identifier=escaping,
            version=1,
            primary_file_name="invoice-approval.bpmn",
            files={"invoice-approval.bpmn": base64.b64encode(b"<overwritten/>").decode("ascii")},
            content_digest="x",
        )
    )
    db_session.flush()
    before = {p.name: p.read_bytes() for p in _model_dir(tmp_path, "t2").iterdir()}

    assert catalog._working_primary_name(tenant_id="t1", process_model_identifier=escaping) == ""
    # Sibling tenant sharing a name prefix (t1 vs t10) is outside t1's root too.
    assert catalog._path_inside_tenant("t1", tmp_path / "bpmn" / "t10" / MODEL) is None
    with pytest.raises(ApiError) as refused:
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=escaping, version=1, user_id=actor.id)
    assert refused.value.status_code == 404
    assert {p.name: p.read_bytes() for p in _model_dir(tmp_path, "t2").iterdir()} == before


def test_publish_refuses_bpmn_start_cannot_run(tmp_path, db_session, actor, in_request):
    _seed(tmp_path, status="draft")
    bpmn = _model_dir(tmp_path) / "invoice-approval.bpmn"
    bpmn.write_bytes(bpmn.read_bytes().replace(b"</bpmn:process>", b"<bpmn:callActivity id='c'/></bpmn:process>"))

    with pytest.raises(ApiError) as refused:
        _publish(db_session)
    assert refused.value.status_code == 400
