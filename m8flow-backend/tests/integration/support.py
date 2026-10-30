"""Helpers shared by the integration tests (fixtures live in conftest.py)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SERVICE = "https://example.test/realms/m8flow"


@contextmanager
def tenant_session(tenant_id: str | None) -> Iterator[Session]:
    """A host session whose transactions carry ``app.current_tenant`` for RLS.

    The tenant is bound before the first statement because the RLS hook runs on
    ``after_begin``, as it does for a request. Commits on success.
    """
    from m8flow_backend.auth.tenant_context import reset_context_tenant_id, set_context_tenant_id
    from m8flow_backend.db import get_session_factory

    token = set_context_tenant_id(tenant_id)
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        reset_context_tenant_id(token)


def new_tenant_id(label: str) -> str:
    return f"it-{label}-{uuid.uuid4().hex[:8]}"


def provision_member(session: Session, *, tenant_id: str, role: str, name: str | None = None, lanes: tuple[str, ...] = ()):
    """A shared-realm user holding one tenant role, granted from m8flow.yml.

    Goes through the same identity calls as login (tenant, user, membership,
    group sync, YAML grants) so authorization decisions come from real rows.
    ``lanes`` are directory groups materialized as workflow-lane memberships.
    """
    from m8flow_backend import identity

    tenant = identity.ensure_tenant(session, tenant_id=tenant_id, slug=tenant_id)
    username = f"{name or role}-{tenant_id}"
    user = identity.ensure_user(
        session,
        username=username,
        service=SERVICE,
        service_id=username,
        email=f"{username}@example.test",
    )
    identity.ensure_membership(session, user, tenant)
    identity.sync_groups(
        session,
        user=user,
        group_identifiers=[f"{tenant_id}:{role}"],
        tenant_id=tenant_id,
    )
    if lanes:
        identity.sync_lane_groups(session, user=user, tenant_id=tenant_id, lane_group_identifiers=list(lanes))
    identity.import_yaml(session, tenant_id=tenant_id)
    session.flush()
    return user


def save_model(session: Session, *, tenant_id: str, user_id: int, path: str, fixture: str, xml: str | None = None) -> None:
    from m8flow_backend import catalog

    catalog.save(
        session,
        path=path,
        xml=xml if xml is not None else (FIXTURES / fixture).read_text(encoding="utf-8"),
        tenant_id=tenant_id,
        user_id=user_id,
    )
