from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from m8flow_bpmn_core import api
from m8flow_bpmn_core.models.permission_assignment import PermissionAssignmentModel
from m8flow_bpmn_core.models.principal import PrincipalModel
from m8flow_bpmn_core.models.user import UserModel
from m8flow_backend.errors import ApiError
from m8flow_backend.integrations.auth.base.roles import SUPER_ADMIN_ROLE
from m8flow_backend.auth.canonicalize import current_tenant_identifiers

# m8flow.yml's permission uris are written without this prefix (`/tasks`, not
# `/v1.0/tasks`); every real caller passes the actual route path, prefix and
# all. Without stripping it here, _uri_permitted's DB-backed grant check can
# never match any real request -- see architecture review finding C5.
_API_PATH_PREFIX = "/v1.0"


# Core authorizes process lifecycle commands with the explicit ``execute``
# permission. Keep that distinct from ``create``: creating an instance must
# not imply that a user can suspend, resume, retry, or terminate one.
_LIFECYCLE_COMMAND_KEYS = frozenset(
    {"process.suspend", "process.resume", "process.retry", "process.terminate"}
)
_PROCESS_START_COMMAND = "process.start"
_TASK_COMMAND_KEYS = frozenset({"task.claim", "task.complete"})


class HostAuthorizationPolicy:
    def authorize(self, session: Session, request: api.AuthorizationRequest) -> api.AuthorizationDecision:
        if _actor_is_super_admin(session, request.actor_user_id):
            return api.AuthorizationDecision(allowed=True, reason=SUPER_ADMIN_ROLE)
        if request.command_key == "process_definition.import":
            user = session.get(UserModel, request.actor_user_id)
            if user is not None and _resource_permitted(
                session,
                user,
                "create",
                "process_definition",
                request.resource_id,
            ):
                return api.AuthorizationDecision(allowed=True, reason="host_yaml")
        if request.command_key == _PROCESS_START_COMMAND:
            user = session.get(UserModel, request.actor_user_id)
            if user is not None:
                # Core authorizes this command against a concrete
                # process_model resource (for example, ``Test/foo``), while
                # the host YAML intentionally grants start at the tenant
                # scope via ``/process-models/%``. Translate that host grant
                # to the resource shape used by the core command.
                model_path = str(request.resource_id)
                if not model_path.startswith("/process-models/"):
                    model_path = f"/process-models/{model_path.lstrip('/')}"
                if _resource_permitted(session, user, "start", "tenant", model_path):
                    return api.AuthorizationDecision(allowed=True, reason="host_yaml")
        if request.command_key in _TASK_COMMAND_KEYS:
            user = session.get(UserModel, request.actor_user_id)
            if user is not None:
                # Core authorizes task commands against a concrete task
                # resource, while the host YAML grants task work at the
                # tenant scope via ``/tasks/*``.
                task_path = str(request.resource_id)
                if not task_path.startswith("/tasks/"):
                    task_path = f"/tasks/{task_path.lstrip('/')}"
                permission = str(request.permission)
                if _resource_permitted(session, user, permission, "tenant", task_path):
                    return api.AuthorizationDecision(allowed=True, reason="host_yaml")
        if request.command_key in _LIFECYCLE_COMMAND_KEYS:
            user = session.get(UserModel, request.actor_user_id)
            if user is not None:
                resource_type = str(getattr(request.resource_type, "value", request.resource_type))
                permission = str(getattr(request.permission, "value", request.permission))
                if permission != "execute":
                    return api.AuthorizationDecision(allowed=False, reason="lifecycle_requires_execute")
                direct_allowed = _resource_permitted(session, user, permission, resource_type, request.resource_id)
                route_allowed = _resource_permitted(
                    session, user, permission, "tenant", f"/process-instances/{request.resource_id}"
                )
                if direct_allowed:
                    return api.AuthorizationDecision(allowed=True, reason="host_yaml")
                # Host YAML grants lifecycle operations on route-shaped
                # instance paths, while core 0.2.1 authorizes the command
                # against an explicit process-instance resource pair.
                if route_allowed:
                    return api.AuthorizationDecision(allowed=True, reason="host_yaml")
        default = api.DatabaseAuthorizationPolicy()
        return default.authorize(session, request)


# Paths whose routes gate with ``group_fallback=False`` as policy, not per call site:
# NATS monitoring is split by what each endpoint can honestly be scoped to, and NATS
# API keys are tenant-admin only (see m8flow.yml). The tenant-admin/editor group
# fallback would re-open both to every tenant role. Applied inside ``allow_uri`` so
# every caller -- notably POST /permissions-check, which drives UI visibility -- answers
# exactly as the route will, instead of offering actions the route then refuses.
_NO_GROUP_FALLBACK_PREFIXES = ("/m8flow/nats/", "/m8flow/nats-tokens")


