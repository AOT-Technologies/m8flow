"""Verify legacy secret payloads and backfill configuration-variable metadata.

The default mode is read-only. Pass ``--apply`` to create named-value rows,
update connector-variable ``is_configured`` flags, and create/readback-verify
the new per-profile secret document. Secret values are never printed or
deleted; legacy provider keys remain available for rollback. Run after the
``d2f4a6b8c0e1`` Alembic revision has been applied.
"""

from __future__ import annotations

import argparse
import uuid
from collections import Counter

from sqlalchemy import select, text

from m8flow_backend.connectors.configuration import (
    ConnectorConfigurationModel,
    ConnectorVariableModel,
)
from m8flow_backend.db import session_scope
from m8flow_backend.models import NamedValueModel
from m8flow_backend.secrets import (
    get_connector_configuration,
    get_secret_provider,
    get_secret_value,
    set_connector_configuration,
)
from m8flow_core.models.tenant import M8flowTenantModel

_PROVIDER_KEY_MAX_LENGTH = 255


def _normalize_connector_document(values: dict[str, str]) -> dict[str, str] | None:
    """Canonicalize field names for comparison while preserving values exactly.

    Connector field names are treated case-insensitively during backfill. If a
    provider document contains two names that collapse to the same casefolded
    key, it is ambiguous and must not be treated as equivalent.
    """
    normalized: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(key, str):
            return None
        canonical_key = key.casefold()
        if canonical_key in normalized:
            return None
        normalized[canonical_key] = value
    return normalized


def _connector_documents_match(existing: dict[str, str], expected: dict[str, str]) -> bool:
    normalized_existing = _normalize_connector_document(existing)
    normalized_expected = _normalize_connector_document(expected)
    return (
        normalized_existing is not None
        and normalized_expected is not None
        and normalized_existing == normalized_expected
    )


def _validate_provider_key_lengths(tenant_id: str, keys: list[str]) -> None:
    """Reject keys that cannot fit in the metadata columns before any writes."""
    for key in keys:
        if not isinstance(key, str):
            raise RuntimeError(
                f"Tenant {tenant_id!r} has a non-string provider key; "
                "provider keys must be strings no longer than "
                f"{_PROVIDER_KEY_MAX_LENGTH} characters."
            )
        if len(key) > _PROVIDER_KEY_MAX_LENGTH:
            raise RuntimeError(
                f"Tenant {tenant_id!r} has a provider key of length {len(key)}; "
                "provider keys stored in configuration metadata may not exceed "
                f"{_PROVIDER_KEY_MAX_LENGTH} characters. Rename the key before "
                "backfilling."
            )


def _validate_provider_key_names(tenant_id: str, keys: list[str]) -> None:
    """Reject ambiguous case-insensitive named-value keys before backfill writes."""
    keys_by_name: dict[str, set[str]] = {}
    for key in keys:
        keys_by_name.setdefault(key.casefold(), set()).add(key)

    collisions = [
        sorted(names)
        for names in keys_by_name.values()
        if len(names) > 1
    ]
    if collisions:
        details = "; ".join(", ".join(names) for names in sorted(collisions))
        raise RuntimeError(
            f"Tenant {tenant_id!r} has case-insensitive collisions among "
            f"provider keys: {details}. Resolve these key names before backfilling."
        )


def _set_tenant(session, tenant_id: str) -> None:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )


