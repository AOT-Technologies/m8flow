"""Versioned publishing: Save changes the working copy, Publish snapshots it as
the next live version, Revert restores a version into the working copy."""

from __future__ import annotations

import base64
import errno
import json
import os
import sys
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
    catalog.update_file({"id": MODEL}, "invoice-approval.bpmn", xml.encode(), session=db_session, tenant_id="t1")
    return xml


def _state(db_session) -> dict:
    row = {"tenant_id": "t1", "id": MODEL, "status": catalog.process_model_status(tenant_id="t1", process_model_identifier=MODEL)}
    return catalog.attach_publish_state(db_session, [row])[0]


def _publish(db_session):
    """What POST .../publish does; returns the live version row."""
    catalog.publish_with_edits(db_session, tenant_id="t1", process_model_identifier=MODEL, published_by="editor")
    return catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL)


@pytest.fixture
def in_request(app, db_session):
    """update_file resolves the current user from the request."""
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


def test_baseline_snapshot_joins_the_callers_session(tmp_path, db_session, actor):
    """No app context, so no current_session() to fall back on: the baseline
    must land in the session the write was handed, alongside the write."""
    _seed(tmp_path, status=None)

    catalog.write_spec_file(db_session, tenant_id="t1", path=MODEL, file_name="notes.md", content=b"edit")

    baseline = catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL)
    assert baseline in db_session and baseline.version == 1 and "notes.md" not in baseline.files


def test_failed_import_restores_the_file_it_overwrote(tmp_path, db_session, actor, in_request, monkeypatch):
    """The failed request rolls back the baseline v1; the edit must not stay on
    disk, or Start (no versions) would run it."""
    _seed(tmp_path, status=None)
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)
    bad = ORIGINAL.replace("<bpmn:process ", '<bpmn:subProcess triggeredByEvent="true"/><bpmn:process ', 1)

    with pytest.raises(ApiError):
        catalog.update_file({"id": MODEL}, "invoice-approval.bpmn", bad.encode(), session=db_session, tenant_id="t1")
    with pytest.raises(ApiError):
        catalog.update_file({"id": MODEL}, "new.bpmn", bad.encode(), session=db_session, tenant_id="t1")

    assert (_model_dir(tmp_path) / "invoice-approval.bpmn").read_bytes() == BPMN.read_bytes()
    assert not (_model_dir(tmp_path) / "new.bpmn").exists()


def test_update_file_rejects_non_utf8_bpmn_before_writing(tmp_path, db_session, actor, in_request, monkeypatch):
    _seed(tmp_path, status="published")
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)
    before = _dir_state(tmp_path)

    with pytest.raises(ApiError) as refused:
        catalog.update_file({"id": MODEL}, "invoice-approval.bpmn", b"\xff\xfe<x/>", session=db_session, tenant_id="t1")

    assert (refused.value.status_code, refused.value.error_code) == (400, "invalid_file_content")
    assert _dir_state(tmp_path) == before


def test_failed_restore_after_failed_import_is_a_clear_500(tmp_path, db_session, actor, in_request, monkeypatch):
    _seed(tmp_path, status="draft")
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)

    def failing_import(*_args, **_kwargs):
        raise ApiError("bpmn_import_failed", "import failed", 400)

    real_write_bytes = Path.write_bytes
    writes = []

    def flaky_write_bytes(self, data):
        writes.append(self)
        if len(writes) == 2:  # 1: the edit, 2: putting the old bytes back
            raise OSError("disk full")
        return real_write_bytes(self, data)

    monkeypatch.setattr(catalog.workflow, "import_definition", failing_import)
    monkeypatch.setattr(Path, "write_bytes", flaky_write_bytes)
    with pytest.raises(ApiError) as failed:
        catalog.update_file({"id": MODEL}, "invoice-approval.bpmn", ORIGINAL.encode(), session=db_session, tenant_id="t1")

    assert (failed.value.status_code, failed.value.error_code) == (500, "restore_failed")