def _without_api_path_prefix(path: str) -> str:
    if path.startswith(_API_PATH_PREFIX):
        return path[len(_API_PATH_PREFIX):] or "/"
    return path


def allow_uri(
    user: UserModel,
    method: str,
    path: str,
    *,
    session: Session | None = None,
    group_fallback: bool = True,
) -> bool:
    if user is None:
        return False
    if actor_is_super_admin(user):
        return True
    path = _without_api_path_prefix(path)
    action = _method_to_action(method)
    if path.startswith(_NO_GROUP_FALLBACK_PREFIXES):
        group_fallback = False
    # A role's permissions can remain materialized in the database after a
    # YAML grant is removed. Keep read-only roles from inheriting stale catalog
    # write grants while the database is being reconciled.
    if action in {"create", "update", "delete"} and path.startswith("/process-models"):
        tenant_ids = current_tenant_identifiers()
        roles = {
            identifier.rsplit(":", 1)[-1]
            for group in getattr(user, "groups", []) or []
            for identifier in [getattr(group, "identifier", "") or ""]
            if ":" not in identifier or identifier.rsplit(":", 1)[0] in tenant_ids
        }
        if roles & {"viewer", "submitter"}:
            return False
    db_session = session
    if db_session is None:
        from flask import g

        db_session = getattr(g, "db_session", None)
    if db_session is None:
        return group_fallback and _group_identifier_fallback(user, path)
    if _resource_permitted(db_session, user, action, "tenant", path):
        return True
    if not group_fallback:
        return False
    return _group_identifier_fallback(user, path)


def user_has_permission(user: UserModel, permission: str, path: str, *, session: Session | None = None) -> bool:
    return allow_uri(user, permission, path, session=session)


def database_permission(user: UserModel, method: str, path: str, *, session: Session) -> bool:
    """Check only materialized RBAC assignments for a user and request.

    Unlike ``allow_uri``, this deliberately does not apply the super-admin
    shortcut, process write guard, or group-identifier fallback. It is used
    for capability responses that must reflect the permission tables exactly.
    """
    if user is None:
        return False
    return _resource_permitted(
        session,
        user,
        _method_to_action(method),
        "tenant",
        _without_api_path_prefix(path),
    )


def require_authorized_user(action: str, *, forbidden_message: str, path: str | None = None) -> UserModel:
    from flask import g, request as flask_request

    from m8flow_backend.auth import require_current_user

    user = require_current_user()
    request_path = path or flask_request.path
    session = getattr(g, "db_session", None)
    if allow_uri(user, action if action in {"GET", "POST", "PUT", "DELETE"} else "GET", request_path, session=session):
        return user
    if _group_identifier_fallback(user, request_path):
        return user
    raise ApiError("permission_denied", forbidden_message, 403)


def install_default_policy() -> None:
    api.set_default_authorization_policy_factory(lambda: HostAuthorizationPolicy())


def _verified_claims_for_request():
    from m8flow_backend.integrations.auth.base.models import VerifiedClaims

    try:
        from flask import g

        claims = getattr(g, "verified_claims", None)
    except Exception:
        return None
    return claims if isinstance(claims, VerifiedClaims) else None


def _actor_matches_verified_claims(user: UserModel) -> bool:
    claims = _verified_claims_for_request()
    if claims is None:
        return False
    if user.service_id and claims.subject and str(user.service_id) == str(claims.subject):
        return True
    return bool(user.username and claims.username and user.username == claims.username)


def _verified_claims_grant_super_admin_to(user: UserModel) -> bool:
    claims = _verified_claims_for_request()
    return claims is not None and _actor_matches_verified_claims(user) and SUPER_ADMIN_ROLE in claims.roles


def actor_is_super_admin(user: UserModel | None) -> bool:
    """The one super-admin check every caller should use: a live "super-admin"
    group membership, or (before local group sync has persisted it) a verified
    JWT role claim bound to this specific user. Formerly reimplemented ad hoc
    in home_controller, template_authorization_service, and
    tenant_management_authorization -- see architecture review finding C1.
    The zero-arg request-context wrapper is `auth.is_super_admin_request`
    (`auth/bind.py`), which delegates here."""
    if user is None:
        return False
    if any(getattr(group, "identifier", None) == SUPER_ADMIN_ROLE for group in user.groups):
        return True
    return _verified_claims_grant_super_admin_to(user)


