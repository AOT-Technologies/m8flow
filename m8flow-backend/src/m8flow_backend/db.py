from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, MetaData, and_, create_engine, event, func, or_
from sqlalchemy.orm import Session, sessionmaker

from m8flow_bpmn_core.models.base import Base as CoreBase
from m8flow_backend.models.host_base import HostBase

LOGGER = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def database_url() -> str:
    return (
        os.environ.get("M8FLOW_BACKEND_DATABASE_URI")
        or os.environ.get("M8FLOW_DATABASE_URI")
        or "sqlite:///:memory:"
    )


def _sqlalchemy_echo_enabled() -> bool:
    return (os.environ.get("M8FLOW_SQLALCHEMY_ECHO") or "").strip().lower() in {"1", "true", "yes", "on"}


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(
            url, echo=_sqlalchemy_echo_enabled(), future=True, connect_args=connect_args
        )
        from m8flow_backend.observability.sql_timing import attach_sql_timing_listeners

        attach_sql_timing_listeners(_engine)
        assert_disjoint_table_names()
    return _engine


def current_session() -> Session:
    try:
        from flask import g, has_request_context

        if has_request_context():
            session = getattr(g, "db_session", None)
            if session is not None:
                return session
            session = get_session_factory()()
            g.db_session = session
            return session
    except RuntimeError:
        # Called outside any Flask app/request context (e.g. a script or
        # background job) - expected, fall through to a fresh session below.
        LOGGER.debug("current_session() called outside Flask app context; using a new session", exc_info=True)
    return get_session_factory()()


class _Db:
    or_ = staticmethod(or_)
    and_ = staticmethod(and_)
    func = func

    @property
    def session(self) -> Session:
        return current_session()

    @property
    def engine(self) -> Engine:
        return get_engine()


db = _Db()


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
    return _session_factory


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def alembic_target_metadata() -> list[MetaData]:
    """Both core and host metadatas, with every host model imported.

    Alembic autogenerate and ``create_all`` must see the full host surface,
    including models that live outside ``models/native.py``.
    """
    import m8flow_bpmn_core.models  # noqa: F401
    import m8flow_backend.models  # noqa: F401
    import m8flow_backend.connectors.configuration  # noqa: F401

    return [CoreBase.metadata, HostBase.metadata]


def assert_disjoint_table_names() -> None:
    alembic_target_metadata()

    overlap = set(CoreBase.metadata.tables) & set(HostBase.metadata.tables)
    if overlap:
        raise RuntimeError(f"Host Base remaps core tables: {sorted(overlap)}")


def create_all(engine: Engine | None = None) -> None:
    metadatas = alembic_target_metadata()
    bind = engine or get_engine()
    assert_disjoint_table_names()
    for metadata in metadatas:
        metadata.create_all(bind)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def attach_host_timestamp_listeners() -> None:
    """Reattach created/updated epoch listeners on host models only."""
    import time

    import m8flow_backend.models  # noqa: F401
    import m8flow_backend.connectors.configuration  # noqa: F401

    def _before_insert(mapper, connection, target) -> None:
        now = int(time.time())
        if hasattr(target, "created_at_in_seconds") and not getattr(target, "created_at_in_seconds", None):
            target.created_at_in_seconds = now
        if hasattr(target, "updated_at_in_seconds"):
            target.updated_at_in_seconds = now

    def _before_update(mapper, connection, target) -> None:
        if hasattr(target, "updated_at_in_seconds"):
            target.updated_at_in_seconds = int(time.time())

    for mapper in HostBase.registry.mappers:
        cls = mapper.class_
        cols = set(mapper.columns.keys())
        if "created_at_in_seconds" not in cols and "updated_at_in_seconds" not in cols:
            continue
        if not event.contains(cls, "before_insert", _before_insert):
            event.listen(cls, "before_insert", _before_insert)
        if not event.contains(cls, "before_update", _before_update):
            event.listen(cls, "before_update", _before_update)
