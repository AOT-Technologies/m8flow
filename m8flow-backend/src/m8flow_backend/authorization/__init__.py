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

# m8flow.yml's permission uris are written without this prefix (`/tasks`, not
# `/v1.0/tasks`); every real caller passes the actual route path, prefix and
# all. Without stripping it here, _uri_permitted's DB-backed grant check can
# never match any real request -- see architecture review finding C5.
_API_PATH_PREFIX = "/v1.0"


# Core's V1 "admin" role is the only built-in grant for these writes.
# Host YAML grants the same actions to tenant-admin / editor via create on
# /process-instances/* (process.suspend / resume / terminate). Honor that
# URI grant so execute_command does not 403 an editor who already passed
# the route's allow_uri check.
_LIFECYCLE_COMMAND_KEYS = frozenset(
    {"process.suspend", "process.resume", "process.terminate"}
)


class HostAuthorizationPolicy:
    def authorize(self, session: Session, request: api.AuthorizationRequest) -> api.AuthorizationDecision:
        if _actor_is_super_admin(session, request.actor_user_id):
            return api.AuthorizationDecision(allowed=True, reason=SUPER_ADMIN_ROLE)
        if request.command_key in _LIFECYCLE_COMMAND_KEYS:
            user = session.get(UserModel, request.actor_user_id)
            target = request.target_uri or ""
            path = target if target.startswith(_API_PATH_PREFIX) else f"{_API_PATH_PREFIX}{target}"
            if user is not None and allow_uri(user, "POST", path, session=session):
                return api.AuthorizationDecision(allowed=True, reason="host_yaml")
        default = api.DatabaseAuthorizationPolicy()
        return default.authorize(session, request)


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
    db_session = session
    if db_session is None:
        from flask import g

        db_session = getattr(g, "db_session", None)
    if db_session is None:
        return group_fallback and _group_identifier_fallback(user, path)
    if _uri_permitted(db_session, user, action, path):
        return True
    if not group_fallback:
        return False
    return _group_identifier_fallback(user, path)


def user_has_permission(user: UserModel, permission: str, path: str, *, session: Session | None = None) -> bool:
    return allow_uri(user, permission, path, session=session)


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
    }
    return mapping.get(method.upper() if method.isupper() else method, "read")


def _uri_permitted(session: Session, user: UserModel, action: str, path: str) -> bool:
    principal_ids = [user.principal.id] if user.principal is not None else []
    group_ids = [group.id for group in user.groups]
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
        if not _path_matches(path, target.uri):
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
    identifiers = [getattr(group, "identifier", "") or "" for group in getattr(user, "groups", [])]
    if any(item == SUPER_ADMIN_ROLE or item.endswith(":tenant-admin") or item.endswith(":editor") for item in identifiers):
        return True
    if "/onboarding" in path or path.endswith("/tasks") or "/tasks" in path:
        if any(item.endswith(":reviewer") or item.endswith(":editor") or item.endswith(":user") for item in identifiers):
            return True
    return False