def _actor_is_super_admin(session: Session, user_id: int) -> bool:
    return actor_is_super_admin(session.get(UserModel, user_id))


def _method_to_action(method: str) -> str:
    mapping = {
        "GET": "read",
        "HEAD": "read",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
        "read": "read",
        "create": "create",
        "update": "update",
        "delete": "delete",
        "start": "start",
        "execute": "execute",
    }
    return mapping.get(method.upper() if method.isupper() else method, "read")


def _active_tenant_groups(user: UserModel) -> list:
    """The user's groups that count in the active tenant: global ones plus that tenant's.

    A multi-org user's role in one organization must not grant anything in another.
    Without an active tenant every group still counts, as before.
    """
    groups = list(getattr(user, "groups", None) or [])
    tenant_ids = current_tenant_identifiers()
    if not tenant_ids:
        return groups

    def counts(identifier: str) -> bool:
        return ":" not in identifier or identifier.partition(":")[0] in tenant_ids

    return [group for group in groups if counts(getattr(group, "identifier", "") or "")]


def _resource_permitted(
    session: Session,
    user: UserModel,
    action: str,
    resource_type: str,
    resource_id: str,
) -> bool:
    principal_ids = [user.principal.id] if user.principal is not None else []
    group_ids = [group.id for group in _active_tenant_groups(user)]
    if group_ids:
        group_principals = session.scalars(
            select(PrincipalModel).where(PrincipalModel.group_id.in_(group_ids))
        ).all()
        principal_ids.extend(p.id for p in group_principals)
    if not principal_ids:
        return False
    assignments = (
        session.scalars(
            select(PermissionAssignmentModel)
            .options(joinedload(PermissionAssignmentModel.permission_target))
            .where(PermissionAssignmentModel.principal_id.in_(principal_ids))
        )
        .unique()
        .all()
    )
    permitted = False
    for assignment in assignments:
        target = assignment.permission_target
        if target is None:
            continue
        requested_type = str(getattr(resource_type, "value", resource_type) or "").strip()
        target_type = getattr(target.resource_type, "value", target.resource_type)
        target_type = str(target_type).strip() if target_type is not None else None
        # Before typed resource targets were introduced, route grants could
        # have a NULL resource_type while resource_id still contained the
        # route-shaped URI. Preserve those legacy tenant grants only for the
        # tenant URI authorization path. Unknown non-null types remain
        # fail-closed and concrete resource requests still require an exact
        # type match.
        legacy_tenant_target = target_type is None and requested_type == "tenant"
        if not (target_type == requested_type or legacy_tenant_target):
            continue
        if not _path_matches(str(resource_id), target.resource_id or ""):
            continue
        if assignment.permission not in {action, "all"}:
            continue
        if assignment.grant_type == "deny":
            return False
        permitted = True
    return permitted


def _path_matches(path: str, uri_pattern: str) -> bool:
    """Match a request path against a permission-target URI.

    Core only stores a trailing ``%`` wildcard (``*`` in YAML). Brace
    placeholders such as ``{tenant_id}`` are one path segment so YAML can
    grant ``/m8flow/tenants/{tenant_id}/members*`` without also granting
    registry GET ``/m8flow/tenants/{id}`` or invitation management.
    """
    if "%" not in uri_pattern and "{" not in uri_pattern:
        return path == uri_pattern or path.startswith(uri_pattern.rstrip("/") + "/")
    regex_parts: list[str] = []
    i = 0
    while i < len(uri_pattern):
        char = uri_pattern[i]
        if char == "%":
            regex_parts.append(".*")
            i += 1
            continue
        if char == "{":
            close = uri_pattern.find("}", i)
            if close == -1:
                regex_parts.append(re.escape(char))
                i += 1
                continue
            regex_parts.append("[^/]+")
            i = close + 1
            continue
        regex_parts.append(re.escape(char))
        i += 1
    return re.fullmatch("".join(regex_parts), path) is not None


def _group_identifier_fallback(user: UserModel, path: str) -> bool:
    """Load-bearing for just-logged-in multi-org users before YAML grants persist."""
    identifiers = [getattr(group, "identifier", "") or "" for group in _active_tenant_groups(user)]
    if any(item == SUPER_ADMIN_ROLE or item.endswith(":tenant-admin") or item.endswith(":editor") for item in identifiers):
        return True
    if "/onboarding" in path or path.endswith("/tasks") or "/tasks" in path:
        if any(item.endswith(":reviewer") or item.endswith(":editor") or item.endswith(":user") for item in identifiers):
            return True
    return False
