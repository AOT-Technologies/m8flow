from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from m8flow_bpmn_core.models.group import GroupModel
from m8flow_bpmn_core.models.permission_assignment import PermissionAssignmentModel
from m8flow_bpmn_core.models.permission_target import PermissionTargetModel
from m8flow_bpmn_core.models.principal import PrincipalModel
from m8flow_bpmn_core.models.tenant import M8flowTenantModel, TenantStatus
from m8flow_bpmn_core.models.user import UserModel
from m8flow_bpmn_core.models.user_group_assignment import UserGroupAssignmentModel

LOGGER = logging.getLogger(__name__)

TIMER_SYSTEM_USERNAME = "__m8f_timer_start__"
GLOBAL_GROUP = "super-admin"

# Permission-target URI macros used in config/permissions/m8flow.yml, expanded
# to the same wildcard targets m8flow-bpmn-core seeds. Kept in sync with the
# YAML's documented macros (PM:ALL / PG:ALL).
_URI_MACROS = {
    "PM:ALL": "/process-models/%",
    "PG:ALL": "/process-groups/%",
}


def _normalize_target_uri(uri: str) -> str:
    """Match PermissionTargetModel.validate_uri: expand YAML macros and
    normalize the `*` wildcard to `%`, so lookups here find the exact rows the
    model stores (the model rewrites `*`->`%` on write; without the same
    rewrite on lookup, `grant()` misses existing rows and re-inserting collides
    on the (uri, command) unique constraint — the idempotency bug)."""
    resolved = _URI_MACROS.get(uri.strip(), uri.strip())
    return re.sub(r"\*", "%", resolved)


def ensure_tenant(
    session: Session,
    *,
    tenant_id: str,
    name: str | None = None,
    slug: str | None = None,
) -> M8flowTenantModel:
    tenant = session.get(M8flowTenantModel, tenant_id)
    if tenant is not None:
        return tenant
    tenant = session.scalars(
        select(M8flowTenantModel).where(M8flowTenantModel.slug == (slug or tenant_id))
    ).first()
    if tenant is not None:
        return tenant
    now = int(time.time())
    tenant = M8flowTenantModel(
        id=tenant_id,
        name=name or tenant_id,
        slug=slug or tenant_id,
        status=TenantStatus.ACTIVE,
        created_by="system",
        modified_by="system",
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
    )
    session.add(tenant)
    session.flush()
    return tenant


def find_user_by_service_identity(session: Session, *, service: str, service_id: str) -> UserModel | None:
    """The one place `(service, service_id)` -> UserModel lookups happen."""
    return session.scalars(
        select(UserModel).where(UserModel.service == service, UserModel.service_id == service_id)
    ).first()


def find_users_by_username(session: Session, username: str) -> list[UserModel]:
    """The one place exact-username -> UserModel lookups happen."""
    return list(session.scalars(select(UserModel).where(UserModel.username == username)).all())


def find_users_by_username_prefix(session: Session, username_prefix: str) -> list[UserModel]:
    """The one place username-prefix -> UserModel lookups happen."""
    return list(
        session.scalars(select(UserModel).where(UserModel.username.like(f"{username_prefix}%"))).all()
    )


def ensure_user(
    session: Session,
    *,
    username: str,
    service: str,
    service_id: str,
    email: str | None = None,
) -> UserModel:
    user = find_user_by_service_identity(session, service=service, service_id=service_id)
    if user is not None:
        return user
    if username == TIMER_SYSTEM_USERNAME:
        existing_timer = session.scalars(
            select(UserModel).where(UserModel.username == TIMER_SYSTEM_USERNAME)
        ).first()
        if existing_timer is not None:
            return existing_timer
    now = int(time.time())
    user = UserModel(
        username=username,
        email=email,
        service=service,
        service_id=service_id,
        display_name=username,
        created_at_in_seconds=now,
        updated_at_in_seconds=now,
    )
    session.add(user)
    session.flush()
    principal = PrincipalModel(user_id=user.id)
    session.add(principal)
    session.flush()
    return user


def ensure_membership(session: Session, user: UserModel, active_tenant: M8flowTenantModel) -> UserModel:
    """Replace field_1 with active tenant id and field_2 with slug when it differs."""
    user.tenant_specific_field_1 = active_tenant.id
    if active_tenant.slug and active_tenant.slug != active_tenant.id:
        user.tenant_specific_field_2 = active_tenant.slug
    else:
        user.tenant_specific_field_2 = None
    session.add(user)
    return user


