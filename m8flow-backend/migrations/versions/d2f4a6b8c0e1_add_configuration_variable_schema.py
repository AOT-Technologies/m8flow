"""Add tenant-scoped configuration variables and connector field rows.

The current-main migration graph ends at ``c1e4f5a6b7d8``. Existing connector
profiles keep their original IDs, JSON, and secret references. This revision
adds the target metadata and copies safe database metadata only; it never reads,
decrypts, moves, or deletes a secret-provider payload. The explicit backend
backfill command verifies provider payloads, writes and reads back the new
profile document, and records configured state while preserving legacy keys for
rollback.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from typing import Any

import sqlalchemy as sa
from alembic import op


revision = "d2f4a6b8c0e1"
down_revision = "c1e4f5a6b7d8"
branch_labels = None
depends_on = None

NAMED_VALUE_TABLE = "m8flow_named_value"
CONNECTOR_VARIABLE_TABLE = "m8flow_connector_variable"
CONNECTOR_CONFIGURATION_TABLE = "m8flow_connector_configuration"
LEGACY_SECRET_TABLE = "secret"

NAMED_VALUE_NAME_INDEX = "uq_m8flow_named_value_tenant_name_ci"
CONNECTOR_FIELD_UNIQUE = "uq_m8flow_connector_variable_field"
CONNECTOR_PARENT_UNIQUE_INDEX = "uq_host_m8flow_connector_configuration_id_tenant"
CONNECTOR_TENANT_POLICY = f"{CONNECTOR_VARIABLE_TABLE}_tenant_isolation"
CONNECTOR_BYPASS_POLICY = f"{CONNECTOR_VARIABLE_TABLE}_super_admin_select"
NAMED_VALUE_TENANT_POLICY = f"{NAMED_VALUE_TABLE}_tenant_isolation"
NAMED_VALUE_BYPASS_POLICY = f"{NAMED_VALUE_TABLE}_super_admin_select"

_NAMED_VALUE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _is_postgres(bind: sa.Connection) -> bool:
    return bind.dialect.name == "postgresql"


def _table_exists(bind: sa.Connection, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def _required_mapping(value: Any, *, field: str, profile_id: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeError(
            f"Connector profile {profile_id!r} has invalid {field} metadata; "
            "repair the row before applying the configuration-variable migration."
        )
    return value


def _validate_field_name(name: Any, *, profile_id: Any) -> str:
    if not isinstance(name, str) or not name or len(name) > 255:
        raise RuntimeError(
            f"Connector profile {profile_id!r} has an invalid field name; "
            "repair the row before applying the configuration-variable migration."
        )
    return name


def _legacy_secret_rows(bind: sa.Connection) -> list[dict[str, Any]]:
    if not _table_exists(bind, LEGACY_SECRET_TABLE):
        return []

    legacy = sa.Table(LEGACY_SECRET_TABLE, sa.MetaData(), autoload_with=bind)
    required = {"key", "m8f_tenant_id"}
    missing = required - set(legacy.c.keys())
    if missing:
        raise RuntimeError(
            "Cannot backfill configuration variables from the legacy secret table; "
            f"missing columns: {', '.join(sorted(missing))}."
        )

    selected = [legacy.c.key, legacy.c.m8f_tenant_id]
    for column in ("created_by_user_id", "created_at", "updated_at"):
        selected.append(legacy.c[column] if column in legacy.c else sa.null().label(column))
    rows = [dict(row._mapping) for row in bind.execute(sa.select(*selected)).all()]

    by_tenant_and_name: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        tenant_id = row["m8f_tenant_id"]
        name = row["key"]
        if not isinstance(tenant_id, str) or not tenant_id:
            raise RuntimeError(
                "Cannot backfill a legacy secret without a tenant ID; "
                "repair tenant ownership before applying this migration."
            )
        if not isinstance(name, str) or not _NAMED_VALUE_NAME.fullmatch(name):
            raise RuntimeError(
                f"Cannot backfill legacy secret key {name!r} for tenant "
                f"{tenant_id!r}: names must match [A-Za-z0-9_-]{{1,255}}."
            )
        by_tenant_and_name[(tenant_id, name.casefold())].append(name)

    collisions = [
        (tenant_id, names)
        for (tenant_id, _normalized), names in by_tenant_and_name.items()
        if len(names) > 1
    ]
    if collisions:
        details = "; ".join(
            f"tenant {tenant_id!r}: {', '.join(sorted(names))}"
            for tenant_id, names in collisions
        )
        raise RuntimeError(
            "Cannot enforce case-insensitive configuration-variable names; "
            f"resolve these existing secret-key collisions first: {details}."
        )
    return rows


def _legacy_connector_rows(bind: sa.Connection) -> list[dict[str, Any]]:
    if not _table_exists(bind, CONNECTOR_CONFIGURATION_TABLE):
        raise RuntimeError(
            "The current-main connector profile table is missing; "
            "cannot backfill connector variables."
        )

    profiles = sa.Table(CONNECTOR_CONFIGURATION_TABLE, sa.MetaData(), autoload_with=bind)
    required = {"id", "m8f_tenant_id", "config_json", "secret_refs"}
    missing = required - set(profiles.c.keys())
    if missing:
        raise RuntimeError(
            "Cannot backfill connector variables; connector profiles are missing "
            f"columns: {', '.join(sorted(missing))}."
        )

    selected = [
        profiles.c.id,
        profiles.c.m8f_tenant_id,
        profiles.c.config_json,
        profiles.c.secret_refs,
    ]
    for column in ("created_by_user_id", "created_at", "updated_at"):
        selected.append(profiles.c[column] if column in profiles.c else sa.null().label(column))

    result: list[dict[str, Any]] = []
    for record in bind.execute(sa.select(*selected)).mappings():
        profile = dict(record)
        if not isinstance(profile["m8f_tenant_id"], str) or not profile["m8f_tenant_id"]:
            raise RuntimeError(
                f"Connector profile {profile['id']!r} has no tenant ID; "
                "repair tenant ownership before applying this migration."
            )

        config = _required_mapping(
            profile["config_json"], field="config_json", profile_id=profile["id"]
        )
        refs = _required_mapping(
            profile["secret_refs"], field="secret_refs", profile_id=profile["id"]
        )
        normalized_config = {
            _validate_field_name(name, profile_id=profile["id"]): value
            for name, value in config.items()
        }
        normalized_refs = {
            _validate_field_name(name, profile_id=profile["id"]): value
            for name, value in refs.items()
        }
        overlap = sorted(set(normalized_config) & set(normalized_refs))
        if overlap:
            raise RuntimeError(
                f"Connector profile {profile['id']!r} stores fields in both config_json "
                f"and secret_refs: {', '.join(overlap)}. Repair the row before migration."
            )
        if any(not isinstance(ref, str) or not ref for ref in normalized_refs.values()):
            raise RuntimeError(
                f"Connector profile {profile['id']!r} has an invalid secret reference; "
                "repair the row before migration."
            )

        profile["config_json"] = normalized_config
        profile["secret_refs"] = normalized_refs
        result.append(profile)
    return result


def _enable_rls(bind: sa.Connection, table: str, tenant_policy: str, bypass_policy: str) -> None:
    if not _is_postgres(bind):
        return
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"CREATE POLICY {tenant_policy} ON {table} FOR ALL "
                       f"USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"))
    op.execute(
        sa.text(f"CREATE POLICY {bypass_policy} ON {table} FOR SELECT USING {_BYPASS_PREDICATE}")
    )


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, NAMED_VALUE_TABLE) or _table_exists(bind, CONNECTOR_VARIABLE_TABLE):
        raise RuntimeError(
            "Configuration-variable tables already exist outside this Alembic revision; "
            "reconcile the schema before upgrading."
        )

    # Validate and collect the legacy rows before touching schema. The transaction
    # never copies secret payloads or changes their original provider references.
    legacy_secrets = _legacy_secret_rows(bind)
    legacy_profiles = _legacy_connector_rows(bind)

    op.add_column(
        CONNECTOR_CONFIGURATION_TABLE,
        sa.Column("provider_key", sa.String(length=512), nullable=True),
    )
    op.add_column(
        CONNECTOR_CONFIGURATION_TABLE,
        sa.Column("schema_version", sa.String(length=64), nullable=True),
    )
    op.create_index(
        CONNECTOR_PARENT_UNIQUE_INDEX,
        CONNECTOR_CONFIGURATION_TABLE,
        ["id", "m8f_tenant_id"],
        unique=True,
    )

    op.create_table(
        NAMED_VALUE_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_sensitive", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("value", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("is_configured", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("provider_key", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(is_sensitive = true AND value IS NULL) OR "
            "(is_sensitive = false AND is_configured = false AND value IS NULL) OR "
            "(is_sensitive = false AND is_configured = true AND value IS NOT NULL)",
            name="ck_m8flow_named_value_storage",
        ),
        sa.ForeignKeyConstraint(
            ["m8f_tenant_id"],
            ["m8flow_tenant.id"],
            name="fk_host_m8flow_named_value_m8f_tenant_id_m8flow_tenant",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_host_m8flow_named_value"),
    )
    op.create_index(
        NAMED_VALUE_NAME_INDEX,
        NAMED_VALUE_TABLE,
        ["m8f_tenant_id", sa.text("lower(name)")],
        unique=True,
    )
    op.create_index("ix_m8flow_named_value_tenant", NAMED_VALUE_TABLE, ["m8f_tenant_id"])

    op.create_table(
        CONNECTOR_VARIABLE_TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
        sa.Column("connector_configuration_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=255), nullable=False),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False),
        sa.Column("provider_key", sa.String(length=255), nullable=True),
        sa.Column("value", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("is_configured", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(is_sensitive = false) OR (value IS NULL)",
            name="ck_m8flow_connector_variable_sensitive_value",
        ),
        sa.ForeignKeyConstraint(
            ["m8f_tenant_id"],
            ["m8flow_tenant.id"],
            name="fk_host_m8flow_connector_variable_m8f_tenant_id_m8flow_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["connector_configuration_id", "m8f_tenant_id"],
            [
                f"{CONNECTOR_CONFIGURATION_TABLE}.id",
                f"{CONNECTOR_CONFIGURATION_TABLE}.m8f_tenant_id",
            ],
            name="fk_m8flow_connector_variable_configuration_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_host_m8flow_connector_variable"),
        sa.UniqueConstraint(
            "connector_configuration_id",
            "field_name",
            name=CONNECTOR_FIELD_UNIQUE,
        ),
    )
    op.create_index(
        "ix_m8flow_connector_variable_tenant_configuration",
        CONNECTOR_VARIABLE_TABLE,
        ["m8f_tenant_id", "connector_configuration_id"],
    )
    op.create_index(
        "ix_m8flow_connector_variable_tenant",
        CONNECTOR_VARIABLE_TABLE,
        ["m8f_tenant_id"],
    )

    named_value = sa.table(
        NAMED_VALUE_TABLE,
        sa.column("id", sa.String(36)),
        sa.column("m8f_tenant_id", sa.String(255)),
        sa.column("name", sa.String(255)),
        sa.column("is_sensitive", sa.Boolean()),
        sa.column("value", sa.JSON(none_as_null=True)),
        sa.column("is_configured", sa.Boolean()),
        sa.column("provider_key", sa.String(255)),
        sa.column("created_by_user_id", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    if legacy_secrets:
        bind.execute(
            named_value.insert(),
            [
                {
                    "id": str(uuid.uuid4()),
                    "m8f_tenant_id": row["m8f_tenant_id"],
                    "name": row["key"],
                    "is_sensitive": True,
                    "value": None,
                    "is_configured": True,
                    # Retain the legacy provider key until the explicit Vault
                    # path migration verifies the replacement document.
                    "provider_key": row["key"],
                    "created_by_user_id": row.get("created_by_user_id"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                }
                for row in legacy_secrets
            ],
        )

    connector_variable = sa.table(
        CONNECTOR_VARIABLE_TABLE,
        sa.column("m8f_tenant_id", sa.String(255)),
        sa.column("connector_configuration_id", sa.Integer()),
        sa.column("field_name", sa.String(255)),
        sa.column("is_sensitive", sa.Boolean()),
        sa.column("provider_key", sa.String(255)),
        sa.column("value", sa.JSON(none_as_null=True)),
        sa.column("is_configured", sa.Boolean()),
        sa.column("created_by_user_id", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connector_rows: list[dict[str, Any]] = []
    for profile in legacy_profiles:
        common = {
            "m8f_tenant_id": profile["m8f_tenant_id"],
            "connector_configuration_id": profile["id"],
            "created_by_user_id": profile.get("created_by_user_id"),
            "created_at": profile.get("created_at"),
            "updated_at": profile.get("updated_at"),
        }
        for name, value in profile["config_json"].items():
            connector_rows.append(
                {
                    **common,
                    "field_name": name,
                    "is_sensitive": False,
                    "provider_key": None,
                    "value": value,
                    "is_configured": value is not None,
                }
            )
        for name in profile["secret_refs"]:
            connector_rows.append(
                {
                    **common,
                    "field_name": name,
                    "is_sensitive": True,
                    "provider_key": profile["secret_refs"][name],
                    "value": None,
                    # Presence of a legacy reference is not proof its provider
                    # payload still exists. The explicit backfill verifies it.
                    "is_configured": False,
                }
            )
    if connector_rows:
        bind.execute(connector_variable.insert(), connector_rows)

    _enable_rls(bind, NAMED_VALUE_TABLE, NAMED_VALUE_TENANT_POLICY, NAMED_VALUE_BYPASS_POLICY)
    _enable_rls(
        bind,
        CONNECTOR_VARIABLE_TABLE,
        CONNECTOR_TENANT_POLICY,
        CONNECTOR_BYPASS_POLICY,
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in (NAMED_VALUE_TABLE, CONNECTOR_VARIABLE_TABLE):
        if _table_exists(bind, table):
            count = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
            if count:
                raise RuntimeError(
                    f"Refusing to drop {table}: it contains {count} rows. "
                    "Export and verify those values, or restore a database backup, "
                    "before downgrading."
                )

    if _is_postgres(bind):
        op.execute(sa.text(f"DROP POLICY IF EXISTS {NAMED_VALUE_BYPASS_POLICY} ON {NAMED_VALUE_TABLE}"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {NAMED_VALUE_TENANT_POLICY} ON {NAMED_VALUE_TABLE}"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {CONNECTOR_BYPASS_POLICY} ON {CONNECTOR_VARIABLE_TABLE}"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {CONNECTOR_TENANT_POLICY} ON {CONNECTOR_VARIABLE_TABLE}"))

    op.drop_index("ix_m8flow_connector_variable_tenant", table_name=CONNECTOR_VARIABLE_TABLE)
    op.drop_index(
        "ix_m8flow_connector_variable_tenant_configuration",
        table_name=CONNECTOR_VARIABLE_TABLE,
    )
    op.drop_table(CONNECTOR_VARIABLE_TABLE)
    op.drop_index("ix_m8flow_named_value_tenant", table_name=NAMED_VALUE_TABLE)
    op.drop_index(NAMED_VALUE_NAME_INDEX, table_name=NAMED_VALUE_TABLE)
    op.drop_table(NAMED_VALUE_TABLE)
    op.drop_index(CONNECTOR_PARENT_UNIQUE_INDEX, table_name=CONNECTOR_CONFIGURATION_TABLE)
    with op.batch_alter_table(CONNECTOR_CONFIGURATION_TABLE) as batch:
        batch.drop_column("schema_version")
        batch.drop_column("provider_key")
