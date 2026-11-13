"""Tenant-scoped working copies and immutable process releases."""

from __future__ import annotations

import json
from base64 import b64decode, b64encode
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from flask import g, has_app_context
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from m8flow_backend.errors import ApiError
from m8flow_backend.models.process_model_version import ProcessModelRelease, ProcessModelState


def request_session() -> Session | None:
    return getattr(g, "db_session", None) if has_app_context() else None


def lock_tenant(session: Session, tenant_id: str) -> None:
    """Serialize catalog changes and scheduler polling for this tenant."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        # Super-admin writes may bind a concrete tenant from the request body
        # after the authentication middleware opened the transaction.
        from m8flow_backend.auth import apply_postgres_rls

        apply_postgres_rls(session.connection())
        key = sha256(f"m8flow:process-models:{tenant_id}".encode()).digest()
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {
            "key": int.from_bytes(key[:8], "big", signed=True),
        })
    elif dialect == "sqlite":
        # Obtain SQLite's write reservation before reading the current revision.
        session.execute(update(ProcessModelState).where(False).values(deleted=True))


def state(session: Session | None, tenant_id: str, model_id: str) -> ProcessModelState | None:
    return session.get(ProcessModelState, (tenant_id, model_id)) if session is not None else None


def write_state(session: Session, tenant_id: str, model_id: str) -> ProcessModelState | None:
    return session.get(ProcessModelState, (tenant_id, model_id), populate_existing=True)


def states(session: Session, tenant_id: str) -> list[ProcessModelState]:
    return list(session.scalars(select(ProcessModelState).where(ProcessModelState.m8f_tenant_id == tenant_id)))


def model_releases(session: Session, model: ProcessModelState) -> list[ProcessModelRelease]:
    return list(session.scalars(
        select(ProcessModelRelease).where(
            ProcessModelRelease.m8f_tenant_id == model.m8f_tenant_id,
            ProcessModelRelease.model_id == model.model_id,
            ProcessModelRelease.generation == model.generation,
        ).order_by(ProcessModelRelease.version.desc())
    ))


def release(session: Session, model: ProcessModelState, number: int | None) -> ProcessModelRelease | None:
    if number is None:
        return None
    return session.get(ProcessModelRelease, (model.m8f_tenant_id, model.model_id, model.generation, number))


def snapshot(files: dict[str, bytes], primary: str | None = None, process_id: str | None = None) -> dict[str, Any]:
    return {
        "files": {name: encode_file(body) for name, body in files.items()},
        "primary_file_name": primary,
        "primary_process_id": process_id,
    }


def encode_file(body: bytes) -> str:
    return b64encode(body).decode("ascii")


def read_file(contents: dict[str, Any], name: str) -> bytes | None:
    body = contents["files"].get(name)
    return b64decode(body) if body is not None else None


def file_bytes(contents: dict[str, Any]) -> dict[str, bytes]:
    return {name: b64decode(body) for name, body in contents["files"].items()}


def bpmn_names(contents: dict[str, Any]) -> list[str]:
    return sorted(name for name in contents["files"] if name.lower().endswith(".bpmn"))


def primary_bpmn(contents: dict[str, Any], model_id: str) -> str | None:
    names = bpmn_names(contents)
    primary = contents["primary_file_name"] or f"{model_id.rsplit('/', 1)[-1]}.bpmn"
    if primary in names:
        return primary
    return names[0] if names else None


def legacy_model(tenant_id: str, model_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    from m8flow_backend import catalog

    directory = catalog._resolved_inside_tenant(tenant_id, model_id, **catalog._MODEL_PATH_ERROR)
    if not directory.is_dir():
        return None
    files = {}
    for path in directory.iterdir():
        if path.name.lower() in catalog._RESERVED_MODEL_FILE_NAMES or not path.is_file():
            continue
        catalog.validate_leaf_file_name(path.name)
        resolved = catalog._resolved_inside_tenant(tenant_id, model_id, path.name, **catalog._MODEL_PATH_ERROR)
        if resolved.parent != directory:
            raise ApiError("invalid_file_name", "Model files must be inside the model directory", 400)
        files[path.name] = resolved.read_bytes()
    if not any(name.lower().endswith(".bpmn") for name in files):
        return None
    meta = catalog._tenant_json(tenant_id, model_id, "process_model.json", **catalog._MODEL_PATH_ERROR)
    primary = meta.get("primary_file_name")
    process_id = meta.get("primary_process_id")
    return meta, snapshot(
        files, primary if isinstance(primary, str) and primary in files else None,
        process_id if isinstance(process_id, str) else None,
    )


def legacy_revision(contents: dict[str, Any]) -> str:
    return sha256(json.dumps(contents, sort_keys=True).encode()).hexdigest()[:32]


def initialize(
    session: Session,
    tenant_id: str,
    model_id: str,
    contents: dict[str, Any],
    *,
    display_name: str,
    description: str = "",
    status: str = "draft",
) -> ProcessModelState:
    generation = uuid4().hex
    model = state(session, tenant_id, model_id)
    if model is None:
        model = ProcessModelState(m8f_tenant_id=tenant_id, model_id=model_id)
        session.add(model)
    model.generation = generation
    model.working_revision = generation
    model.display_name = display_name
    model.description = description
    model.status = status
    model.working = contents
    model.deleted = False
    model.latest_version = None
    model.updated_at = datetime.now(UTC)
    if status in {"published", "paused"}:
        add_release(session, model, published_by=None, published_at=None)
    session.flush()
    return model


def import_legacy(session: Session, tenant_id: str, model_id: str) -> ProcessModelState | None:
    """Call under the catalog write lock. A tombstone also counts as imported."""
    from m8flow_backend import catalog

    existing = state(session, tenant_id, model_id)
    if existing is not None:
        return None if existing.deleted else existing
    legacy = legacy_model(tenant_id, model_id)
    if legacy is None:
        return None
    meta, contents = legacy
    status = meta.get("status")
    if not isinstance(status, str) or status.strip() not in catalog.PROCESS_MODEL_STATUSES:
        status = "published"
    name = meta.get("display_name")
    description = meta.get("description")
    model = initialize(
        session, tenant_id, model_id, contents, status=status.strip(),
        display_name=(name.strip() if isinstance(name, str) else "") or model_id.rsplit("/", 1)[-1],
        description=description.strip() if isinstance(description, str) else "",
    )
    model.working_revision = legacy_revision(contents)
    return model


def draft_number(session: Session, model: ProcessModelState) -> int | None:
    latest = release(session, model, model.latest_version)
    if latest is None:
        return 1
    return latest.version + 1 if latest.contents != model.working else None


def fields(session: Session, model: ProcessModelState) -> dict[str, Any]:
    draft = draft_number(session, model)
    return {
        "published_version": model.latest_version,
        "draft_version": draft,
        "has_unpublished_changes": model.latest_version is not None and draft is not None,
        "working_revision": model.working_revision,
    }


def check_revision(model: ProcessModelState, expected: str | None) -> None:
    if expected is not None and expected != model.working_revision:
        raise ApiError("stale_working_revision", "The draft changed. Reload the model before trying again.", 409)


def touch(model: ProcessModelState) -> None:
    model.working_revision = uuid4().hex
    model.updated_at = datetime.now(UTC)


def replace_working(model: ProcessModelState, contents: dict[str, Any]) -> None:
    if model.working != contents:
        model.working = contents
        touch(model)


def add_release(
    session: Session, model: ProcessModelState, *, published_by: str | None, published_at: datetime | None
) -> ProcessModelRelease:
    version = (model.latest_version or 0) + 1
    entry = ProcessModelRelease(
        m8f_tenant_id=model.m8f_tenant_id, model_id=model.model_id, generation=model.generation,
        version=version, contents=model.working, published_by=published_by, published_at=published_at,
    )
    session.add(entry)
    model.latest_version = version
    return entry


def definition_digest(entry: ProcessModelRelease, file_name: str) -> str:
    return sha256(f"m8flow:release:{entry.generation}:{entry.version}:{file_name}".encode()).hexdigest()


def definition_reference(entry: ProcessModelRelease) -> str:
    return f"{entry.generation}:{entry.version}"


def release_by_reference(
    session: Session, tenant_id: str, model_id: str, reference: str | None,
) -> ProcessModelRelease | None:
    generation, _, number = (reference or "").partition(":")
    if len(generation) != 32 or not number.isdecimal():
        return None
    return session.get(ProcessModelRelease, (tenant_id, model_id, generation, int(number)))