def sync_groups(
    session: Session,
    *,
    user: UserModel,
    group_identifiers: list[str],
    tenant_id: str,
) -> None:
    desired: set[str] = set()
    for identifier in group_identifiers:
        normalized = identifier.strip()
        if not normalized:
            continue
        if ":" not in normalized:
            if normalized != GLOBAL_GROUP:
                continue
            desired.add(normalized)
            continue
        desired.add(normalized)

    for identifier in desired:
        group = _ensure_group(session, identifier)
        assignment = session.scalars(
            select(UserGroupAssignmentModel).where(
                UserGroupAssignmentModel.user_id == user.id,
                UserGroupAssignmentModel.group_id == group.id,
            )
        ).first()
        if assignment is None:
            session.add(UserGroupAssignmentModel(user_id=user.id, group_id=group.id))


@dataclass
class _YamlGrantCache:
    """In-memory grant rows for one ``import_yaml`` pass.

    Without a cache each ``grant()`` issues a permission_target lookup by
    (uri, command) and a permission_assignment lookup — thousands of
    round-trips for an idempotent no-op.
    """

    session: Session
    targets: dict[tuple[str, str | None], PermissionTargetModel] = field(default_factory=dict)
    assignments: dict[tuple[int, int, str], PermissionAssignmentModel] = field(default_factory=dict)

    @classmethod
    def load(cls, session: Session) -> _YamlGrantCache:
        cache = cls(session=session)
        cache.targets = {
            (row.uri, row.command): row for row in session.scalars(select(PermissionTargetModel)).all()
        }
        cache.assignments = {
            (row.principal_id, row.permission_target_id, row.permission): row
            for row in session.scalars(select(PermissionAssignmentModel)).all()
        }
        return cache

    def target(self, uri: str, command: str | None) -> PermissionTargetModel:
        key = (uri, command)
        existing = self.targets.get(key)
        if existing is not None:
            return existing
        created = PermissionTargetModel(uri=uri, command=command)
        self.session.add(created)
        self.session.flush()
        self.targets[key] = created
        return created

    def assignment(
        self,
        *,
        principal_id: int,
        target_id: int,
        permission: str,
        grant_type: str,
    ) -> PermissionAssignmentModel:
        key = (principal_id, target_id, permission)
        existing = self.assignments.get(key)
        if existing is not None:
            # Same value is a no-op. Assigning anyway dirties the row and
            # every authenticated request would UPDATE hundreds of
            # permission_assignment rows (row locks under Home's parallel
            # GETs).
            if existing.grant_type != grant_type:
                existing.grant_type = grant_type
            return existing
        created = PermissionAssignmentModel(
            principal_id=principal_id,
            permission_target_id=target_id,
            permission=permission,
            grant_type=grant_type,
        )
        self.session.add(created)
        self.session.flush()
        self.assignments[key] = created
        return created


def grant(
    session: Session,
    *,
    principal: PrincipalModel,
    uri: str,
    permission: str,
    grant_type: str = "permit",
    command: str | None = None,
    cache: _YamlGrantCache | None = None,
) -> PermissionAssignmentModel:
    uri = _normalize_target_uri(uri)
    if cache is not None:
        target = cache.target(uri, command)
        return cache.assignment(
            principal_id=principal.id,
            target_id=target.id,
            permission=permission,
            grant_type=grant_type,
        )
    target = session.scalars(
        select(PermissionTargetModel).where(
            PermissionTargetModel.uri == uri,
            PermissionTargetModel.command == command,
        )
    ).first()
    if target is None:
        target = PermissionTargetModel(uri=uri, command=command)
        session.add(target)
        session.flush()
    existing = session.scalars(
        select(PermissionAssignmentModel).where(
            PermissionAssignmentModel.principal_id == principal.id,
            PermissionAssignmentModel.permission_target_id == target.id,
            PermissionAssignmentModel.permission == permission,
        )
    ).first()
    if existing is not None:
        existing.grant_type = grant_type
        return existing
    assignment = PermissionAssignmentModel(
        principal_id=principal.id,
        permission_target_id=target.id,
        permission=permission,
        grant_type=grant_type,
    )
    session.add(assignment)
    session.flush()
    return assignment


