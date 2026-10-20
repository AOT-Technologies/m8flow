"""Public interface of the active-tenant deep module: token encode/decode,
session finalization, request authentication, and re-exports of the
request-binding helpers (bind.py) that most external callers reach for.

Internals: tenant_context.py (leaf ContextVar/constants), canonicalize.py
(DB-backed tenant-identifier resolution), claims.py (pure JWT claim
parsing), identity_helpers.py (shared-realm provisioning + group-identifier
utilities), resolve.py (pure active-tenant SELECTION core), ports.py /
adapters.py (the Directory/TenantRepo seam), bind.py (request-time BINDING:
RLS, ContextVar lifecycle, super-admin/tenant-required checks).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import jwt
from flask import Flask, g, request
from sqlalchemy import select
from sqlalchemy.orm import Session

from m8flow_bpmn_core.models.user import UserModel
from m8flow_backend.errors import ApiError
from m8flow_backend.integrations.auth.base.models import IssuerRef, Membership, VerifiedClaims
from m8flow_backend.auth.tenant_context import (
    SELECTED_TENANT_COOKIE_NAME,
    get_context_tenant_id,
)
from m8flow_backend.auth.bind import (  # noqa: F401 -- re-exported public surface
    apply_postgres_rls,
    apply_postgres_rls_to_request_session,
    bind_request_tenant,
    install_postgres_rls_hook,
    install_tenant_runtime,
    is_public_request,
    is_super_admin_request,
    is_tenant_context_exempt_request,
    mark_tenant_exempt,
    path_matches_any_prefix,
    path_matches_prefix,
    require_catalog_write_tenant_id,
    require_tenant_id,
    resolve_read_tenant_id,
    resolve_request_tenant,
    TENANT_CONTEXT_EXEMPT_PATH_PREFIXES,
)

from m8flow_backend.startup.env_var_mapper import is_unit_testing_environment
from m8flow_backend.routes.session_cookies import clear_session_cookie, set_session_cookie

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"

_TEST_ONLY_JWT_SECRET = "unit-test-secret-key-32bytes-min"


def jwt_secret() -> str:
    configured = (os.environ.get("FLASK_SESSION_SECRET_KEY") or "").strip()
    if configured:
        return configured
    if is_unit_testing_environment():
        return _TEST_ONLY_JWT_SECRET
    raise RuntimeError(
        "FLASK_SESSION_SECRET_KEY must be set outside unit-testing environments."
    )


def encode_auth_token(*, user: UserModel, extra: dict[str, Any] | None = None) -> str:
    payload = {
        "sub": f"service:{user.service}::service_id:{user.service_id}",
        "preferred_username": user.username,
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400,
        "iss": user.service,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_auth_token(token: str, maybe_token: str | None = None, **_kwargs) -> dict[str, Any]:
    actual = maybe_token if maybe_token is not None else token
    try:
        header = jwt.get_unverified_header(actual)
    except jwt.PyJWTError as exc:
        raise jwt.InvalidTokenError("malformed token") from exc
    alg = header.get("alg")
    if alg == JWT_ALGORITHM:
        payload = jwt.decode(actual, jwt_secret(), algorithms=[JWT_ALGORITHM])
        _store_verified_payload(payload, verified_claims=None)
        return payload
    from m8flow_backend.integrations.auth import get_auth_provider
    from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, TokenInvalid

    try:
        claims = get_auth_provider().verify_token(actual)
    except (TokenInvalid, ProviderUnavailable) as exc:
        raise jwt.InvalidTokenError(str(exc)) from exc
    payload = claims.jwt_claims
    if not isinstance(payload, dict):
        raise jwt.InvalidTokenError("verified token had no payload")
    _store_verified_payload(payload, verified_claims=claims)
    return payload


def _store_verified_payload(payload: dict[str, Any], *, verified_claims) -> None:
    from flask import has_request_context

    if not has_request_context():
        return
    g.decoded_token = payload
    if verified_claims is not None:
        g.verified_claims = verified_claims


def clear_dead_auth_realm_cookie(response) -> None:
    clear_session_cookie(response, "m8flow_auth_realm")


def set_selected_tenant_cookie(response, tenant_id: str) -> None:
    set_session_cookie(response, SELECTED_TENANT_COOKIE_NAME, tenant_id, max_age=86400 * 30)


_FINALIZATION_TRUTHY = frozenset({"1", "true", "yes"})


def try_finalize_shared_realm_session(redirect_url: str):
    """Finalize an already-authenticated shared-realm session onto one tenant.

    When ``tenant`` + ``tenant_finalization`` are present and the browser still
    has a shared-realm access/id token, set ``m8flow_selected_tenant``, enrich
    the active organization's groups from the auth provider (the token listing
    orgs is not enough), sync local groups, and redirect to ``redirect_url``
    without a second Keycloak round-trip.

    Returns ``None`` to fall through to ordinary OIDC login when the session
    cannot be parsed or has no organization memberships.
    """
    from flask import g, redirect, request

    flag = str(request.args.get("tenant_finalization") or "").strip().lower()
    if flag not in _FINALIZATION_TRUTHY:
        return None
    tenant_alias = (request.args.get("tenant") or "").strip()
    if not tenant_alias:
        return None

    identifier = (
        (request.args.get("authentication_identifier") or "").strip()
        or (request.cookies.get("authentication_identifier") or "").strip()
    )
    from m8flow_backend.integrations.auth import get_auth_provider
    from m8flow_backend.integrations.auth.base.models import IssuerRef

    if IssuerRef(value=identifier) != get_auth_provider().default_issuer():
        return None

    session_token = request.cookies.get("access_token") or request.cookies.get("id_token")
    if not session_token:
        return None

    try:
        decoded = decode_auth_token(session_token)
    except jwt.PyJWTError:
        logger.warning(
            "tenant_finalization: unable to parse existing shared-realm session; falling back to standard login"
        )
        return None

    claims = getattr(g, "verified_claims", None)
    if not isinstance(claims, VerifiedClaims):
        # decode_auth_token's Keycloak/OIDC branch already populates
        # g.verified_claims as a side effect (see _store_verified_payload) --
        # this is a defensive fallback for the rare case it didn't. Re-verify
        # session_token through the port (never a direct adapter import,
        # auth-provider-seam wayfinder map ticket 10) rather than hand-
        # mapping the already-decoded payload; session_token is the exact
        # token decode_auth_token just verified above, so this is a repeat
        # of the same cryptographic check, not new trust.
        from m8flow_backend.integrations.auth import get_auth_provider
        from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable, TokenInvalid

        try:
            claims = get_auth_provider().verify_token(session_token)
        except (TokenInvalid, ProviderUnavailable):
            logger.warning(
                "tenant_finalization: unable to parse existing shared-realm session; falling back to standard login"
            )
            return None
        g.verified_claims = claims

    from m8flow_backend.services.tenant_service import TenantService

    tenant_info = TenantService.check_tenant_exists(tenant_alias)
    if not tenant_info.get("exists"):
        raise ApiError("tenant_not_found", "Tenant not found", 404)
    selected_tenant_id = str(tenant_info["tenant_id"])

    directory_memberships = _directory_memberships_for_username(
        claims.username
        or (decoded.get("preferred_username") if isinstance(decoded.get("preferred_username"), str) else None)
    )
    memberships = directory_memberships or list(claims.memberships)
    if not memberships:
        logger.warning(
            "tenant_finalization: shared-realm session lacked organization memberships; falling back to standard login"
        )
        return None

    if directory_memberships:
        g.verified_claims = VerifiedClaims(
            subject=claims.subject,
            issuer=claims.issuer,
            username=claims.username,
            email=claims.email,
            roles=claims.roles,
            memberships=directory_memberships,
            jwt_claims=claims.jwt_claims,
        )

    from m8flow_backend.auth import resolve as _resolve
    from m8flow_backend.auth.canonicalize import DbTenantRepo

    tenant_repo = DbTenantRepo()
    token_membership = _resolve.membership_for_active_tenant(
        memberships, tenant_alias, tenant_repo=tenant_repo
    ) or _resolve.membership_for_active_tenant(memberships, selected_tenant_id, tenant_repo=tenant_repo)
    if token_membership is None:
        raise ApiError(
            "tenant_not_available",
            "Selected tenant is not available for this session",
            403,
        )

    session: Session = g.db_session
    username = claims.username or str(decoded.get("preferred_username") or claims.subject)
    from sqlalchemy.exc import IntegrityError

    try:
        user = on_login_or_token_enrichment(
            session,
            username=str(username),
            service=claims.issuer,
            service_id=claims.subject,
            email=claims.email if isinstance(claims.email, str) else None,
            active_tenant_id=selected_tenant_id,
        )
    except IntegrityError:
        session.rollback()
        user = session.scalars(
            select(UserModel).where(
                UserModel.service == claims.issuer,
                UserModel.service_id == claims.subject,
            )
        ).first()
        if user is None:
            logger.warning(
                "tenant_finalization: user provisioning raced and could not be recovered; falling back to standard login"
            )
            return None

    sync_groups_from_token(
        session,
        user=user,
        decoded=decoded,
        tenant_id=selected_tenant_id,
    )
    session.flush()

    # Option D (map ticket 08/10): make the Keycloak-minted token carry the
    # target org's claims. Record the active org on the user (RealmInfoMapper
    # reads m8flow_active_tenant), then re-mint via a plain refresh_token grant
    # -- Keycloak re-runs the mapper against the freshly-written attribute
    # (verified: no user-cache staleness). Silent, no org-scope, no re-login.
    remint = _remint_active_tenant_token(
        username=str(username),
        identifier=identifier,
        tenant_id=selected_tenant_id,
    )

    from m8flow_backend.routes.session_cookies import set_token_cookies, token_set_as_dict
    from m8flow_backend.routes.safe_redirect import safe_redirect_or_fallback

    response = redirect(safe_redirect_or_fallback(redirect_url))
    if remint is not None:
        # New token set carries m8flow_tenant_* + organization.{alias} for the
        # selected org; refresh rotation replaces the prior refresh token.
        set_token_cookies(response, token_set_as_dict(remint), identifier=identifier)
    # Cookie stays authoritative regardless of the re-mint outcome.
    set_selected_tenant_cookie(response, selected_tenant_id)
    return response


def _remint_active_tenant_token(*, username: str, identifier: str, tenant_id: str):
    """Make the session token carry the target tenant's claims. Returns the new
    ``TokenSet`` or ``None``.

    The flow itself (write active tenant, refresh; degrade gracefully) lives
    in ``integrations.auth.core.AuthService.switch_tenant`` and follows the
    provider's declared ``switch_mode``. Failure is non-fatal and leaves
    session cookies untouched: the ``m8flow_selected_tenant`` cookie is
    authoritative for active-tenant resolution.
    """
    from flask import request

    from m8flow_backend.integrations.auth import get_auth_provider
    from m8flow_backend.integrations.auth.base.errors import CapabilityNotSupported
    from m8flow_backend.integrations.auth.core import AuthService

    try:
        outcome = AuthService(get_auth_provider()).switch_tenant(
            username=username,
            tenant_id=tenant_id,
            refresh_token=request.cookies.get("refresh_token"),
            issuer=IssuerRef(value=identifier),
        )
    except CapabilityNotSupported:
        # A switch mode the host has not wired yet: fall back to cookie-only.
        logger.warning("tenant switch: provider switch mode not wired; cookie-only switch for %s", username)
        return None
    return outcome.tokens


def _directory_memberships_for_username(username: str | None) -> list[Membership]:
    from m8flow_backend.integrations.auth import get_auth_provider
    from m8flow_backend.integrations.auth.core import AuthService

    return AuthService(get_auth_provider()).directory_memberships_best_effort(username)


def on_login_or_token_enrichment(
    session: Session,
    *,
    username: str,
    service: str,
    service_id: str,
    email: str | None,
    active_tenant_id: str,
) -> UserModel:
    from m8flow_backend import identity

    user = identity.ensure_user(
        session,
        username=username,
        service=service,
        service_id=service_id,
        email=email,
    )
    tenant = identity.ensure_tenant(session, tenant_id=active_tenant_id)
    identity.ensure_membership(session, user, tenant)
    return user


def user_from_internal_token(session: Session, decoded: dict[str, Any]) -> UserModel | None:
    subject = decoded.get("sub")
    if not isinstance(subject, str) or "::" not in subject:
        return None
    service_part, service_id_part = subject.split("::", 1)
    if not service_part.startswith("service:") or not service_id_part.startswith("service_id:"):
        return None
    service = service_part.removeprefix("service:").strip()
    service_id = service_id_part.removeprefix("service_id:").strip()
    return session.scalars(
        select(UserModel).where(UserModel.service == service, UserModel.service_id == service_id)
    ).first()


def require_current_user() -> UserModel:
    user = getattr(g, "user", None)
    if user is None:
        raise ApiError("not_authenticated", "User not authenticated", 401)
    return user


def install_auth_middleware(app: Flask) -> None:
    @app.before_request
    def _authenticate() -> None:
        header = request.headers.get("Authorization") or ""
        token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else None
        if not token:
            token = request.cookies.get("access_token")
        # Tenant-exempt prefixes skip tenant-cookie resolution, not authentication.
        # A present Bearer/cookie must still set g.user so /tenants/{id}/members
        # and invitations work. Truly public callers (no token) stay anonymous.
        if not token:
            return

        session: Session = g.db_session
        try:
            decoded = decode_auth_token(token)
        except jwt.PyJWTError:
            return
        user = user_from_internal_token(session, decoded)
        if user is None:
            from sqlalchemy.exc import IntegrityError

            from m8flow_backend.integrations.auth import get_auth_provider

            # Typed VerifiedClaims is the contract (auth-provider-seam
            # wayfinder map, ticket 10): decode_auth_token's Keycloak/OIDC
            # branch always populates g.verified_claims, so a raw payload
            # read is only ever needed for the HS256 local-token branch,
            # which builds no VerifiedClaims -- decoded stays the fallback
            # source for that case only, never the primary one.
            claims = getattr(g, "verified_claims", None)
            if isinstance(claims, VerifiedClaims):
                username = str(claims.username or claims.subject or "unknown")
                service = str(claims.issuer or "local")
                service_id = str(claims.subject or username)
                email = claims.email
            else:
                username = str(decoded.get("preferred_username") or decoded.get("sub") or "unknown")
                service = str(decoded.get("iss") or "local")
                service_id = str(decoded.get("sub") or username)
                email = decoded.get("email") if isinstance(decoded.get("email"), str) else None
            tenant_id = (
                request.cookies.get(SELECTED_TENANT_COOKIE_NAME)
                or get_context_tenant_id()
                or get_auth_provider().default_tenant_ref().alias
            )
            try:
                user = on_login_or_token_enrichment(
                    session,
                    username=username,
                    service=service,
                    service_id=service_id,
                    email=email,
                    active_tenant_id=str(tenant_id),
                )
            except IntegrityError:
                # Concurrent first-hit enrichment (e.g. React StrictMode double
                # fetch) can race on the unique (service, service_id) key.
                session.rollback()
                user = session.scalars(
                    select(UserModel).where(
                        UserModel.service == service,
                        UserModel.service_id == service_id,
                    )
                ).first()
                if user is None:
                    return
            sync_groups_from_token(session, user=user, decoded=decoded, tenant_id=str(tenant_id))
        else:
            from m8flow_backend.integrations.auth import get_auth_provider

            sync_groups_from_token(
                session,
                user=user,
                decoded=decoded,
                tenant_id=str(
                    request.cookies.get(SELECTED_TENANT_COOKIE_NAME)
                    or get_context_tenant_id()
                    or get_auth_provider().default_tenant_ref().alias
                ),
            )
        g.user = user
        g.decoded_token = decoded
        # The exact token g.user was authenticated with, for anything that must act as
        # this caller downstream (e.g. the MCP Tools proxy) without re-deriving it.
        g.token = token


def sync_groups_from_token(
    session: Session,
    *,
    user: UserModel,
    decoded: dict[str, Any],
    tenant_id: str,
) -> None:
    """Persist verified neutral roles onto the local user (esp. master super-admin).

    Delegates the active-tenant SELECTION (membership match, thin-token
    enrichment, canonicalization, group-identifier computation) to the pure
    ``resolve.select(...)`` core; this function owns only the write (identity
    sync + YAML seed guard), matching resolve.py's ports/adapter design.
    """
    del decoded  # RBAC/sync reads VerifiedClaims, not raw JWT JSON.
    from m8flow_backend import identity
    from m8flow_backend.auth import resolve as _resolve
    from m8flow_backend.auth.adapters import ProviderDirectory
    from m8flow_backend.auth.canonicalize import DbTenantRepo

    claims = getattr(g, "verified_claims", None)
    if not isinstance(claims, VerifiedClaims):
        return

    active = _resolve.select(
        memberships=claims.memberships,
        roles=frozenset(claims.roles),
        tenant_id=tenant_id,
        username=claims.username or getattr(user, "username", None),
        directory=ProviderDirectory(issuer=claims.issuer),
        tenant_repo=DbTenantRepo(),
        require_lane_groups=True,
    )

    if not active.group_identifiers and not active.lane_group_identifiers:
        return
    identity.sync_groups(
        session,
        user=user,
        group_identifiers=active.group_identifiers,
        tenant_id=str(active.tenant_id),
    )
    identity.sync_lane_groups(
        session,
        user=user,
        tenant_id=str(active.tenant_id),
        lane_group_identifiers=active.lane_group_identifiers,
    )
    # sync_groups only creates the UserGroupAssignmentModel row; it never seeds
    # the tenant-qualified group's actual m8flow.yml permissions into the DB.
    # Without this, allow_uri's real DB-grant check (_uri_permitted) has
    # nothing to find for a freshly-synced tenant role and silently falls
    # through to _group_identifier_fallback on every request. Skip once the
    # tenant already has the current seed-version marker; re-importing on every
    # Home GET was ~500 SQL statements and contended UPDATEs on permission_assignment.
    if active.group_identifiers:
        active_tenant_id = str(active.tenant_id)
        if not identity.tenant_permission_seed_current(session, tenant_id=active_tenant_id):
            try:
                identity.import_yaml(session, tenant_id=active_tenant_id)
            except Exception as exc:
                logger.exception(
                    "Lifecycle permission seeding failed for tenant %s",
                    active_tenant_id,
                )
                raise ApiError(
                    "lifecycle_permissions_unavailable",
                    "Tenant authorization is not ready; lifecycle permissions could not be seeded.",
                    503,
                ) from exc
        lifecycle_roles = {
            f"{active_tenant_id}:editor",
            f"{active_tenant_id}:tenant-admin",
        }
        if lifecycle_roles.intersection(active.group_identifiers):
            missing_lifecycle_grants = identity.missing_lifecycle_execute_grants(
                session, tenant_id=active_tenant_id
            )
            if missing_lifecycle_grants:
                missing = ", ".join(missing_lifecycle_grants)
                raise ApiError(
                    "lifecycle_permissions_unavailable",
                    f"Tenant authorization is not ready; missing lifecycle execute grants: {missing}",
                    503,
                )
    # Reconcile on every sync, not only when membership changed: core resolves
    # lane owners once, when the task materializes, and skips members it can't
    # place in the tenant then (e.g. a multi-org user whose active org was
    # another tenant). Their membership doesn't change when they return, so a
    # change-gated reconcile would orphan the task for good (M8F-580). The core
    # call is idempotent and only adds potential-owner rows, never claims.
    # ponytail: ~2 SELECTs + savepoint per authenticated request; if it shows in
    # profiles, cache a per-(user, tenant) "nothing to reconcile" result for N
    # seconds. Don't gate on "task has no owners": partially assigned lanes must heal too.
    from m8flow_backend import workflow

    try:
        # Reconciliation is best-effort. Keep it in a savepoint so a
        # transient task-assignment failure cannot abort authentication or
        # roll back the group synchronization performed above.
        with session.begin_nested():
            workflow.reconcile_pending_tasks_for_user(
                session,
                tenant_id=str(active.tenant_id),
                user_id=user.id,
            )
    except Exception:
        logger.warning(
            "Pending-task reconciliation failed for user %s in tenant %s",
            user.id,
            active.tenant_id,
            exc_info=True,
        )
    session.flush()
    try:
        session.expire(user, ["groups"])
    except Exception:
        # Best-effort cache invalidation only; group membership was already
        # persisted above, so a stale in-memory `user.groups` is a minor
        # inconsistency for this request, not a failed sync.
        logger.debug("Failed to expire cached user.groups after group sync", exc_info=True)