def test_working_digest_is_cached_until_a_file_changes(tmp_path, actor, monkeypatch):
    _seed(tmp_path, status="draft")
    for path in _model_dir(tmp_path).iterdir():  # old enough to be cached
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns - 10_000_000_000))
    real_read = catalog.model_file_bytes
    reads = []
    monkeypatch.setattr(catalog, "model_file_bytes", lambda **kw: reads.append(kw) or real_read(**kw))

    def digest():
        return catalog.working_digest(tenant_id="t1", process_model_identifier=MODEL)

    first = digest()
    assert digest() == first and len(reads) == 1  # unchanged dir: no re-read
    (_model_dir(tmp_path) / "invoice-schema.json").write_text('{"title": "v2 longer"}', encoding="utf-8")
    assert digest() != first and len(reads) == 2


def test_working_digest_sees_a_same_tick_same_size_rewrite(tmp_path, actor):
    """A failed write's restore can land in the same mtime tick with the same
    size, leaving the stat signature unchanged; the digest must still move."""
    _seed(tmp_path, status="draft")
    schema = _model_dir(tmp_path) / "invoice-schema.json"
    first = catalog.working_digest(tenant_id="t1", process_model_identifier=MODEL)
    stat = schema.stat()

    schema.write_text('{"title": "v9"}', encoding="utf-8")  # same size as '{"title": "v1"}'
    os.utime(schema, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    assert schema.stat().st_size == stat.st_size
    assert catalog.working_digest(tenant_id="t1", process_model_identifier=MODEL) != first


def test_start_runs_the_published_dmn_not_a_later_saved_one(tmp_path, db_session, actor, in_request, monkeypatch):
    from m8flow_bpmn_core.models.bpmn_process_definition import BpmnProcessDefinitionModel

    from m8flow_backend import workflow

    _seed(tmp_path, status="draft")
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)
    published = catalog._default_file_bytes("rules.dmn")
    (_model_dir(tmp_path) / "rules.dmn").write_bytes(published)
    _publish(db_session)
    # Same BPMN, so the import of this DMN-only save lands on the live definition's row.
    edited = published.replace(b"<text></text>", b'<text>"edited"</text>')
    catalog.update_file({"id": MODEL}, "rules.dmn", edited, session=db_session, tenant_id="t1")

    definition_id = workflow._definition_id_for_start(
        db_session, tenant_id="t1", user_id=actor.id, process_model_identifier=MODEL
    )

    assert db_session.get(BpmnProcessDefinitionModel, definition_id).source_dmn_xml == published.decode("utf-8")


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


def test_corrupt_base64_in_a_version_is_a_clear_error(tmp_path, db_session, actor, in_request):
    _seed(tmp_path, status="draft")
    row = _publish(db_session)
    row.files = {**row.files, "invoice-schema.json": "!!not-base64!!"}
    db_session.flush()
    before = _dir_state(tmp_path)

    with pytest.raises(ApiError) as form:
        catalog.read_published_file(
            db_session, tenant_id="t1", process_model_identifier=MODEL, file_name="invoice-schema.json"
        )
    with pytest.raises(ApiError) as start:
        catalog.read_published_primary_bpmn(db_session, tenant_id="t1", process_model_identifier=MODEL)
    with pytest.raises(ApiError) as revert:
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=MODEL, version=1, user_id=actor.id)

    for refused in (form, start, revert):
        assert (refused.value.status_code, refused.value.error_code) == (500, "corrupt_process_model_version")
    assert _dir_state(tmp_path) == before


def _dir_state(tmp_path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in _model_dir(tmp_path).iterdir()}


def _prepare_revert(tmp_path, db_session, actor, monkeypatch) -> dict[str, bytes]:
    """v1 published, then a v2 working copy with an extra file; returns that working copy."""
    _seed(tmp_path, status="draft")
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)
    _publish(db_session)
    _edit_bpmn(db_session, actor, "v2")
    (_model_dir(tmp_path) / "extra.md").write_text("added after v1", encoding="utf-8")
    return _dir_state(tmp_path)