def import_yaml(session: Session | Any = None, *, tenant_id: str | None = None, yaml_path: str | None = None) -> None:
    if session is None or not hasattr(session, "get"):
        from flask import g

        from m8flow_backend.db import current_session

        session = current_session()
        tenant_id = tenant_id or getattr(g, "m8flow_tenant_id", None)
    import yaml

    path = yaml_path or os.environ.get("M8FLOW_PERMISSIONS_YAML")
    if path is None:
        path = str(
            Path_from_package()
        )
    with open(path, encoding="utf-8") as handle:
        document = yaml.safe_load(handle) or {}
    groups = document.get("groups") or {}
    permissions = document.get("permissions") or {}
    grant_cache = _YamlGrantCache.load(session)
    # One SELECT per distinct group/principal for this pass. The YAML file
    # repeats the same role names on tens of permission specs; looking them
    # up each time was ~400 round-trips on every authenticated request.
    groups_by_identifier: dict[str, GroupModel] = {}
    principals_by_group_id: dict[int, PrincipalModel] = {}

    def _group(identifier: str) -> GroupModel:
        cached = groups_by_identifier.get(identifier)
        if cached is not None:
            return cached
        group = _ensure_group(session, identifier)
        groups_by_identifier[identifier] = group
        return group

    def _principal_for(group: GroupModel) -> PrincipalModel:
        cached = principals_by_group_id.get(group.id)
        if cached is not None:
            return cached
        # Query the principal rather than reading group.principal: _ensure_group
        # already creates one for new groups, but the relationship may not be
        # populated on this instance yet, and a blind add() here duplicates it
        # (UNIQUE principal.group_id). Idempotent lookup instead.
        principal = session.scalars(
            select(PrincipalModel).where(PrincipalModel.group_id == group.id)
        ).first()
        if principal is None:
            principal = PrincipalModel(group_id=group.id)
            session.add(principal)
            session.flush()
        principals_by_group_id[group.id] = principal
        return principal

    for group_name in groups:
        identifier = group_name if group_name == GLOBAL_GROUP else (
            f"{tenant_id}:{group_name}" if tenant_id and ":" not in group_name else group_name
        )
        if ":" not in identifier and identifier != GLOBAL_GROUP:
            continue
        _group(identifier)
    for _name, spec in permissions.items():
        uris = spec.get("uri")
        if isinstance(uris, str):
            uris = [uris]
        actions = spec.get("actions") or ["read"]
        command = spec.get("command")
        group_names = spec.get("groups") or []
        for group_name in group_names:
            identifier = group_name if group_name == GLOBAL_GROUP else (
                f"{tenant_id}:{group_name}" if tenant_id and ":" not in str(group_name) else str(group_name)
            )
            if identifier == "everybody" or (
                ":" not in identifier and identifier != GLOBAL_GROUP and identifier != "everybody"
            ):
                if identifier != "everybody":
                    continue
                identifier = f"{tenant_id}:user" if tenant_id else identifier
            group = _group(identifier)
            principal = _principal_for(group)
            for uri in uris or []:
                for action in actions:
                    grant(
                        session,
                        principal=principal,
                        uri=str(uri),
                        permission=str(action),
                        command=command,
                        cache=grant_cache,
                    )
    if tenant_id:
        from m8flow_bpmn_core.services.authorization import ensure_v1_role

        ensure_v1_role(session, tenant_id=tenant_id, role_name="admin")


# Marker role import_yaml always creates for a tenant. Presence of any grant
# on `{tenant_id}:editor` means this tenant already has YAML permissions.
_YAML_SEED_MARKER_ROLE = "editor"


def tenant_yaml_grants_present(session: Session, *, tenant_id: str) -> bool:
    """True when ``import_yaml`` has already materialized grants for this tenant.

    Auth used to re-run YAML seeding on every authenticated request. After the
    first seed this is a single exists-query so Home's parallel GETs don't
    each repeat hundreds of group/principal lookups.
    """
    if not tenant_id or not str(tenant_id).strip():
        return False
    identifier = f"{str(tenant_id).strip()}:{_YAML_SEED_MARKER_ROLE}"
    stmt = (
        select(PermissionAssignmentModel.id)
        .join(PrincipalModel, PrincipalModel.id == PermissionAssignmentModel.principal_id)
        .join(GroupModel, GroupModel.id == PrincipalModel.group_id)
        .where(GroupModel.identifier == identifier)
        .limit(1)
    )
    return session.scalars(stmt).first() is not None


