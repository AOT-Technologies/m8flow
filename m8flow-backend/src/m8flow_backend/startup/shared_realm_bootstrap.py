from __future__ import annotations

import logging
import os
from typing import Any

import sqlalchemy as sa

from m8flow_backend.config import default_organization_alias
from m8flow_backend.config import default_organization_name
from m8flow_backend.services.keycloak_service import get_organization_by_alias
from m8flow_backend.tenancy import create_tenant_if_not_exists

logger = logging.getLogger(__name__)

_SKIP_ENVIRONMENTS = {"unit_testing", "testing"}


def _should_skip_shared_realm_reconciliation() -> bool:
    env = (os.environ.get("SPIFFWORKFLOW_BACKEND_ENV") or "").strip().lower()
    return env in _SKIP_ENVIRONMENTS


def _tenant_scoped_table_names(engine: Any) -> list[str]:
    inspector = sa.inspect(engine)
    table_names: list[str] = []
    for table_name in inspector.get_table_names():
        if table_name == "m8flow_tenant":
            continue
        try:
            column_names = {column["name"] for column in inspector.get_columns(table_name)}
        except Exception:
            continue
        if "m8f_tenant_id" in column_names:
            table_names.append(table_name)
    return table_names


def _update_tenant_scoped_rows(db_session: Any, engine: Any, old_tenant_id: str, new_tenant_id: str) -> list[str]:
    updated_tables: list[str] = []
    for table_name in _tenant_scoped_table_names(engine):
        result = db_session.execute(
            sa.text(
                f'UPDATE "{table_name}" '
                "SET m8f_tenant_id = :new_tenant_id "
                "WHERE m8f_tenant_id = :old_tenant_id"
            ),
            {
                "new_tenant_id": new_tenant_id,
                "old_tenant_id": old_tenant_id,
            },
        )
        if getattr(result, "rowcount", 0):
            updated_tables.append(table_name)
    return updated_tables


def _rename_tenant_scoped_groups(db_session: Any, old_tenant_id: str, new_tenant_id: str) -> list[tuple[str, str]]:
    from spiffworkflow_backend.models.group import GroupModel

    old_prefix = f"{old_tenant_id}:"
    new_prefix = f"{new_tenant_id}:"
    renamed_groups: list[tuple[str, str]] = []

    groups = GroupModel.query.filter(GroupModel.identifier.like(f"{old_prefix}%")).order_by(GroupModel.id).all()
    for group in groups:
        old_identifier = group.identifier
        if not isinstance(old_identifier, str) or not old_identifier.startswith(old_prefix):
            continue

        suffix = old_identifier[len(old_prefix) :]
        if not suffix:
            continue

        new_identifier = f"{new_prefix}{suffix}"
        if new_identifier == old_identifier:
            continue

        existing = GroupModel.query.filter(GroupModel.identifier == new_identifier).first()
        if existing is not None and existing.id != group.id:
            logger.warning(
                "shared_realm_bootstrap: group identifier %s already exists; skipping rename from %s",
                new_identifier,
                old_identifier,
            )
            continue

        group.identifier = new_identifier
        renamed_groups.append((old_identifier, new_identifier))

    if renamed_groups:
        db_session.flush()
    return renamed_groups


def resolve_default_shared_realm_tenant_id() -> str | None:
    """
    Resolve the tenant id for shared-realm bootstrap data.

    The canonical shared-realm tenant row always keeps the default organization
    alias as its slug, so a slug lookup works for both the legacy alias-id row
    and the post-reconciliation canonical organization-id row.
    """
    organization_alias = default_organization_alias()
    if not isinstance(organization_alias, str) or not organization_alias.strip():
        return None

    try:
        from m8flow_backend.models.m8flow_tenant import M8flowTenantModel

        tenant = M8flowTenantModel.query.filter_by(slug=organization_alias.strip()).first()
    except Exception:
        return None

    tenant_id = getattr(tenant, "id", None)
    if not isinstance(tenant_id, str):
        return None

    normalized_tenant_id = tenant_id.strip()
    return normalized_tenant_id or None


def reconcile_default_shared_realm_tenant(flask_app: Any) -> None:
    """
    Reconcile the canonical shared-realm tenant row with the Keycloak organization id.

    The m8flow seed migration creates a legacy alias-based row. On shared-realm
    installs we want the canonical tenant id to be the Keycloak organization id so
    that tenant-qualified group identifiers and tenant-scoped rows share the same
    prefix.
    """
    if _should_skip_shared_realm_reconciliation():
        return

    organization_alias = default_organization_alias()
    if not isinstance(organization_alias, str) or not organization_alias.strip():
        return
    organization_alias = organization_alias.strip()

    with flask_app.app_context():
        try:
            organization = get_organization_by_alias(organization_alias)
        except Exception:
            logger.warning(
                "shared_realm_bootstrap: unable to resolve default organization '%s' from Keycloak",
                organization_alias,
                exc_info=True,
            )
            return

        if not isinstance(organization, dict):
            logger.warning(
                "shared_realm_bootstrap: default organization '%s' was not returned as a dict",
                organization_alias,
            )
            return

        organization_id = organization.get("id")
        if not isinstance(organization_id, str) or not organization_id.strip():
            logger.warning(
                "shared_realm_bootstrap: default organization '%s' has no usable id",
                organization_alias,
            )
            return
        organization_id = organization_id.strip()

        organization_name = organization.get("name")
        if not isinstance(organization_name, str) or not organization_name.strip():
            organization_name = default_organization_name()
        organization_name = organization_name.strip()

        from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
        from spiffworkflow_backend.models.db import db

        canonical_tenant = db.session.get(M8flowTenantModel, organization_id)
        legacy_tenant = None if canonical_tenant is not None else M8flowTenantModel.query.filter_by(slug=organization_alias).first()

        if canonical_tenant is None and legacy_tenant is None:
            create_tenant_if_not_exists(
                organization_id,
                name=organization_name,
                slug=organization_alias,
            )
            logger.info(
                "shared_realm_bootstrap: created canonical shared-realm tenant id=%s slug=%s",
                organization_id,
                organization_alias,
            )
            return

        tenant = canonical_tenant or legacy_tenant
        assert tenant is not None

        old_tenant_id = tenant.id.strip() if isinstance(tenant.id, str) else ""
        tenant_changed = False

        if old_tenant_id and old_tenant_id != organization_id:
            updated_tables = _update_tenant_scoped_rows(db.session, db.engine, old_tenant_id, organization_id)
            renamed_groups = _rename_tenant_scoped_groups(db.session, old_tenant_id, organization_id)
            tenant.id = organization_id
            tenant_changed = True
            logger.info(
                "shared_realm_bootstrap: canonicalized shared-realm tenant id from %s to %s (updated_tables=%s renamed_groups=%s)",
                old_tenant_id,
                organization_id,
                updated_tables,
                renamed_groups,
            )

        if tenant.slug != organization_alias:
            tenant.slug = organization_alias
            tenant_changed = True
        if tenant.name != organization_name:
            tenant.name = organization_name
            tenant_changed = True

        if tenant_changed:
            db.session.add(tenant)
            db.session.commit()
