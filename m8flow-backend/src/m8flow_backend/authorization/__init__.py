from __future__ import annotations

import logging
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
LOGGER = logging.getLogger(__name__)


def _host_yaml_decision(
    session: Session,
    user: UserModel,
    *,
    permission: str,
    resource_type: str,
    resource_id: object,
    path_prefix: str | None = None,
    command: str | None = None,
    allow_legacy_commandless: bool = False,
) -> api.AuthorizationDecision | None:
    """Translate a core resource into the route-shaped host YAML grant.

    Core commands use typed resource pairs, while the host policy intentionally
    grants some operations against route-shaped tenant targets. Keeping the
    translation here makes the security-boundary rules explicit and prevents
    command branches from drifting apart.
    """
    translated_id = _normalize_route_resource_id(resource_id, path_prefix)
    if _resource_permitted(
        session,
        user,
        permission,
        resource_type,
        translated_id,
        command=command,
        allow_legacy_commandless=allow_legacy_commandless,
    ):
        return api.AuthorizationDecision(allowed=True, reason="host_yaml")
    return None


def _normalize_route_resource_id(resource_id: object, path_prefix: str | None) -> str:
    """Translate a typed core identifier into the host YAML route shape.

    Core normally supplies an integer or UUID for ``resource_id``. During
    rolling upgrades, callers may instead provide an already formatted route,
    a route without its leading slash, or the full ``/v1.0`` API path. Accept
    those equivalent representations without changing direct typed-resource
    matching or broadening the route prefix beyond the caller's explicit
    ``path_prefix``.
    """
    translated_id = str(resource_id).strip()
    if path_prefix is None:
        return translated_id

    normalized_prefix = path_prefix if path_prefix.startswith("/") else f"/{path_prefix}"
    if not normalized_prefix.endswith("/"):
        normalized_prefix += "/"
    translated_id = _without_api_path_prefix(translated_id)
    prefix_without_leading_slash = normalized_prefix.lstrip("/")
    if translated_id.startswith(prefix_without_leading_slash):
        translated_id = f"/{translated_id}"
    if not translated_id.startswith(normalized_prefix):
        translated_id = f"{normalized_prefix}{translated_id.lstrip('/')}"
    return translated_id


class HostAuthorizationPolicy:
    def authorize(self, session: Session, request: api.AuthorizationRequest) -> api.AuthorizationDecision:
        if _actor_is_super_admin(session, request.actor_user_id):
            return api.AuthorizationDecision(allowed=True, reason=SUPER_ADMIN_ROLE)
        user = session.get(UserModel, request.actor_user_id)
        if user is None:
            return api.DatabaseAuthorizationPolicy().authorize(session, request)
        if request.command_key == "process_definition.import":
            decision = _host_yaml_decision(
                session,
                user,
                permission="create",
                resource_type="process_definition",
                resource_id=request.resource_id,
            )
            if decision is not None:
                return decision
        if request.command_key == _PROCESS_START_COMMAND:
            # Core authorizes this command against a concrete process_model
            # resource, while host YAML grants start at /process-models/%.
            decision = _host_yaml_decision(
                session,
                user,
                permission="start",
                resource_type="tenant",
                resource_id=request.resource_id,
                path_prefix="/process-models/",
            )
            if decision is not None:
                return decision
            # Before command-aware target identity, the host's start grant was
            # sometimes stored as a commandless tenant route. Keep this
            # narrowly scoped fallback while existing tenants are reseeded:
            # only process-start's `start` action and process-model route can
            # use it, never an arbitrary commandless target.
            legacy_decision = _host_yaml_decision(
                session,
                user,
                permission="start",
                resource_type="tenant",
                resource_id=request.resource_id,
                path_prefix="/process-models/",
                command=_PROCESS_START_COMMAND,
                allow_legacy_commandless=True,
            )
            if legacy_decision is not None:
                return api.AuthorizationDecision(allowed=True, reason="host_yaml_legacy")
        if request.command_key in _TASK_COMMAND_KEYS:
            # Core authorizes task commands against a concrete task resource,
            # while host YAML grants task work at /tasks/*.
            permission = str(getattr(request.permission, "value", request.permission))
            decision = _host_yaml_decision(
                session,
                user,
                permission=permission,
                resource_type="tenant",
                resource_id=request.resource_id,
                path_prefix="/tasks/",
            )
            if decision is not None:
                return decision
        if request.command_key in _LIFECYCLE_COMMAND_KEYS:
            resource_type = str(getattr(request.resource_type, "value", request.resource_type))
            permission = str(getattr(request.permission, "value", request.permission))
            if permission != "execute":
                return api.AuthorizationDecision(allowed=False, reason="lifecycle_requires_execute")
            direct_decision = _host_yaml_decision(
                session,
                user,
                permission=permission,
                resource_type=resource_type,
                resource_id=request.resource_id,
                command=request.command_key,
            )
            if direct_decision is not None:
                return direct_decision
            # Host YAML grants lifecycle operations on route-shaped instance
            # paths, while core authorizes against an explicit process-instance
            # resource pair.
            route_decision = _host_yaml_decision(
                session,
                user,
                permission=permission,
                resource_type="tenant",
                resource_id=request.resource_id,
                path_prefix="/process-instances/",
                command=request.command_key,
            )
            if route_decision is not None:
                return route_decision
            legacy_direct = _host_yaml_decision(
                session,
                user,
                permission="create",
                resource_type=resource_type,
                resource_id=request.resource_id,
                command=request.command_key,
            )
            legacy_route = _host_yaml_decision(
                session,
                user,
                permission="create",
                resource_type="tenant",
                resource_id=request.resource_id,
                path_prefix="/process-instances/",
                command=request.command_key,
            )
            if legacy_direct is not None or legacy_route is not None:
                return api.AuthorizationDecision(
                    allowed=False,
                    reason="lifecycle_permissions_migration_required",
                )
        default = api.DatabaseAuthorizationPolicy()
        return default.authorize(session, request)


