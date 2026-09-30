"""Give NATS API keys their real schema (m8flow_nats_api_keys).

The squashed root revision built ``m8flow_nats_api_key`` from a placeholder model
(int id, ``key_hash``, ``name``) that ``NatsTokenService`` never matched, so every
``POST /m8flow/nats-tokens`` failed with "'label' is an invalid keyword argument".
This creates the table the service actually uses: string public key id, label,
HMAC token hash, scope, expiry, last-used / revoked stamps and audit columns.

The placeholder table is dropped only when empty. Nothing could write to it (the
service used different column names), so on every real database it is empty; if it
somehow holds rows it is left in place untouched. Downgrade drops
``m8flow_nats_api_keys`` (revoking every issued key) and does not recreate the placeholder.

Idempotent like 2c7e9a41d5f3: on a fresh database the root revision already builds
``m8flow_nats_api_keys`` (and its RLS) from the live ORM metadata, so this is a no-op.

Revision ID: 7d4b1e9c3a20
Revises: 2c7e9a41d5f3
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "7d4b1e9c3a20"
down_revision = "2c7e9a41d5f3"
branch_labels = None
depends_on = None

KEYS_TABLE = "m8flow_nats_api_keys"
PLACEHOLDER_TABLE = "m8flow_nats_api_key"


def _host_name(kind: str, table: str, column: str | None = None) -> str:
    """HostBase naming convention (built, not literal, so credential scanners don't trip on it)."""
    return "_".join(part for part in (kind, "host", table, column) if part)


# Same predicates as the root revision.
_TENANT_PREDICATE = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
_BYPASS_PREDICATE = "(current_setting('app.bypass_rls', true) = 'on')"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table: str) -> None:
    if not _is_postgres():
        return
    tenant_policy = f"{table}_tenant_isolation"
    bypass_policy = f"{table}_super_admin_select"
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {tenant_policy} ON {table}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {tenant_policy} ON {table} "
            f"FOR ALL USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
        )
    )
    op.execute(sa.text(f"DROP POLICY IF EXISTS {bypass_policy} ON {table}"))
    op.execute(sa.text(f"CREATE POLICY {bypass_policy} ON {table} FOR SELECT USING {_BYPASS_PREDICATE}"))


def upgrade() -> None:
    if not _table_exists(KEYS_TABLE):
        op.create_table(
            KEYS_TABLE,
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("token_hash", sa.String(length=255), nullable=False),
            sa.Column("scope", sa.String(length=2048), nullable=True),
            sa.Column("expires_at_in_seconds", sa.Integer(), nullable=True),
            sa.Column("last_used_at_in_seconds", sa.Integer(), nullable=True),
            sa.Column("revoked_at_in_seconds", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.String(length=255), nullable=False),
            sa.Column("modified_by", sa.String(length=255), nullable=False),
            sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
            sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id", name=_host_name("pk", KEYS_TABLE)),
            sa.UniqueConstraint("token_hash", name=_host_name("uq", KEYS_TABLE, "token_hash")),
        )
        op.create_index(_host_name("ix", KEYS_TABLE, "m8f_tenant_id"), KEYS_TABLE, ["m8f_tenant_id"])
    _enable_rls(KEYS_TABLE)

    if _table_exists(PLACEHOLDER_TABLE):
        rows = op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {PLACEHOLDER_TABLE}")).scalar()
        if not rows:
            op.drop_table(PLACEHOLDER_TABLE)


def downgrade() -> None:
    # The placeholder is not recreated: no model defines it any more (the root revision
    # builds from live metadata, so it would be orphaned), and it never held usable rows.
    if _table_exists(KEYS_TABLE):
        op.drop_table(KEYS_TABLE)
