"""Seed a "default" profile from the credentials a tenant already configured.

Before profiles, each connector had exactly one credential set per tenant, saved
as Secrets under fixed canonical keys (SMTP_PASSWORD, SLACK_TOKEN, ...) by the
Connectors > Configure page. This copies those values into a profile named
``default`` so a tenant's existing setup is usable from the modeler dropdown
straight away.

Copy, not move. The original Secrets are left in place, so every process model
that spells out ``"M8FLOW_SECRET:SMTP_PASSWORD"`` keeps working unchanged. The
cost is the same credential encrypted under two keys until a later release
retires the old ones -- deliberate, because breaking live process models to
tidy up storage is the wrong trade.

Idempotent: a connector that already has a ``default`` profile is skipped, so
this can be re-run safely.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Audit conventions, matching the vault events already in m8flow_audit_log.
AUDIT_CATEGORY = "connector_profile"
AUDIT_SOURCE = "connector_profile_migration"


def _audit(
    event_type: str,
    status: str,
    message: str,
    *,
    severity: str = "info",
    resource_id: Any = None,
    **details: Any,
) -> None:
    """Record a seeding event, best effort.

    Seeding copies a tenant's credentials, so each outcome belongs in
    m8flow_audit_log and not only in the application log. ``try_record_event``
    fills in tenant, actor and request ids from the request context, redacts the
    payload and swallows its own errors, so this can never break a seed.

    Only field *names* are ever passed as details -- never a config value, which
    would be a live credential.
    """
    from flask import has_app_context

    if not has_app_context():
        return

    from m8flow_backend.services.audit_log_service import get_audit_log_service

    get_audit_log_service().try_record_event(
        category=AUDIT_CATEGORY,
        event_type=event_type,
        source=AUDIT_SOURCE,
        status=status,
        severity=severity,
        message=message,
        resource_type="connector_profile",
        resource_id=resource_id,
        details=details,
    )


# Old canonical Secret key -> the field name in the new pydantic definition.
#
# The two differ on purpose: the old keys are display-oriented and global
# (SMTP_HOST), while a definition field name must be the connector proxy's
# keyword argument (smtp_host). Only connectors whose credentials map cleanly
# appear here; the rest are left to be configured as profiles by hand.
SECRET_KEY_TO_FIELD: dict[str, dict[str, str]] = {
    "smtp": {
        "SMTP_HOST": "smtp_host",
        "SMTP_PORT": "smtp_port",
        "SMTP_USER": "smtp_user",
        "SMTP_PASSWORD": "smtp_password",
        "SMTP_FROM_EMAIL": "email_from",
    },
    "slack": {
        "SLACK_TOKEN": "token",
        "SLACK_CHANNEL_ID": "channel",
    },
    "postgres_v2": {
        "POSTGRES_CONNECTION_STRING": "database_connection_str",
    },
    "stripe": {
        "STRIPE_KEY": "api_key",
    },
    "salesforce": {
        "SF_CLIENT_ID": "client_id",
        "SF_CLIENT_SECRET": "client_secret",
        "SF_ACCESS_TOKEN": "access_token",
        "SF_REFRESH_TOKEN": "refresh_token",
        "SF_INSTANCE_URL": "instance_url",
    },
    # github is omitted deliberately -- see UNMAPPED_SECRET_KEYS below, which
    # also makes the omission visible to the user instead of silent.
}

# Legacy keys we deliberately do not seed, and why. Kept as data so the gap can
# be reported to the user instead of vanishing into a code comment.
UNMAPPED_SECRET_KEYS: dict[str, str] = {
    "GITHUB_PAT_TOKEN": (
        "the GitHub connector's proxy parameter name is unverified, so a seeded "
        "profile could store the token under a name the connector never reads"
    ),
}

DEFAULT_PROFILE_NAME = "default"


def _existing_secret_values(keys: list[str]) -> dict[str, str]:
    """Read the current tenant's values for the given Secret keys.

    Tenant scoping is handled by the query listener in tenant_scoping_patch, so
    this only sees the calling tenant's secrets.
    """
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.models.secret_model import SecretModel
    from spiffworkflow_backend.services.secret_service import SecretService

    rows = db.session.query(SecretModel).filter(SecretModel.key.in_(keys)).all()
    values: dict[str, str] = {}
    for row in rows:
        try:
            decrypted = SecretService._decrypt(row.value)
        except Exception as exc:
            # A secret we cannot decrypt is not worth failing the whole seed for;
            # the tenant can re-enter that one field in the profile form.
            # codeql[py/clear-text-logging-sensitive-data]: row.key is the
            # Secret's key column (e.g. "SMTP_PASSWORD"), a fixed canonical
            # name. The value is row.value and is never logged.
            logger.warning("Could not decrypt secret '%s' while seeding", row.key)
            _audit(
                "connector_profile.seed.secret_unreadable",
                "failed",
                "A stored secret could not be decrypted while seeding.",
                severity="warning",
                secret_key=row.key,
                error_type=type(exc).__name__,
            )
            continue
        if decrypted not in (None, ""):
            values[row.key] = decrypted
    return values


def _existing_secret_keys(keys: list[str]) -> list[str]:
    """Which of the given Secret keys the current tenant has, names only.

    Deliberately never decrypts: a caller that only needs to know *whether* a
    secret exists must not hold its plaintext, so a log line built from this
    cannot leak a credential even by accident. The query selects the key column
    alone, so the encrypted value is never even loaded.
    """
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.models.secret_model import SecretModel

    rows = db.session.query(SecretModel.key).filter(SecretModel.key.in_(keys)).all()
    return [row.key for row in rows]


def seed_default_profile(connector_type: str, user_id: int | None = None) -> Any | None:
    """Create the ``default`` profile for one connector, if it is missing.

    Returns the created profile, or None when there was nothing to seed (no
    stored credentials, or a ``default`` profile already exists).
    """
    from m8flow_backend.services.connector_profile_service import (
        ConnectorProfileError,
        ConnectorProfileService,
    )

    mapping = SECRET_KEY_TO_FIELD.get(connector_type)
    if not mapping:
        return None

    existing = ConnectorProfileService.list_profiles(connector_type)
    if any(profile.profile_name == DEFAULT_PROFILE_NAME for profile in existing):
        return None

    values = _existing_secret_values(list(mapping))
    if not values:
        # Nothing was configured the old way, so there is nothing to carry over.
        return None

    config = {mapping[key]: value for key, value in values.items()}

    try:
        profile = ConnectorProfileService.create_profile(
            {
                "connector_type": connector_type,
                "profile_name": DEFAULT_PROFILE_NAME,
                "display_name": "Default",
                "description": (
                    "Created from the credentials previously configured under "
                    "Connectors. The original secrets are unchanged, so existing "
                    "process models keep working."
                ),
                "config": config,
            },
            user_id,
        )
    except ConnectorProfileError as error:
        # Seeding is best effort: a validation gap (say a required field the old
        # form never collected) must not block anything, and the tenant can
        # finish the profile by hand.
        # Nothing off `error` is logged here: error.message/error.errors can echo
        # the submitted config, so the exception type and message go to the
        # redacted audit log below instead of the clear-text application log.
        logger.warning(
            "Could not seed a default %s profile; see the audit log for details.",
            connector_type,
        )
        _audit(
            "connector_profile.seed.failed",
            "failed",
            f"Could not seed a default {connector_type} profile: {error.message}",
            severity="warning",
            connector_type=connector_type,
            profile_name=DEFAULT_PROFILE_NAME,
            validation_errors=error.errors,
        )
        return None

    # Field names only (smtp_host, ...), never values. The app log gets the
    # count as an int; the field names go to the redacted audit log below.
    # CodeQL classifies anything traced to SECRET_KEY_TO_FIELD as sensitive, so
    # only a non-string (the count) is logged here.
    seeded_fields = sorted(field for key, field in mapping.items() if key in values)
    logger.info(
        "Seeded default %s profile from %d existing secret field(s).",
        connector_type,
        len(seeded_fields),
    )
    _audit(
        "connector_profile.seed.succeeded",
        "success",
        f"Seeded the default {connector_type} profile from existing secrets.",
        connector_type=connector_type,
        profile_name=DEFAULT_PROFILE_NAME,
        resource_id=getattr(profile, "id", None),
        # Field names only. The values are the credentials themselves.
        seeded_fields=seeded_fields,
    )
    return profile


def report_unseedable_secrets() -> list[str]:
    """Legacy secret keys the tenant has that no profile can be seeded from.

    Without this the omission is invisible: a tenant with a stored
    GITHUB_PAT_TOKEN would get no profile, no error and no explanation. Logging
    the names (never the values) makes the gap findable.
    """
    # The key names and reasons go to the redacted audit log (one
    # connector_profile.seed.skipped event each), which is where the gap is meant
    # to be found. The app log gets only the count as an int: CodeQL classifies
    # anything traced to UNMAPPED_SECRET_KEYS as sensitive, so no name is logged.
    present_keys = set(_existing_secret_keys(list(UNMAPPED_SECRET_KEYS)))
    reported: list[str] = []
    for key, reason in UNMAPPED_SECRET_KEYS.items():
        if key not in present_keys:
            continue
        _audit(
            "connector_profile.seed.skipped",
            "skipped",
            f"Secret '{key}' cannot be carried into a connector profile.",
            secret_key=key,
            reason=reason,
        )
        reported.append(key)
    if reported:
        logger.info(
            "%d stored legacy secret(s) have no connector-profile mapping and "
            "were skipped; see the connector_profile.seed.skipped audit events "
            "for the key names and reasons.",
            len(reported),
        )
    return reported


def seed_all_default_profiles(user_id: int | None = None) -> list[str]:
    """Seed every connector that has old-style credentials stored.

    Returns the connector types for which a profile was created.
    """
    seeded: list[str] = []
    for connector_type in SECRET_KEY_TO_FIELD:
        if seed_default_profile(connector_type, user_id) is not None:
            seeded.append(connector_type)
    report_unseedable_secrets()
    return seeded