def allocate_lane_group_id(lane_name: str) -> int:
    from m8flow_bpmn_core.services.workflow_runtime import resolve_lane_assignment_id

    return resolve_lane_assignment_id(lane_name)


def ensure_group(session: Session | str, identifier: str | None = None, **_kwargs) -> GroupModel:
    if identifier is None or isinstance(session, str):
        from m8flow_backend.db import current_session

        identifier = session if isinstance(session, str) else identifier
        session = current_session()
    return _ensure_group(session, identifier)


def _ensure_group(session: Session, identifier: str) -> GroupModel:
    group = session.scalars(select(GroupModel).where(GroupModel.identifier == identifier)).first()
    if group is not None:
        return group
    group = GroupModel(identifier=identifier, name=identifier, source_is_open_id=True)
    session.add(group)
    session.flush()
    if group.principal is None:
        session.add(PrincipalModel(group_id=group.id))
        session.flush()
    return group


def Path_from_package() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parents[1] / "config" / "permissions" / "m8flow.yml")


def ensure_tenant_exists(tenant_id: str | None) -> None:
    """Validate that the tenant row exists; raise if missing to enforce pre-provisioning.

    Relocated from tenancy.py during the active-tenant deep-module collapse
    (ticket 03): provisioning/validation is identity's job, not auth's.
    """
    if not tenant_id:
        from m8flow_backend.auth.tenant_context import TENANT_CLAIM

        raise RuntimeError(
            f"Missing tenant id. Ensure the token contains {TENANT_CLAIM} (or set tenant in request context)."
        )

    from flask import g
    from m8flow_bpmn_core.models.tenant import M8flowTenantModel

    session = getattr(g, "db_session", None)
    tenant = session.get(M8flowTenantModel, tenant_id) if session is not None else None

    if tenant is None:
        raise RuntimeError(
            f"Tenant '{tenant_id}' does not exist. Create it in m8flow_tenant before using M8Flow."
        )


def _tenant_row_exists(session: Session, tenant_id: str, slug_value: str) -> bool:
    if session.get(M8flowTenantModel, tenant_id) is not None:
        return True
    return (
        session.scalars(select(M8flowTenantModel).where(M8flowTenantModel.slug == slug_value)).first() is not None
    )


def _ensure_tenant_and_vault_identity(session: Session, *, tenant_id: str, display_name: str, slug_value: str) -> None:
    from m8flow_backend.secrets.provisioning import TenantVaultProvisioningError, provision_vault_identity_if_enabled

    existed = _tenant_row_exists(session, tenant_id, slug_value)
    tenant = ensure_tenant(session, tenant_id=tenant_id, name=display_name, slug=slug_value)
    if existed:
        return
    try:
        provision_vault_identity_if_enabled(tenant_id)
    except TenantVaultProvisioningError:
        session.delete(tenant)
        session.flush()
        raise


def create_tenant_if_not_exists(
    tenant_id: str,
    name: str | None = None,
    slug: str | None = None,
) -> None:
    """Create a tenant row if it does not exist (e.g. after creating a Keycloak realm).
    When slug is provided (e.g. realm name), it is used for M8flowTenantModel.slug;
    otherwise slug defaults to tenant_id (backward compatible).

    Relocated from tenancy.py during the active-tenant deep-module collapse
    (ticket 03): provisioning is identity's job, not auth's.
    """
    if not tenant_id or not tenant_id.strip():
        return
    tenant_id = tenant_id.strip()
    display_name = (name or tenant_id).strip()
    slug_value = (slug or tenant_id).strip()

    from flask import g

    session = getattr(g, "db_session", None)
    if session is None:
        from m8flow_backend.db import session_scope

        with session_scope() as scoped:
            _ensure_tenant_and_vault_identity(
                scoped, tenant_id=tenant_id, display_name=display_name, slug_value=slug_value
            )
        LOGGER.info("Created tenant row for tenant_id=%s name=%s slug=%s", tenant_id, display_name, slug_value)
        return
    _ensure_tenant_and_vault_identity(
        session, tenant_id=tenant_id, display_name=display_name, slug_value=slug_value
    )
    LOGGER.info("Created tenant row for tenant_id=%s name=%s slug=%s", tenant_id, display_name, slug_value)