# Paths whose routes gate with ``group_fallback=False`` as policy, not per call site:
# secrets have explicit role grants; NATS monitoring is split by endpoint, NATS API
# keys are tenant-admin only, and MCP Tools runs arbitrary tools as the caller. The
# tenant-admin/editor group fallback would re-open these to every tenant role.
# Applied inside ``allow_uri`` so permission checks agree with route authorization.
_NO_GROUP_FALLBACK_PREFIXES = (
    "/secrets",
    "/m8flow/connector-profiles",
    "/m8flow/nats/",
    "/m8flow/nats-tokens",
    "/m8flow/task-review-access",
    "/m8flow/mcp-tools",
    "/m8flow/tenant-management",
)


def _without_api_path_prefix(path: str) -> str:
    if path.startswith(_API_PATH_PREFIX):
        return path[len(_API_PATH_PREFIX):] or "/"
    return path


def _normalize_authorization_path(path: str) -> str:
    """Normalize API prefixes and public Task Review paths to RBAC targets.

    The Task Review alias is prefix-based so concrete IDs and permission-check
    placeholders use the same target. Trailing slashes are ignored on both
    public and canonical Task Review paths.
    """
    path = _without_api_path_prefix(path)
    public_prefix = "/m8flow/task-review"
    target_prefix = "/m8flow/task-review-access"
    normalized = path.rstrip("/") or "/"
    if normalized == public_prefix or normalized.startswith(public_prefix + "/"):
        return target_prefix + normalized[len(public_prefix):]
    if normalized == target_prefix or normalized.startswith(target_prefix + "/"):
        return normalized
    return normalized


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
    path = _normalize_authorization_path(path)
    # Home's personal task panel is intentionally opt-in by an explicit
    # tenant grant. Do not let the global super-admin shortcut (or group
    # fallback) expose an individual task queue on Home.
    if path == "/m8flow/home-task-count":
        db_session = session
        if db_session is None:
            from flask import g, has_app_context

            if has_app_context():
                db_session = getattr(g, "db_session", None)
        if db_session is None:
            # This permission is grant-backed and deliberately has no role
            # fallback. Outside a request, there is no DB grant context to
            # consult, so fail closed without touching Flask's LocalProxy.
            LOGGER.warning(
                "Failing closed for %s %s permission check: no database session is available",
                method,
                path,
            )
            return False
        return _resource_permitted(
            db_session, user, _method_to_action(method), "tenant", path
        )
    action = _method_to_action(method)
    task_review_segments = path.strip("/").split("/")
    if (
        action == "create"
        and len(task_review_segments) == 4
        and task_review_segments[:2] == ["m8flow", "task-review-access"]
        and task_review_segments[2]
        and task_review_segments[3] == "submit"
        and actor_is_super_admin(user)
    ):
        # Super-admins may inspect Task Review across tenants, but submission
        # is a reviewer/tenant role action. Keep permissions-check and route
        # authorization aligned instead of applying the global shortcut here.
        return False
    if actor_is_super_admin(user):
        return True
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


