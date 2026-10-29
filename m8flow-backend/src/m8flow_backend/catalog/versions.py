"""Process model history and versioned publishing.

The model files on disk are the *working copy*. Every save, publish and revert
is recorded as a `ProcessModelVersionModel` row holding the full file set, and
Start runs the newest live row (`publish` or `baseline`) -- so saving a
published model does not change what Start runs until Publish Changes.

Models published before history existed have no rows; `ensure_baseline`
snapshots their files as the live version before the first write; until then
Start runs the file on disk, so upgrading never changes what a model runs.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import delete, func, select, text, tuple_
from sqlalchemy.orm import Session

from m8flow_backend import catalog, workflow
from m8flow_backend.errors import ApiError
from m8flow_backend.models.process_model_version import LIVE_ACTIONS, ProcessModelVersionModel

ACTION_SAVE = "save"
ACTION_PUBLISH = "publish"
ACTION_REVERT = "revert"
ACTION_BASELINE = "baseline"

SYSTEM_USER = "system"
MAX_PER_PAGE = 100


def _working_files(*, tenant_id: str, process_model_identifier: str) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for row in catalog.list_model_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        body = catalog.read_model_file(
            tenant_id=tenant_id, process_model_identifier=process_model_identifier, file_name=row["name"]
        )
        if body is not None:
            files[row["name"]] = body
    return files


def _primary_file_name(*, tenant_id: str, process_model_identifier: str, files: dict[str, bytes]) -> str | None:
    meta = catalog._tenant_json(  # noqa: SLF001 - same package
        tenant_id, process_model_identifier, "process_model.json", **catalog._MODEL_PATH_ERROR  # noqa: SLF001
    )
    primary = meta.get("primary_file_name")
    if isinstance(primary, str) and primary.strip() in files:
        return primary.strip()
    bpmn = sorted(name for name in files if name.lower().endswith(".bpmn"))
    return bpmn[0] if bpmn else None


def _digest(files: dict[str, bytes], primary_file_name: str | None) -> str:
    # The primary file is part of the digest: changing it changes what Start runs.
    hasher = hashlib.sha256((primary_file_name or "").encode("utf-8") + b"\0")
    for name in sorted(files):
        hasher.update(name.encode("utf-8") + b"\0")
        hasher.update(hashlib.sha256(files[name]).digest())
    return hasher.hexdigest()


def _encode(files: dict[str, bytes]) -> dict[str, dict[str, str]]:
    encoded: dict[str, dict[str, str]] = {}
    for name, body in files.items():
        try:
            encoded[name] = {"text": body.decode("utf-8")}
        except UnicodeDecodeError:
            encoded[name] = {"base64": base64.b64encode(body).decode("ascii")}
    return encoded


def _decode(stored: dict[str, Any], *, strict: bool = False) -> dict[str, bytes]:
    """`strict` (revert, which deletes files absent from the result): a malformed
    entry raises instead of being skipped."""
    files: dict[str, bytes] = {}
    for name, value in (stored or {}).items():
        if isinstance(value, dict) and isinstance(value.get("text"), str):
            files[name] = value["text"].encode("utf-8")
        elif isinstance(value, dict) and isinstance(value.get("base64"), str):
            try:
                files[name] = base64.b64decode(value["base64"], validate=strict)
            except ValueError:
                raise ApiError("invalid_version", f"Stored file {name!r} is corrupt", 500) from None
        elif strict:
            raise ApiError("invalid_version", f"Stored file {name!r} is corrupt", 500)
    return files


def _rows(tenant_id: str, process_model_identifier: str):
    return select(ProcessModelVersionModel).where(
        ProcessModelVersionModel.m8f_tenant_id == tenant_id,
        ProcessModelVersionModel.process_model_identifier == process_model_identifier,
    )


def latest(session: Session, *, tenant_id: str, process_model_identifier: str) -> ProcessModelVersionModel | None:
    return session.scalars(
        _rows(tenant_id, process_model_identifier).order_by(ProcessModelVersionModel.version.desc()).limit(1)
    ).first()


def live(session: Session, *, tenant_id: str, process_model_identifier: str) -> ProcessModelVersionModel | None:
    return session.scalars(
        _rows(tenant_id, process_model_identifier)
        .where(ProcessModelVersionModel.action.in_(LIVE_ACTIONS))
        .order_by(ProcessModelVersionModel.version.desc())
        .limit(1)
    ).first()


def _working_digest(*, tenant_id: str, process_model_identifier: str) -> str:
    files = _working_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    primary = _primary_file_name(tenant_id=tenant_id, process_model_identifier=process_model_identifier, files=files)
    return _digest(files, primary)


def record(
    session: Session,
    *,
    tenant_id: str,
    process_model_identifier: str,
    action: str,
    created_by: str,
    reverted_from_version: int | None = None,
) -> ProcessModelVersionModel | None:
    """Snapshot the working copy as a new row. A `save` identical to the newest
    row is skipped, so repeated saves do not flood history."""
    if not catalog.model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        return None
    if session.get_bind().dialect.name == "postgresql":
        # Serialize version numbering per model: the loser would otherwise hit the
        # (tenant, model, version) unique key. Held to commit; reentrant in a
        # transaction. SQLite already serializes writers. Signed 64-bit key.
        key = hashlib.sha256(f"m8flow:model-version:{tenant_id}:{process_model_identifier}".encode()).digest()
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int.from_bytes(key[:8], "big", signed=True)})
    files = _working_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    primary = _primary_file_name(tenant_id=tenant_id, process_model_identifier=process_model_identifier, files=files)
    digest = _digest(files, primary)
    newest = latest(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if action == ACTION_SAVE and newest is not None and newest.digest == digest:
        return None
    # shortcut: every distinct save keeps a full copy of the files forever; add a
    # retention policy (keep live + last N saves) if the table grows too large.
    row = ProcessModelVersionModel(
        m8f_tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        version=(newest.version if newest else 0) + 1,
        action=action,
        files=_encode(files),
        primary_file_name=primary,
        digest=digest,
        reverted_from_version=reverted_from_version,
        created_by=created_by or SYSTEM_USER,
    )
    session.add(row)
    session.flush()
    return row


def ensure_baseline(
    session: Session, *, tenant_id: str, process_model_identifier: str, created_by: str = SYSTEM_USER
) -> ProcessModelVersionModel | None:
    """A model published before history existed gets its current files recorded
    as the live version, before anything changes them."""
    if not catalog.model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        return None
    status = catalog.process_model_status(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if status == catalog.PROCESS_MODEL_STATUS_DRAFT:
        return None
    if live(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier) is not None:
        return None
    return record(
        session,
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        action=ACTION_BASELINE,
        created_by=created_by,
    )


@contextmanager
def recording(session: Session, *, tenant_id: str, process_model_identifier: str, created_by: str) -> Iterator[None]:
    """Wrap a working-copy write: baseline before it, `save` row after it."""
    ensure_baseline(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    yield
    record(
        session,
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        action=ACTION_SAVE,
        created_by=created_by,
    )


def publish(
    session: Session, *, tenant_id: str, process_model_identifier: str, user_id: int, created_by: str
) -> ProcessModelVersionModel | None:
    """Make the working copy live and import it into core, so Start and timer
    starts run it from now on. No-op when it already matches the live row."""
    current = live(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if current is not None and current.digest == _working_digest(
        tenant_id=tenant_id, process_model_identifier=process_model_identifier
    ):
        return None
    row = record(
        session,
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        action=ACTION_PUBLISH,
        created_by=created_by,
    )
    if row is not None:
        workflow.ensure_live_definition(
            session, tenant_id=tenant_id, user_id=user_id, process_model_identifier=process_model_identifier
        )
    return row


def live_sources(
    session: Session, *, tenant_id: str, process_model_identifier: str
) -> tuple[str, str, str | None] | None:
    """(primary BPMN file name, BPMN XML, DMN XML) of the live version; None when
    nothing is live yet. The DMN is picked as save picks it
    (catalog._model_dmn_xml: first by sorted name)."""
    row = live(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    if row is None:
        return None
    files = _decode(row.files)
    name = row.primary_file_name if row.primary_file_name in files else None
    if name is None or not name.lower().endswith(".bpmn"):
        bpmn = sorted(n for n in files if n.lower().endswith(".bpmn"))
        name = bpmn[0] if bpmn else None
    if name is None:
        return None
    dmn_names = sorted(n for n in files if n.lower().endswith(".dmn"))
    try:
        xml = files[name].decode("utf-8")
        dmn_xml = files[dmn_names[0]].decode("utf-8") if dmn_names else None
    except UnicodeDecodeError as exc:
        # Same 400 as read_primary_bpmn gives for a non-UTF-8 file on disk.
        raise ApiError("invalid_file_content", "File is not valid UTF-8", 400) from exc
    catalog._reject_unsupported_constructs(xml)  # noqa: SLF001
    return name, xml, dmn_xml


def status_fields(session: Session, *, tenant_id: str, process_model_identifier: str) -> dict[str, Any]:
    key = (tenant_id, process_model_identifier)
    return status_fields_for_rows(session, [{"tenant_id": tenant_id, "id": process_model_identifier}])[key]


def _newest(session: Session, keys: set[tuple[str, str]], *, live_only: bool) -> dict[tuple[str, str], Any]:
    """(version, digest) of each model's newest row; `files` is never loaded."""
    newest = select(
        ProcessModelVersionModel.m8f_tenant_id,
        ProcessModelVersionModel.process_model_identifier,
        func.max(ProcessModelVersionModel.version).label("version"),
    ).where(
        tuple_(ProcessModelVersionModel.m8f_tenant_id, ProcessModelVersionModel.process_model_identifier).in_(
            list(keys)
        )
    )
    if live_only:
        newest = newest.where(ProcessModelVersionModel.action.in_(LIVE_ACTIONS))
    newest = newest.group_by(
        ProcessModelVersionModel.m8f_tenant_id, ProcessModelVersionModel.process_model_identifier
    ).subquery()
    rows = session.execute(
        select(
            ProcessModelVersionModel.m8f_tenant_id,
            ProcessModelVersionModel.process_model_identifier,
            ProcessModelVersionModel.version,
            ProcessModelVersionModel.digest,
        ).join(
            newest,
            (ProcessModelVersionModel.m8f_tenant_id == newest.c.m8f_tenant_id)
            & (ProcessModelVersionModel.process_model_identifier == newest.c.process_model_identifier)
            & (ProcessModelVersionModel.version == newest.c.version),
        )
    ).all()
    return {(row.m8f_tenant_id, row.process_model_identifier): row for row in rows}