def run(*, apply: bool) -> Counter[str]:
    stats: Counter[str] = Counter()
    provider = get_secret_provider()

    with session_scope() as session:
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            # Tenant enumeration is read-only. All payload reads and writes below
            # switch back to an explicit tenant context before accessing data.
            session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        tenant_ids = list(session.scalars(select(M8flowTenantModel.id).order_by(M8flowTenantModel.id)))

        # Validate every tenant's provider keys before the apply pass. A bad
        # key discovered late must not leave earlier tenants partially migrated.
        provider_keys_by_tenant: dict[str, list[str]] = {}
        for tenant_id in tenant_ids:
            _set_tenant(session, tenant_id)
            provider_keys = provider.list_keys(session, tenant_id=tenant_id)
            _validate_provider_key_lengths(tenant_id, provider_keys)
            provider_keys_by_tenant[tenant_id] = provider_keys

        for tenant_id in tenant_ids:
            _set_tenant(session, tenant_id)
            variables = list(
                session.scalars(
                    select(ConnectorVariableModel).where(
                        ConnectorVariableModel.m8f_tenant_id == tenant_id,
                        ConnectorVariableModel.is_sensitive.is_(True),
                    )
                )
            )
            profiles = list(
                session.scalars(
                    select(ConnectorConfigurationModel).where(
                        ConnectorConfigurationModel.m8f_tenant_id == tenant_id
                    )
                )
            )
            profiles_by_id = {profile.id: profile for profile in profiles}
            documents_by_key: dict[str, dict[str, str] | None] = {}

            def profile_document(profile: ConnectorConfigurationModel):
                key = profile.provider_key
                if not key:
                    return None
                if key not in documents_by_key:
                    documents_by_key[key] = get_connector_configuration(
                        session,
                        tenant_id=tenant_id,
                        configuration_id=key,
                    )
                return documents_by_key[key]

            referenced_keys = {
                variable.provider_key for variable in variables if variable.provider_key
            }
            for profile in profiles:
                referenced_keys.update(
                    key for key in (profile.secret_refs or {}).values() if key
                )

            provider_keys = provider_keys_by_tenant[tenant_id]
            named_value_keys = [
                key for key in provider_keys if key not in referenced_keys
            ]
            _validate_provider_key_names(tenant_id, named_value_keys)

            # Do the collision check before any connector metadata or provider
            # documents are updated, so an ambiguous tenant remains untouched.
            existing = {
                row.name.casefold(): row
                for row in session.scalars(
                    select(NamedValueModel).where(NamedValueModel.m8f_tenant_id == tenant_id)
                )
            }

            # Confirm each legacy connector reference still resolves. Do not
            # persist the plaintext returned by the provider.
            for variable in variables:
                key = variable.provider_key
                if not key:
                    stats["connector_missing_reference"] += 1
                    continue
                profile = profiles_by_id.get(variable.connector_configuration_id)
                if profile and profile.provider_key == key:
                    document = profile_document(profile)
                    configured = (
                        document is not None
                        and variable.field_name in document
                        and document[variable.field_name] is not None
                    )
                else:
                    configured = provider.get_value(
                        session, tenant_id=tenant_id, key=key
                    ) is not None
                stats["connector_payload_found" if configured else "connector_payload_missing"] += 1
                if variable.is_configured != configured:
                    stats["connector_flags_to_update"] += 1
                    if apply:
                        variable.is_configured = configured

            for profile in profiles:
                refs = dict(profile.secret_refs or {})
                if not refs and profile.provider_key != str(profile.id):
                    continue
                document_refs = {
                    field_name: key
                    for field_name, key in refs.items()
                    if profile.provider_key and key == profile.provider_key
                }
                legacy_refs = {
                    field_name: key
                    for field_name, key in refs.items()
                    if not profile.provider_key or key != profile.provider_key
                }
                values: dict[str, str] = {}
                missing_fields: list[str] = []
                existing_document = profile_document(profile) if document_refs else None
                if document_refs:
                    if existing_document is None:
                        missing_fields.extend(document_refs)
                    else:
                        for field_name in document_refs:
                            value = existing_document.get(field_name)
                            if value is None:
                                missing_fields.append(field_name)
                            else:
                                values[field_name] = value
                for field_name, key in legacy_refs.items():
                    value = get_secret_value(session, tenant_id=tenant_id, key=key)
                    if value is None:
                        missing_fields.append(field_name)
                    else:
                        values[field_name] = value
                stats["connector_profiles_examined"] += 1
                if missing_fields:
                    stats["connector_profile_payloads_missing"] += len(missing_fields)
                    continue

                # New profiles already point at their UUID-keyed document.
                # Keep that pointer; legacy profiles are migrated to the
                # profile-ID document below.
                target_key = profile.provider_key if document_refs else str(profile.id)
                if not document_refs:
                    existing_document = get_connector_configuration(
                        session,
                        tenant_id=tenant_id,
                        configuration_id=target_key,
                    )
                documents_match = existing_document is not None and _connector_documents_match(
                    existing_document, values
                )
                if existing_document is not None and not documents_match:
                    stats["connector_document_conflicts"] += 1
                    continue
                if documents_match and profile.provider_key == target_key:
                    stats["connector_documents_verified"] += 1
                    continue

                stats["connector_documents_to_write"] += 1
                if apply:
                    set_connector_configuration(
                        session,
                        tenant_id=tenant_id,
                        configuration_id=target_key,
                        values=values,
                        user_id=profile.created_by_user_id,
                        replace_existing=profile.provider_key == target_key,
                    )
                    written_document = get_connector_configuration(
                        session,
                        tenant_id=tenant_id,
                        configuration_id=target_key,
                    )
                    if written_document is None or not _connector_documents_match(
                        written_document, values
                    ):
                        raise RuntimeError(
                            f"Connector profile {profile.id} provider document verification failed."
                        )
                    profile.provider_key = target_key
                    profile.schema_version = "1"

            # Secret keys not referenced by connector profiles represent the
            # legacy named-value catalog. Preserve existing rows and names.
            for key in named_value_keys:
                value_exists = provider.get_value(session, tenant_id=tenant_id, key=key) is not None
                normalized = key.casefold()
                row = existing.get(normalized)
                if row is None:
                    stats["named_value_rows_to_create"] += 1
                    if apply:
                        row = NamedValueModel(
                            id=str(uuid.uuid4()),
                            m8f_tenant_id=tenant_id,
                            name=key,
                            is_sensitive=True,
                            value=None,
                            is_configured=value_exists,
                            provider_key=key,
                        )
                        session.add(row)
                        existing[normalized] = row
                else:
                    stats["named_value_rows_existing"] += 1
                    if row.is_sensitive and row.is_configured != value_exists:
                        stats["named_value_flags_to_update"] += 1
                        if apply:
                            row.is_configured = value_exists

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist metadata updates. Without this flag the command is read-only.",
    )
    args = parser.parse_args()
    stats = run(apply=args.apply)
    mode = "Applied" if args.apply else "Dry run"
    print(f"{mode}: verified configuration-variable metadata (secret values were not displayed).")
    for name, count in sorted(stats.items()):
        print(f"{name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