def test_revert_leaves_working_copy_untouched_when_a_write_fails(tmp_path, db_session, actor, in_request, monkeypatch):
    before = _prepare_revert(tmp_path, db_session, actor, monkeypatch)
    real_write_bytes = Path.write_bytes
    calls = []

    def flaky_write_bytes(self, data):
        calls.append(self)
        if len(calls) == 2:
            raise OSError("disk full")
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", flaky_write_bytes)
    with pytest.raises(OSError):
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=MODEL, version=1, user_id=actor.id)

    assert _dir_state(tmp_path) == before
    assert list((tmp_path / "bpmn" / ".m8flow-trash").iterdir()) == []


def test_revert_leaves_working_copy_untouched_when_the_metadata_write_fails(
    tmp_path, db_session, actor, in_request, monkeypatch
):
    before = _prepare_revert(tmp_path, db_session, actor, monkeypatch)
    real_write_text = Path.write_text

    def flaky_write_text(self, *args, **kwargs):
        if self.name == "process_model.json":
            raise OSError("disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", flaky_write_text)
    with pytest.raises(OSError):
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=MODEL, version=1, user_id=actor.id)

    assert _dir_state(tmp_path) == before  # failed in staging: never swapped in
    assert list((tmp_path / "bpmn" / ".m8flow-trash").iterdir()) == []


def test_revert_leaves_working_copy_untouched_when_reimport_fails(tmp_path, db_session, actor, in_request, monkeypatch):
    before = _prepare_revert(tmp_path, db_session, actor, monkeypatch)
    swaps = []

    def failing_import(*_args, **_kwargs):
        raise ApiError("unsupported_bpmn", "import failed", 400)

    monkeypatch.setattr(catalog.workflow, "import_definition", failing_import)
    monkeypatch.setattr(catalog, "_exchange_dirs", lambda *args: swaps.append(args))
    with pytest.raises(ApiError) as refused:
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=MODEL, version=1, user_id=actor.id)

    assert refused.value.status_code == 400
    assert swaps == []  # the import runs before the swap
    assert _dir_state(tmp_path) == before
    assert list((tmp_path / "bpmn" / ".m8flow-trash").iterdir()) == []


def _fail_renames_into_model_dir(tmp_path, monkeypatch, *, failing: set[int]) -> list[Path]:
    """Force the non-Linux rename fallback; the n-th rename into the model dir (1-based) in `failing` raises."""
    monkeypatch.setattr(catalog, "_exchange_dirs", lambda *_args: False)
    real_rename = Path.rename
    into_model_dir: list[Path] = []

    def flaky_rename(self, target):
        if Path(target) == _model_dir(tmp_path):
            into_model_dir.append(self)
            if len(into_model_dir) in failing:  # 1: staging swapped in, 2: the backup put back
                raise OSError("locked")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky_rename)
    return into_model_dir


def test_revert_restores_working_copy_when_the_swap_in_fails(tmp_path, db_session, actor, in_request, monkeypatch):
    before = _prepare_revert(tmp_path, db_session, actor, monkeypatch)
    _fail_renames_into_model_dir(tmp_path, monkeypatch, failing={1})

    with pytest.raises(OSError):
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=MODEL, version=1, user_id=actor.id)

    assert _dir_state(tmp_path) == before
    assert list((tmp_path / "bpmn" / ".m8flow-trash").iterdir()) == []


def test_revert_that_cannot_restore_says_so_and_keeps_the_backup(tmp_path, db_session, actor, in_request, monkeypatch):
    before = _prepare_revert(tmp_path, db_session, actor, monkeypatch)
    into_model_dir = _fail_renames_into_model_dir(tmp_path, monkeypatch, failing={1, 2})

    with pytest.raises(ApiError) as failed:
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=MODEL, version=1, user_id=actor.id)

    assert (failed.value.status_code, failed.value.error_code) == (500, "revert_restore_failed")
    backup = into_model_dir[1]
    assert {p.name: p.read_bytes() for p in backup.iterdir() if p.is_file()} == before


