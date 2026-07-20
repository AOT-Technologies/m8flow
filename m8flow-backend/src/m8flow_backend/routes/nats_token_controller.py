from __future__ import annotations
from flask import g, request
from m8flow_backend.services.nats_token_service import NatsTokenService
from m8flow_backend.helpers.response_helper import success_response, handle_api_errors
from m8flow_backend.tenancy import get_tenant_id
from spiffworkflow_backend.exceptions.api_error import ApiError

# Supported token lifetimes offered in the UI. Omitting the value (or null) means "never expires".
SECONDS_PER_DAY = 24 * 60 * 60
ALLOWED_EXPIRY_DAYS = {30, 90, 365}
MAX_LABEL_LENGTH = 255


def _serialize_api_key_metadata(api_key):
    """Serialize key metadata WITHOUT ever exposing the token value."""
    return {
        "id": api_key.id,
        "label": api_key.label,
        "tenantId": api_key.m8f_tenant_id,
        "scope": api_key.scope,
        "expiresAtInSeconds": api_key.expires_at_in_seconds,
        "lastUsedAtInSeconds": api_key.last_used_at_in_seconds,
        "revokedAtInSeconds": api_key.revoked_at_in_seconds,
        "createdAtInSeconds": api_key.created_at_in_seconds,
        "createdBy": api_key.created_by,
        "updatedAtInSeconds": api_key.updated_at_in_seconds,
        "modifiedBy": api_key.modified_by,
    }


def _serialize_api_key(api_key, raw_token):
    """Serialize a named API key including its raw value (only right after creation)."""
    return {**_serialize_api_key_metadata(api_key), "token": raw_token}


def _require_authenticated_user():
    """Ensure user is authenticated."""
    user = getattr(g, 'user', None)
    if not user:
        raise ApiError(
            error_code="not_authenticated",
            message="User not authenticated",
            status_code=401
        )
    return user


def _resolve_expiry_seconds(body: dict) -> int | None:
    """Validate the optional expiresInDays from the request body and convert to seconds.

    Returns None when the token should never expire (value omitted or null).
    Raises ApiError(400) for unsupported values.
    """
    expires_in_days = body.get("expiresInDays")
    if expires_in_days is None:
        return None

    try:
        expires_in_days = int(expires_in_days)
    except (TypeError, ValueError):
        raise ApiError(
            error_code="invalid_expiry",
            message="expiresInDays must be an integer or null.",
            status_code=400,
        )

    if expires_in_days not in ALLOWED_EXPIRY_DAYS:
        allowed = ", ".join(str(d) for d in sorted(ALLOWED_EXPIRY_DAYS))
        raise ApiError(
            error_code="invalid_expiry",
            message=f"expiresInDays must be one of: {allowed} (or null for no expiry).",
            status_code=400,
        )

    return expires_in_days * SECONDS_PER_DAY


def _resolve_label(body: dict) -> str:
    """Validate and normalize the required key label."""
    label = body.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ApiError(
            error_code="invalid_label",
            message="A non-empty label is required for the API key.",
            status_code=400,
        )
    label = label.strip()
    if len(label) > MAX_LABEL_LENGTH:
        raise ApiError(
            error_code="invalid_label",
            message=f"label must be at most {MAX_LABEL_LENGTH} characters.",
            status_code=400,
        )
    return label


def _resolve_scope(body: dict) -> str | None:
    """Validate the optional scope. Accepts a string or a list of process identifiers."""
    scope = body.get("scope")
    if scope is None:
        return None
    if isinstance(scope, list):
        # Every entry must be a string; reject non-strings rather than coercing
        # them (e.g. None -> "None") into a valid-looking process identifier.
        for entry in scope:
            if not isinstance(entry, str):
                raise ApiError(
                    error_code="invalid_scope",
                    message="Each scope entry must be a string process identifier.",
                    status_code=400,
                )
        # Deduplicate while preserving first-seen order.
        seen: set[str] = set()
        entries: list[str] = []
        for entry in scope:
            stripped = entry.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                entries.append(stripped)
        return ",".join(entries) if entries else None
    if isinstance(scope, str):
        stripped = scope.strip()
        return stripped or None
    raise ApiError(
        error_code="invalid_scope",
        message="scope must be a string, a list of process identifiers, or null.",
        status_code=400,
    )


@handle_api_errors
def generate_token():
    """
    Create a new named NATS API key for the current tenant.

    Body: ``{"label": "...", "expiresInDays": 30|90|365|null, "scope": "..."|[...]|null}``.
    The raw key value is returned ONCE and can never be retrieved again.

    Restricted to users with 'manage-nats-tokens' permission (tenant-admin).
    """
    user = _require_authenticated_user()
    tenant_id = get_tenant_id()

    body = request.get_json(silent=True) or {}
    label = _resolve_label(body)
    expires_in_seconds = _resolve_expiry_seconds(body)
    scope = _resolve_scope(body)

    api_key, raw_token = NatsTokenService.create_named_key(
        tenant_id=tenant_id,
        user_id=user.username,
        label=label,
        expires_in_seconds=expires_in_seconds,
        scope=scope,
    )

    # The raw token is returned here ONCE and never again.
    return success_response(_serialize_api_key(api_key, raw_token), 201)


@handle_api_errors
def list_tokens():
    """
    List metadata for the current tenant's NATS API keys, WITHOUT any token values.

    Restricted to users with 'read-nats-tokens' (or 'manage-nats-tokens').
    """
    _require_authenticated_user()
    tenant_id = get_tenant_id()

    keys = NatsTokenService.list_keys(tenant_id)
    return success_response(
        {"keys": [_serialize_api_key_metadata(key) for key in keys]},
        200,
    )


@handle_api_errors
def delete_token(key_id: str):
    """
    Revoke a single NATS API key owned by the current tenant.

    Restricted to users with 'manage-nats-tokens' permission.
    """
    user = _require_authenticated_user()
    tenant_id = get_tenant_id()

    revoked = NatsTokenService.revoke_key(tenant_id, key_id, user.username)
    return success_response({"revoked": revoked, "id": key_id}, 200)
