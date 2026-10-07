from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import MetaData, event, inspect
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_host_%(column_0_label)s",
    "uq": "uq_host_%(table_name)s_%(column_0_name)s",
    "ck": "ck_host_%(table_name)s_%(column_0_name)s",
    "fk": "fk_host_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_host_%(table_name)s",
}


class HostBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    @classmethod
    def commit_with_rollback_on_exception(cls) -> None:
        from m8flow_backend.db import current_session

        current_session().flush()


def _timestamp_pairs(mapper: Any) -> tuple[tuple[str, str], ...]:
    """Return native timestamp columns declared by a host table."""
    columns = set(mapper.columns.keys())
    return tuple(
        (name, name)
        for name in ("created_at", "updated_at")
        if name in columns
    )


@event.listens_for(HostBase, "before_insert", propagate=True)
def _synchronize_host_timestamps_before_insert(mapper: Any, connection: Any, target: Any) -> None:
    pairs = _timestamp_pairs(mapper)
    if not pairs:
        return
    now = datetime.now(UTC)
    if any(native == "created_at" for _legacy, native in pairs) and target.created_at is None:
        target.created_at = now
    if any(native == "updated_at" for _legacy, native in pairs) and target.updated_at is None:
        target.updated_at = now


@event.listens_for(HostBase, "before_update", propagate=True)
def _synchronize_host_timestamps_before_update(mapper: Any, connection: Any, target: Any) -> None:
    pairs = _timestamp_pairs(mapper)
    if not pairs:
        return
    state = inspect(target)
    if any(native == "updated_at" for _legacy, native in pairs):
        if not state.attrs.updated_at.history.has_changes():
            target.updated_at = datetime.now(UTC)
