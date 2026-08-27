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
        except Exception:
            # A secret we cannot decrypt is not worth failing the whole seed for;
            # the tenant can re-enter that one field in the profile form.
            # codeql[py/clear-text-logging-sensitive-data]: row.key is the
            # Secret's key column (e.g. "SMTP_PASSWORD"), a fixed canonical
            # name. The value is row.value and is never logged.
            logger.warning("Could not decrypt secret '%s' while seeding", row.key)
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
                "is_default": True,
            },
            user_id,
        )
    except ConnectorProfileError as error:
        # Seeding is best effort: a validation gap (say a required field the old
        # form never collected) must not block anything, and the tenant can
        # finish the profile by hand.
        logger.warning(
            "Could not seed a default %s profile: %s", connector_type, error.message
        )
        return None

    # codeql[py/clear-text-logging-sensitive-data]: sorted(config.keys()) yields
    # the dict's field names (smtp_host, smtp_password), never its values.
    logger.info(
        "Seeded default %s profile from existing secrets: %s",
        connector_type,
        ", ".join(sorted(config.keys())),
    )
    return profile


def report_unseedable_secrets() -> list[str]:
    """Legacy secret keys the tenant has that no profile can be seeded from.

    Without this the omission is invisible: a tenant with a stored
    GITHUB_PAT_TOKEN would get no profile, no error and no explanation. Logging
    the names (never the values) makes the gap findable.
    """
    present = _existing_secret_keys(list(UNMAPPED_SECRET_KEYS))
    for key in present:
        logger.info(
            "Secret '%s' cannot be carried into a connector profile: %s. "
            "Configure that connector's profile by hand.",
            key,
            UNMAPPED_SECRET_KEYS[key],
        )
    return present


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
