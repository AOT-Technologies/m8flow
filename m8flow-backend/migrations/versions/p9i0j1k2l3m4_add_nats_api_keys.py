"""Add m8flow_nats_api_keys table and drop the legacy m8flow_nats_tokens table.

Full cutover from the legacy single-key-per-tenant model to named, multi-key-per-tenant
NATS API keys. The legacy ``m8flow_nats_tokens`` table is dropped; ``downgrade`` recreates
it in its original (pre-expiry) schema.

Revision ID: p9i0j1k2l3m4
Revises: n7g8h9i0j1k2
Create Date: 2026-07-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "p9i0j1k2l3m4"
down_revision = "n7g8h9i0j1k2"
branch_labels = None
depends_on = None

API_KEYS_TABLE = "m8flow_nats_api_keys"
LEGACY_TOKENS_TABLE = "m8flow_nats_tokens"
API_KEYS_TENANT_INDEX = "ix_m8flow_nats_api_keys_m8f_tenant_id"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade():
    if not _table_exists(API_KEYS_TABLE):
        op.create_table(
            API_KEYS_TABLE,
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
            sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index(
            op.f(API_KEYS_TENANT_INDEX),
            API_KEYS_TABLE,
            ["m8f_tenant_id"],
            unique=False,
        )

    # Drop the legacy single-key-per-tenant table now that named keys replace it.
    if _table_exists(LEGACY_TOKENS_TABLE):
        op.drop_table(LEGACY_TOKENS_TABLE)


def downgrade():
    # Recreate the legacy table in its original (pre-expiry) schema.
    if not _table_exists(LEGACY_TOKENS_TABLE):
        op.create_table(
            LEGACY_TOKENS_TABLE,
            sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
            sa.Column("token", sa.String(length=255), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=False),
            sa.Column("modified_by", sa.String(length=255), nullable=False),
            sa.Column("created_at_in_seconds", sa.Integer(), nullable=False),
            sa.Column("updated_at_in_seconds", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]),
            sa.PrimaryKeyConstraint("m8f_tenant_id"),
            sa.UniqueConstraint("token"),
        )

    if _table_exists(API_KEYS_TABLE):
        op.drop_index(op.f(API_KEYS_TENANT_INDEX), table_name=API_KEYS_TABLE)
        op.drop_table(API_KEYS_TABLE)
