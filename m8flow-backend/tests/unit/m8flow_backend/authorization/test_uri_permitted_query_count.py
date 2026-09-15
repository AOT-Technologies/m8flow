"""_uri_permitted must not lazy-load permission_target one row at a time."""

from __future__ import annotations

from sqlalchemy import event

from m8flow_backend import identity
from m8flow_backend.authorization import _uri_permitted
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups

_TENANT_ID = "t1"
_SERVICE = "https://example.test/realms/m8flow"


def _provision_editor(db_session):
    tenant = ensure_tenant(db_session, tenant_id=_TENANT_ID, slug=_TENANT_ID)
    user = ensure_user(db_session, username="editor-nplus1", service=_SERVICE, service_id="editor-nplus1")
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=[f"{_TENANT_ID}:editor"], tenant_id=_TENANT_ID)
    identity.import_yaml(db_session, tenant_id=_TENANT_ID)
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(user)
    return user


def _capture_sql(session):
    statements: list[str] = []
    engine = session.get_bind()

    def _before(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", _before)

    def _stop() -> None:
        event.remove(engine, "before_cursor_execute", _before)

    return statements, _stop


def test_uri_permitted_does_not_select_permission_target_by_id(db_session):
    user = _provision_editor(db_session)
    statements, stop = _capture_sql(db_session)
    try:
        assert _uri_permitted(db_session, user, "read", "/process-models") is True
    finally:
        stop()
    by_id = [
        sql
        for sql in statements
        if "permission_target" in sql.lower() and "permission_target.id =" in sql.replace('"', "")
    ]
    assert by_id == [], by_id