def status_fields_for_rows(session: Session, rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """`has_unpublished_changes` = the working copy differs from the live version.
    Every working-copy write goes through `record`, so the newest row's digest is
    the working copy's: no disk read. With nothing live it is False by definition:
    a draft's "not yet published" is its status, and a pre-history published
    model runs its file on disk, so there is nothing for it to differ from."""
    keys = {(row["tenant_id"], row["id"]) for row in rows}
    if not keys:
        return {}
    live_rows = _newest(session, keys, live_only=True)
    newest_rows = _newest(session, keys, live_only=False)
    fields: dict[tuple[str, str], dict[str, Any]] = {}
    for key in keys:
        current = live_rows.get(key)
        if current is None:
            fields[key] = {"live_version": None, "has_unpublished_changes": False}
        else:
            fields[key] = {
                "live_version": current.version,
                "has_unpublished_changes": newest_rows[key].digest != current.digest,
            }
    return fields


def list_versions(
    session: Session, *, tenant_id: str, process_model_identifier: str, page: int = 1, per_page: int = 50
) -> dict[str, Any]:
    page = max(1, page)
    per_page = min(max(1, per_page), MAX_PER_PAGE)
    total = session.scalar(
        select(func.count()).select_from(_rows(tenant_id, process_model_identifier).subquery())
    ) or 0
    current = live(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    rows = session.scalars(
        _rows(tenant_id, process_model_identifier)
        .order_by(ProcessModelVersionModel.version.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return {
        "results": [
            {
                "version": row.version,
                "action": row.action,
                "created_by": row.created_by,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "reverted_from_version": row.reverted_from_version,
                "primary_file_name": row.primary_file_name,
                "is_live": current is not None and row.id == current.id,
            }
            for row in rows
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    }


def revert(
    session: Session, *, tenant_id: str, process_model_identifier: str, version: int, user_id: int, created_by: str
) -> ProcessModelVersionModel | None:
    """Restore version `version`'s files into the working copy. Does not go live."""
    if not catalog.model_exists(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        raise ApiError("not_found", "Process model not found", 404)
    target = session.scalars(
        _rows(tenant_id, process_model_identifier).where(ProcessModelVersionModel.version == version)
    ).first()
    if target is None:
        raise ApiError("not_found", f"Version {version} not found", 404)
    files = _decode(target.files, strict=True)
    for name in files:
        catalog.validate_leaf_file_name(name)
    bpmn_name = target.primary_file_name if target.primary_file_name in files else None
    if bpmn_name is None or not bpmn_name.lower().endswith(".bpmn"):
        bpmn = sorted(n for n in files if n.lower().endswith(".bpmn"))
        bpmn_name = bpmn[0] if bpmn else None
    if bpmn_name is None:
        raise ApiError("invalid_version", f"Version {version} has no BPMN file", 400)

    # Validate before any side effect: a version that cannot be imported must
    # not leave a stray `save` row or a half-restored working copy behind.
    # Core imports one DMN per definition; pick it exactly as save does
    # (catalog._model_dmn_xml: first by sorted name) so revert == save.
    dmn_names = sorted(n for n in files if n.lower().endswith(".dmn"))
    try:
        xml = files[bpmn_name].decode("utf-8")
        dmn_xml = files[dmn_names[0]].decode("utf-8") if dmn_names else None
    except UnicodeDecodeError as exc:
        # Same 400 as live_sources and catalog.read_primary_bpmn.
        raise ApiError("invalid_file_content", f"Version {version} has a file that is not valid UTF-8", 400) from exc
    catalog._reject_unsupported_constructs(xml)  # noqa: SLF001

    # Nothing on disk may be lost: capture the current working copy first.
    ensure_baseline(session, tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    record(
        session,
        tenant_id=tenant_id,
        process_model_identifier=process_model_identifier,
        action=ACTION_SAVE,
        created_by=created_by,
    )

    workflow.validate_definition(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        bpmn_identifier=process_model_identifier,
        source_bpmn_xml=xml,
        source_dmn_xml=dmn_xml,
        bpmn_name=bpmn_name,
    )
    # The disk is not part of the DB transaction: if anything below fails, the
    # session rolls back, so put the working copy back to match it.
    before = _working_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier)
    meta_path = _model_path(tenant_id, process_model_identifier, "process_model.json")
    meta_before = meta_path.read_bytes() if meta_path.is_file() else None
    try:
        _replace_working_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier, files=files)
        if target.primary_file_name in files:
            catalog.update_process_model_metadata(
                tenant_id=tenant_id,
                process_model_identifier=process_model_identifier,
                primary_file_name=target.primary_file_name,
            )
        return record(
            session,
            tenant_id=tenant_id,
            process_model_identifier=process_model_identifier,
            action=ACTION_REVERT,
            created_by=created_by,
            reverted_from_version=version,
        )
    except BaseException:
        _replace_working_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier, files=before)
        if meta_before is not None:
            meta_path.write_bytes(meta_before)
        else:
            # A model may have no process_model.json (any dir with a .bpmn is a model).
            meta_path.unlink(missing_ok=True)
        raise


def _model_path(tenant_id: str, process_model_identifier: str, file_name: str):
    return catalog._resolved_inside_tenant(  # noqa: SLF001
        tenant_id, process_model_identifier, file_name, **catalog._MODEL_PATH_ERROR  # noqa: SLF001
    )


def _replace_working_files(*, tenant_id: str, process_model_identifier: str, files: dict[str, bytes]) -> None:
    """Make the model's files exactly `files` (process_model.json untouched)."""
    for name, body in files.items():
        catalog.write_spec_file(tenant_id=tenant_id, path=process_model_identifier, file_name=name, content=body)
    for existing in catalog.list_model_files(tenant_id=tenant_id, process_model_identifier=process_model_identifier):
        if existing["name"] not in files:
            _model_path(tenant_id, process_model_identifier, existing["name"]).unlink()


def delete_all(session: Session, *, tenant_id: str, process_model_identifier: str) -> None:
    session.execute(
        delete(ProcessModelVersionModel).where(
            ProcessModelVersionModel.m8f_tenant_id == tenant_id,
            ProcessModelVersionModel.process_model_identifier == process_model_identifier,
        )
    )