def test_exchange_dirs_swaps_contents(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "marker").write_text("a", encoding="utf-8")
    (b / "marker").write_text("b", encoding="utf-8")

    if not catalog._exchange_dirs(a, b):
        pytest.skip("atomic directory exchange is not supported here")
    assert ((a / "marker").read_text(encoding="utf-8"), (b / "marker").read_text(encoding="utf-8")) == ("b", "a")


@pytest.mark.skipif(sys.platform != "linux", reason="renameat2 is Linux-only")
def test_exchange_dirs_raises_on_unexpected_error(tmp_path):
    """A real failure is not 'unsupported': it must surface, not fall back to the non-atomic renames."""
    (tmp_path / "a").mkdir()
    with pytest.raises(OSError) as failed:
        catalog._exchange_dirs(tmp_path / "a", tmp_path / "missing")
    assert failed.value.errno == errno.ENOENT


def test_failed_publish_with_edits_leaves_working_copy_untouched(tmp_path, db_session, actor, in_request, monkeypatch):
    _seed(tmp_path, status="published")
    before = _dir_state(tmp_path)

    def failing_publish(*_args, **_kwargs):
        raise ApiError("no_primary_bpmn", "publish failed", 400)

    monkeypatch.setattr(catalog, "publish_version", failing_publish)
    with pytest.raises(ApiError):
        catalog.publish_with_edits(
            db_session, tenant_id="t1", process_model_identifier=MODEL, published_by="editor", display_name="Renamed"
        )

    assert _dir_state(tmp_path) == before


def test_publish_writes_status_and_version_together(tmp_path, db_session, actor, in_request):
    _seed(tmp_path, status="draft")

    identity_row = catalog.publish_with_edits(
        db_session, tenant_id="t1", process_model_identifier=MODEL, published_by="editor"
    )

    assert identity_row["status"] == "published"
    assert catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL).version == 1


def test_failed_publish_leaves_no_version_and_no_status(tmp_path, db_session, actor, in_request, monkeypatch):
    """Fails after both writes: process_model.json goes back, and the request
    rollback (mirrored here) drops the version row."""
    _seed(tmp_path, status="draft")
    before = _dir_state(tmp_path)
    real_identity = catalog.get_model_identity
    calls = []

    def identity_lost_after_snapshot(**kwargs):
        calls.append(kwargs)
        return None if len(calls) == 2 else real_identity(**kwargs)  # 1: metadata write, 2: after the snapshot

    monkeypatch.setattr(catalog, "get_model_identity", identity_lost_after_snapshot)
    with pytest.raises(ApiError) as failed:
        catalog.publish_with_edits(db_session, tenant_id="t1", process_model_identifier=MODEL, published_by="editor")
    assert catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL) is not None  # snapshot ran
    db_session.rollback()

    assert failed.value.status_code == 404
    assert _dir_state(tmp_path) == before
    assert catalog.process_model_status(tenant_id="t1", process_model_identifier=MODEL) == "draft"
    assert catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL) is None


def test_publish_state_uses_the_newest_version_of_each_listed_model(tmp_path, db_session, actor, in_request, monkeypatch):
    _seed(tmp_path, status="draft")
    monkeypatch.setattr("m8flow_backend.auth.require_current_user", lambda: actor)
    _publish(db_session)
    _edit_bpmn(db_session, actor, "v2")
    _publish(db_session)

    rows = catalog.attach_publish_state(
        db_session,
        [
            {"tenant_id": "t1", "id": MODEL, "status": "published"},
            {"tenant_id": "t1", "id": "finance/never-published", "status": "draft"},
        ],
    )

    assert [(r["published_version"], r["has_unpublished_changes"]) for r in rows] == [(2, False), (None, False)]


