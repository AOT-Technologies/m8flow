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
            referenced_keys = {
                variable.provider_key for variable in variables if variable.provider_key
            }

            profiles = list(
                session.scalars(
                    select(ConnectorConfigurationModel).where(
                        ConnectorConfigurationModel.m8f_tenant_id == tenant_id
                    )
                )
            )

            # Confirm each legacy connector reference still resolves. Do not
            # persist the plaintext returned by the provider.
            for variable in variables:
                key = variable.provider_key
                if not key:
                    stats["connector_missing_reference"] += 1
                    continue
                configured = provider.get_value(session, tenant_id=tenant_id, key=key) is not None
                stats["connector_payload_found" if configured else "connector_payload_missing"] += 1
                if variable.is_configured != configured:
                    stats["connector_flags_to_update"] += 1
                    if apply:
                        variable.is_configured = configured

            for profile in profiles:
                refs = dict(profile.secret_refs or {})
                if not refs and profile.provider_key != str(profile.id):
                    continue
                values: dict[str, str] = {}
                missing_fields: list[str] = []
                for field_name, key in refs.items():
                    value = get_secret_value(session, tenant_id=tenant_id, key=key)
                    if value is None:
                        missing_fields.append(field_name)
                    else:
                        values[field_name] = value
                stats["connector_profiles_examined"] += 1
                if missing_fields:
                    stats["connector_profile_payloads_missing"] += len(missing_fields)
                    continue

                existing_document = get_connector_configuration(
                    session,
                    tenant_id=tenant_id,
                    configuration_id=profile.id,
                )
                if existing_document is not None and existing_document != values:
                    stats["connector_document_conflicts"] += 1
                    continue
                if existing_document == values and profile.provider_key == str(profile.id):
                    stats["connector_documents_verified"] += 1
                    continue

                stats["connector_documents_to_write"] += 1
                if apply:
                    set_connector_configuration(
                        session,
                        tenant_id=tenant_id,
                        configuration_id=profile.id,
                        values=values,
                        user_id=profile.created_by_user_id,
                        replace_existing=profile.provider_key == str(profile.id),
                    )
                    if get_connector_configuration(
                        session,
                        tenant_id=tenant_id,
                        configuration_id=profile.id,
                    ) != values:
                        raise RuntimeError(
                            f"Connector profile {profile.id} provider document verification failed."
                        )
                    profile.provider_key = str(profile.id)
                    profile.schema_version = "1"

            # Secret keys not referenced by connector profiles represent the
            # legacy named-value catalog. Preserve existing rows and names.
            existing = {
                row.name.casefold(): row
                for row in session.scalars(
                    select(NamedValueModel).where(NamedValueModel.m8f_tenant_id == tenant_id)
                )
            }
            for key in provider.list_keys(session, tenant_id=tenant_id):
                if key in referenced_keys:
                    continue
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
