"""Tenant user invitation lifecycle.

A Super Admin invites a person by email + roles; the system stores a PENDING invitation
with a hashed, time-bound, single-use token and emails an accept link. The Keycloak
account is created lazily, only when the invitee accepts and sets a password.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from typing import Any

from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.models.db import db

from m8flow_backend.config import app_frontend_base_url
from m8flow_backend.config import shared_realm_name
from m8flow_backend.models.tenant_invitation import M8flowTenantInvitationModel
from m8flow_backend.models.tenant_invitation import TenantInvitationStatus
from m8flow_backend.services.email_service import send_email
from m8flow_backend.services.email_service import smtp_is_configured
from m8flow_backend.services.keycloak_service import create_user_in_realm
from m8flow_backend.services.keycloak_service import get_realm_user_by_username
from m8flow_backend.services.tenant_group_mapping import normalize_tenant_role_names
from m8flow_backend.services.tenant_group_mapping import (
    primary_organization_group_name_for_tenant_role,
)
from m8flow_backend.services.tenant_role_service import add_tenant_member
from m8flow_backend.services.tenant_service import TenantService
from m8flow_backend.tenancy import reset_context_tenant_id
from m8flow_backend.tenancy import set_context_tenant_id

logger = logging.getLogger(__name__)

DEFAULT_VALIDITY_DAYS = 7
MAX_VALIDITY_DAYS = 30
MIN_PASSWORD_LENGTH = 8
_SECONDS_PER_DAY = 24 * 60 * 60


def _now_seconds() -> int:
    return int(time.time())


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _normalized_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def _validity_days(validity_days: int | None) -> int:
    try:
        days = int(validity_days) if validity_days is not None else DEFAULT_VALIDITY_DAYS
    except (TypeError, ValueError):
        days = DEFAULT_VALIDITY_DAYS
    return max(1, min(days, MAX_VALIDITY_DAYS))


def _accept_url(raw_token: str) -> str:
    return f"{app_frontend_base_url()}/accept-invitation?token={raw_token}"


def _is_expired(invitation: M8flowTenantInvitationModel) -> bool:
    return invitation.expires_at_in_seconds <= _now_seconds()


def _maybe_expire(invitation: M8flowTenantInvitationModel) -> M8flowTenantInvitationModel:
    """Lazily flip a PENDING-but-past-expiry invitation to EXPIRED."""
    if invitation.status == TenantInvitationStatus.PENDING and _is_expired(invitation):
        invitation.status = TenantInvitationStatus.EXPIRED
        db.session.add(invitation)
        db.session.commit()
    return invitation


def _serialize(invitation: M8flowTenantInvitationModel, *, include_link: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": invitation.id,
        "tenant_id": invitation.m8f_tenant_id,
        "email": invitation.email,
        "roles": invitation.role_names(),
        "status": invitation.status.value
        if isinstance(invitation.status, TenantInvitationStatus)
        else str(invitation.status),
        "expires_at_in_seconds": invitation.expires_at_in_seconds,
        "accepted_at_in_seconds": invitation.accepted_at_in_seconds,
        "created_by": invitation.created_by,
        "created_at_in_seconds": invitation.created_at_in_seconds,
    }
    if include_link is not None:
        # Only surfaced when SMTP is not configured (dev mode), so the link is testable.
        data["invitation_link"] = include_link
    return data


def _validated_roles(roles: Any) -> tuple[str, ...]:
    normalized = normalize_tenant_role_names(roles if isinstance(roles, (list, tuple)) else [roles])
    if not normalized:
        raise ApiError(
            error_code="invalid_roles",
            message="At least one valid role is required.",
            status_code=400,
        )
    return normalized


def _send_invitation_email(email: str, tenant_name: str, raw_token: str) -> bool:
    accept_url = _accept_url(raw_token)
    subject = f"You have been invited to {tenant_name} on m8flow"
    html_body = (
        f"<p>You have been invited to join <strong>{tenant_name}</strong> on m8flow.</p>"
        f"<p>Click the link below to set your password and activate your account. "
        f"This link is single-use and will expire.</p>"
        f'<p><a href="{accept_url}">Accept your invitation</a></p>'
        f"<p>If the link does not work, copy and paste this URL into your browser:<br>{accept_url}</p>"
    )
    text_body = (
        f"You have been invited to join {tenant_name} on m8flow.\n\n"
        f"Set your password and activate your account here (single-use, expires soon):\n{accept_url}\n"
    )
    return send_email(email, subject, html_body, text_body=text_body)


def _has_active_pending_invitation(tenant_id: str, email: str) -> bool:
    invitation = (
        M8flowTenantInvitationModel.query.filter_by(
            m8f_tenant_id=tenant_id,
            email=email,
            status=TenantInvitationStatus.PENDING,
        )
        .order_by(M8flowTenantInvitationModel.expires_at_in_seconds.desc())
        .first()
    )
    if invitation is None:
        return False
    _maybe_expire(invitation)
    return invitation.status == TenantInvitationStatus.PENDING


def create_invitation(
    tenant_id: str,
    email: str,
    roles: Any,
    validity_days: int | None,
    created_by: str,
) -> dict[str, Any]:
    """Create a PENDING invitation, email the accept link, and return the invitation."""
    normalized_email = _normalized_email(email)
    if not normalized_email or "@" not in normalized_email:
        raise ApiError(
            error_code="invalid_email",
            message="A valid email address is required.",
            status_code=400,
        )

    tenant = TenantService.get_tenant_by_id(tenant_id)
    normalized_roles = _validated_roles(roles)

    if _has_active_pending_invitation(tenant_id, normalized_email):
        raise ApiError(
            error_code="invitation_exists",
            message=f"A pending invitation already exists for '{normalized_email}'.",
            status_code=409,
        )

    # username == email; reject if that account already exists in the shared realm.
    if get_realm_user_by_username(shared_realm_name(), normalized_email):
        raise ApiError(
            error_code="user_exists",
            message=f"A user with email '{normalized_email}' already exists.",
            status_code=409,
        )

    raw_token = secrets.token_urlsafe(32)
    now = _now_seconds()
    invitation = M8flowTenantInvitationModel(
        id=str(uuid.uuid4()),
        m8f_tenant_id=tenant_id,
        email=normalized_email,
        roles=",".join(normalized_roles),
        token_hash=_hash_token(raw_token),
        status=TenantInvitationStatus.PENDING,
        expires_at_in_seconds=now + _validity_days(validity_days) * _SECONDS_PER_DAY,
        accepted_at_in_seconds=None,
        created_by=created_by,
        modified_by=created_by,
    )
    db.session.add(invitation)
    db.session.commit()

    sent = _send_invitation_email(normalized_email, tenant.name, raw_token)
    link = None if sent else _accept_url(raw_token)
    return _serialize(invitation, include_link=link)


def list_invitations(
    tenant_id: str,
    status_filter: str | None = None,
    offset: int = 0,
    limit: int = 10,
) -> dict[str, Any]:
    """List invitations for a tenant (optionally filtered by status)."""
    TenantService.get_tenant_by_id(tenant_id)
    query = M8flowTenantInvitationModel.query.filter_by(m8f_tenant_id=tenant_id)
    if status_filter:
        normalized_status = status_filter.strip().upper()
        if normalized_status in TenantInvitationStatus.__members__:
            query = query.filter_by(status=TenantInvitationStatus[normalized_status])

    total = query.count()
    invitations = (
        query.order_by(M8flowTenantInvitationModel.created_at_in_seconds.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    # Reflect lazy expiry in the listing without a separate sweep.
    for invitation in invitations:
        _maybe_expire(invitation)

    return {
        "results": [_serialize(invitation) for invitation in invitations],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def _invitation_or_error(tenant_id: str, invitation_id: str) -> M8flowTenantInvitationModel:
    invitation = M8flowTenantInvitationModel.query.filter_by(
        id=invitation_id,
        m8f_tenant_id=tenant_id,
    ).first()
    if invitation is None:
        raise ApiError(
            error_code="invitation_not_found",
            message="Invitation not found.",
            status_code=404,
        )
    return invitation


def resend_invitation(tenant_id: str, invitation_id: str, modified_by: str) -> dict[str, Any]:
    """Rotate the token + expiry of a pending invitation and re-send the email."""
    tenant = TenantService.get_tenant_by_id(tenant_id)
    invitation = _invitation_or_error(tenant_id, invitation_id)
    _maybe_expire(invitation)

    if invitation.status not in (TenantInvitationStatus.PENDING, TenantInvitationStatus.EXPIRED):
        raise ApiError(
            error_code="invitation_not_resendable",
            message=f"Cannot resend an invitation with status '{invitation.status.value}'.",
            status_code=409,
        )

    raw_token = secrets.token_urlsafe(32)
    invitation.token_hash = _hash_token(raw_token)
    invitation.status = TenantInvitationStatus.PENDING
    invitation.expires_at_in_seconds = _now_seconds() + DEFAULT_VALIDITY_DAYS * _SECONDS_PER_DAY
    invitation.modified_by = modified_by
    db.session.add(invitation)
    db.session.commit()

    sent = _send_invitation_email(invitation.email, tenant.name, raw_token)
    link = None if sent else _accept_url(raw_token)
    return _serialize(invitation, include_link=link)


def revoke_invitation(tenant_id: str, invitation_id: str, modified_by: str) -> dict[str, Any]:
    """Mark a pending invitation as REVOKED so its link can no longer be used."""
    TenantService.get_tenant_by_id(tenant_id)
    invitation = _invitation_or_error(tenant_id, invitation_id)

    if invitation.status == TenantInvitationStatus.ACCEPTED:
        raise ApiError(
            error_code="invitation_already_accepted",
            message="Cannot revoke an invitation that has already been accepted.",
            status_code=409,
        )

    invitation.status = TenantInvitationStatus.REVOKED
    invitation.modified_by = modified_by
    db.session.add(invitation)
    db.session.commit()
    return _serialize(invitation)


def _pending_invitation_by_token(raw_token: str) -> M8flowTenantInvitationModel:
    token = str(raw_token or "").strip()
    if not token:
        raise ApiError(
            error_code="invalid_invitation",
            message="Invitation token is required.",
            status_code=400,
        )

    invitation = M8flowTenantInvitationModel.query.filter_by(token_hash=_hash_token(token)).first()
    if invitation is None:
        raise ApiError(
            error_code="invalid_invitation",
            message="This invitation link is invalid.",
            status_code=404,
        )

    _maybe_expire(invitation)

    if invitation.status == TenantInvitationStatus.EXPIRED:
        raise ApiError(
            error_code="invitation_expired",
            message="This invitation link has expired.",
            status_code=410,
        )
    if invitation.status != TenantInvitationStatus.PENDING:
        # ACCEPTED or REVOKED.
        raise ApiError(
            error_code="invitation_unusable",
            message="This invitation link can no longer be used.",
            status_code=409,
        )
    return invitation


def validate_token(raw_token: str) -> dict[str, Any]:
    """Validate a token and return safe metadata for the accept page (no secrets)."""
    invitation = _pending_invitation_by_token(raw_token)
    tenant = TenantService.get_tenant_by_id(invitation.m8f_tenant_id)
    return {
        "email": invitation.email,
        "tenant_id": invitation.m8f_tenant_id,
        "tenant_name": tenant.name,
        "roles": invitation.role_names(),
        "expires_at_in_seconds": invitation.expires_at_in_seconds,
    }


def accept_invitation(raw_token: str, password: str) -> dict[str, Any]:
    """Create the Keycloak account, attach to tenant with roles, and consume the token."""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError(
            error_code="weak_password",
            message=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            status_code=400,
        )

    invitation = _pending_invitation_by_token(raw_token)
    tenant = TenantService.get_tenant_by_id(invitation.m8f_tenant_id)
    email = invitation.email
    role_names = invitation.role_names()

    # Map roles -> organization groups; tenant roles are derived from group membership.
    group_names = []
    for role_name in role_names:
        group_name = primary_organization_group_name_for_tenant_role(role_name)
        if group_name and group_name not in group_names:
            group_names.append(group_name)

    # Create the Keycloak user (username == email). If it already exists (e.g. a retried
    # accept after a partial failure), continue so the rest of the flow is idempotent.
    realm = shared_realm_name()
    if not get_realm_user_by_username(realm, email):
        create_user_in_realm(realm, email, password, email=email)

    # This is an unauthenticated request, so set the tenant context explicitly to the
    # invitation's tenant for the membership write (mirrors an authenticated tenant request).
    context_token = set_context_tenant_id(invitation.m8f_tenant_id)
    try:
        # Attach to the tenant organization and assign the granted role groups.
        add_tenant_member(invitation.m8f_tenant_id, username=email, group_names=group_names)

        invitation.status = TenantInvitationStatus.ACCEPTED
        invitation.accepted_at_in_seconds = _now_seconds()
        invitation.modified_by = email
        db.session.add(invitation)
        db.session.commit()
    finally:
        reset_context_tenant_id(context_token)

    logger.info(
        "tenant_invitation: accepted invitation %s for %s in tenant %s",
        invitation.id,
        email,
        invitation.m8f_tenant_id,
    )

    return {
        "email": email,
        "tenant_id": invitation.m8f_tenant_id,
        "tenant_name": tenant.name,
        "roles": role_names,
        "smtp_configured": smtp_is_configured(),
    }