def test_path_inside_tenant_is_strict_child(tmp_path, actor):
    root = tmp_path / "bpmn" / "t1"
    _seed(tmp_path, status="draft")

    assert catalog._path_inside_tenant("t1", root) is None
    assert catalog._path_inside_tenant("t1", root / ".") is None
    assert catalog._path_inside_tenant("t1", root / MODEL) == Path(os.path.abspath(root / MODEL))
    bpmn = root / MODEL / "invoice-approval.bpmn"
    assert catalog._path_inside_tenant("t1", bpmn) == Path(os.path.abspath(bpmn))


@pytest.mark.parametrize(
    "relative",
    [
        f"../t2/{MODEL}",
        "finance/../../t2",
        "..",
        os.path.abspath(os.sep),  # absolute right operand: pathlib drops the root
        f"../t10/{MODEL}",  # sibling tenant sharing the "t1" prefix
        f"../T1/{MODEL}",  # case variant of its own root: fails closed, never admits
        f"../t1/{MODEL}",  # walks out and back into its own root
        f"finance/../{MODEL}",  # stays inside, but no caller needs ".."
    ],
)
def test_path_inside_tenant_rejects_escapes(tmp_path, actor, relative):
    """Includes `..` walks that end back inside t1: refused before any prefix check."""
    _seed(tmp_path, status="draft", tenant_id="t2")
    (tmp_path / "bpmn" / "t10" / MODEL).mkdir(parents=True)

    assert catalog._path_inside_tenant("t1", tmp_path / "bpmn" / "t1" / relative) is None


@pytest.mark.skipif(sys.platform != "win32", reason="backslash is a separator only on Windows")
def test_path_inside_tenant_rejects_backslash_and_mixed_case_escapes_on_windows(tmp_path, actor):
    _seed(tmp_path, status="draft", tenant_id="t2")
    root = tmp_path / "bpmn" / "t1"

    assert catalog._path_inside_tenant("t1", root / f"..\\t2\\{MODEL}") is None
    assert catalog._path_inside_tenant("t1", root / f"..\\T2\\{MODEL}") is None
    assert catalog._path_inside_tenant("t1", Path(str(root).upper()) / MODEL) is None  # fails closed