def user_has_permission(
    user: UserModel,
    permission: str,
    path: str,
    *,
    session: Session | None = None,
    group_fallback: bool = True,
) -> bool:
    return allow_uri(user, permission, path, session=session, group_fallback=group_fallback)


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
    command: str | None = None,
    allow_legacy_commandless: bool = False,
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
        if command is not None and target.command != command and not (
            allow_legacy_commandless and target.command is None
        ):
            continue
        requested_type = str(getattr(resource_type, "value", resource_type) or "").strip()
        target_type = getattr(target.resource_type, "value", target.resource_type)
        target_type = str(target_type).strip() if target_type is not None else None
        target_resource_id = target.resource_id
        legacy_uri = getattr(target, "uri", None)
        target_command = getattr(target, "command", None)
        legacy_tenant_target = (
            target_type is None
            and requested_type == "tenant"
            and target_resource_id is None
            and bool(str(legacy_uri or "").strip())
            and bool(str(target_command or "").strip())
        )
        # Null-type targets are ambiguous unless they carry the complete
        # pre-typed legacy shape. Do not let malformed rows become wildcard
        # tenant grants through the path matcher.
        if target_type is None and not legacy_tenant_target:
            LOGGER.warning(
                "Skipping ambiguous permission target id=%s with null resource_type",
                getattr(target, "id", None),
            )
        if not (target_type == requested_type or legacy_tenant_target):
            continue
        if legacy_tenant_target:
            # A partially migrated legacy target may still expose its route in
            # ``uri`` even though the typed resource_id was not populated.
            # Keep this fallback tenant-scoped only; concrete resource
            # requests must never authorize from a legacy URI field.
            target_resource_id = legacy_uri
        # Before typed resource targets, host tenant URI grants used implicit
        # prefix matching. Preserve that behavior only for path-shaped tenant
        # targets; process_instance/process_definition IDs remain exact unless
        # the target explicitly contains a wildcard or placeholder.
        legacy_tenant_route = (
            (legacy_tenant_target or target_type == requested_type == "tenant")
            and str(target_resource_id or "").startswith("/")
        )
        if not _path_matches(
            str(resource_id), target_resource_id or "", legacy_prefix=legacy_tenant_route
        ):
            continue
        if assignment.permission not in {action, "all"}:
            continue
        if assignment.grant_type == "deny":
            return False
        permitted = True
    return permitted


def _path_matches(path: str, uri_pattern: str, *, legacy_prefix: bool = False) -> bool:
    """Match a request path against a permission-target URI.

    Permission targets may contain the SQL-style ``%`` wildcard or the
    YAML-style ``*`` wildcard. The identity importer normally canonicalizes
    ``*`` to ``%``, but accepting both keeps authorization compatible with
    rows seeded by older core versions or written by another importer. Brace
    placeholders such as ``{tenant_id}`` are one path segment so YAML can
    grant ``/m8flow/tenants/{tenant_id}/members*`` without also granting
    registry GET ``/m8flow/tenants/{id}`` or invitation management.
    """
    if "%" not in uri_pattern and "*" not in uri_pattern and "{" not in uri_pattern:
        if legacy_prefix:
            normalized_pattern = uri_pattern.rstrip("/")
            return path == uri_pattern or path.startswith(f"{normalized_pattern}/")
        return path == uri_pattern
    regex_parts: list[str] = []
    i = 0
    while i < len(uri_pattern):
        char = uri_pattern[i]
        if char == "%":
            regex_parts.append(".*")
            i += 1
            continue
        if char == "*":
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