def test_path_inside_tenant_rejects_a_link_to_the_tenant_root(tmp_path, actor):
    root = tmp_path / "bpmn" / "t1"
    _seed(tmp_path, status="draft")
    try:
        os.symlink(root, root / "finance" / "self", target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks is not permitted here")

    assert catalog._path_inside_tenant("t1", root / "finance" / "self") is None


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


def test_symlinks_escaping_the_tenant_root_are_rejected(tmp_path, db_session, actor, in_request):
    """A link under t1's root pointing into t2 passes a lexical check; t1 must still not read or overwrite t2."""
    from m8flow_backend.models.process_model_version import ProcessModelVersionModel

    _seed(tmp_path, status="draft")
    _seed(tmp_path, status="draft", tenant_id="t2")
    t2_dir = _model_dir(tmp_path, "t2")
    linked_dir = tmp_path / "bpmn" / "t1" / "finance" / "linked"
    try:
        os.symlink(t2_dir, linked_dir, target_is_directory=True)
        os.symlink(t2_dir / "invoice-approval.bpmn", _model_dir(tmp_path) / "stolen.bpmn")
    except OSError:
        pytest.skip("creating symlinks is not permitted here")
    before = {p.name: p.read_bytes() for p in t2_dir.iterdir()}

    assert catalog._path_inside_tenant("t1", linked_dir / "invoice-approval.bpmn") is None
    assert catalog._working_primary_name(tenant_id="t1", process_model_identifier="finance/linked") == ""
    assert catalog.read_model_file(tenant_id="t1", process_model_identifier=MODEL, file_name="stolen.bpmn") is None
    assert "stolen.bpmn" not in catalog.model_file_bytes(tenant_id="t1", process_model_identifier=MODEL)
    with pytest.raises(ApiError) as write:
        catalog.write_spec_file(db_session, tenant_id="t1", path=MODEL, file_name="stolen.bpmn", content=b"<overwritten/>")
    assert write.value.status_code == 400
    # A version naming the linked file: revert must refuse before writing anything.
    db_session.add(
        ProcessModelVersionModel(
            m8f_tenant_id="t1",
            process_model_identifier=MODEL,
            version=1,
            primary_file_name="invoice-approval.bpmn",
            files={
                name: base64.b64encode(body).decode("ascii")
                for name, body in {"invoice-approval.bpmn": BPMN.read_bytes(), "stolen.bpmn": b"<overwritten/>"}.items()
            },
            content_digest="x",
        )
    )
    db_session.flush()
    with pytest.raises(ApiError) as revert:
        catalog.revert_to_version(db_session, tenant_id="t1", process_model_identifier=MODEL, version=1, user_id=actor.id)
    assert revert.value.status_code == 400
    with pytest.raises(ApiError) as delete:
        catalog.delete_model_file(db_session, tenant_id="t1", process_model_identifier=MODEL, file_name="stolen.bpmn")
    assert (delete.value.status_code, delete.value.error_code) == (400, "invalid_file_name")
    assert (_model_dir(tmp_path) / "stolen.bpmn").is_symlink()
    assert {p.name: p.read_bytes() for p in t2_dir.iterdir()} == before


def test_delete_removes_model_and_versions(tmp_path, db_session, actor, in_request):
    _seed(tmp_path, status="draft")
    _publish(db_session)

    catalog.delete_process_model(db_session, tenant_id="t1", process_model_identifier=MODEL)

    assert not _model_dir(tmp_path).exists()
    assert catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL) is None
    assert list((tmp_path / "bpmn" / ".m8flow-trash").iterdir()) == []


@pytest.mark.parametrize("identifier", ["", ".", f"../t2/{MODEL}"])
def test_delete_refuses_identifiers_outside_the_tenant_root(tmp_path, db_session, actor, in_request, identifier):
    _seed(tmp_path, status="draft", tenant_id="t2")
    t2_dir = _model_dir(tmp_path, "t2")
    before = {p.name: p.read_bytes() for p in t2_dir.iterdir()}

    with pytest.raises(ApiError) as deleted:
        catalog.delete_process_model(db_session, tenant_id="t1", process_model_identifier=identifier)

    assert deleted.value.status_code == 400
    assert {p.name: p.read_bytes() for p in t2_dir.iterdir()} == before


def test_delete_restores_the_model_when_commit_fails(tmp_path, db_session, actor, in_request):
    """Files must not be lost while their version rows survive a failed commit."""
    _seed(tmp_path, status="draft")
    _publish(db_session)
    db_session.commit()
    before = {p.name: p.read_bytes() for p in _model_dir(tmp_path).iterdir()}

    def failing_commit():
        raise RuntimeError("commit failed")

    db_session.commit = failing_commit
    try:
        with pytest.raises(RuntimeError):
            catalog.delete_process_model(db_session, tenant_id="t1", process_model_identifier=MODEL)
    finally:
        del db_session.commit
    db_session.rollback()

    assert {p.name: p.read_bytes() for p in _model_dir(tmp_path).iterdir()} == before
    assert catalog.latest_version(db_session, tenant_id="t1", process_model_identifier=MODEL) is not None


def test_publish_refuses_bpmn_start_cannot_run(tmp_path, db_session, actor, in_request):
    _seed(tmp_path, status="draft")
    bpmn = _model_dir(tmp_path) / "invoice-approval.bpmn"
    bpmn.write_bytes(bpmn.read_bytes().replace(b"</bpmn:process>", b"<bpmn:callActivity id='c'/></bpmn:process>"))

    with pytest.raises(ApiError) as refused:
        _publish(db_session)
    assert refused.value.status_code == 400
