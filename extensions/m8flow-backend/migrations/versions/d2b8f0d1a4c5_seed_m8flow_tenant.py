"""Seed the base m8flow tenant row.

Revision ID: d2b8f0d1a4c5
Revises: b8837274af96
Create Date: 2026-03-20
"""

from __future__ import annotations

import time

from alembic import op
import sqlalchemy as sa


revision = "d2b8f0d1a4c5"
down_revision = "b8837274af96"
branch_labels = None
depends_on = None


TENANT_ID = "m8flow"
TENANT_SLUG = "m8flow"
TENANT_NAME = "M8Flow Realm"


def _tenant_exists(bind: sa.Connection, tenant_id: str) -> bool:
    return (
        bind.execute(
            sa.text("SELECT 1 FROM m8flow_tenant WHERE id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar()
        is not None
    )


def _tenant_id_for_slug(bind: sa.Connection, slug: str) -> str | None:
    return bind.execute(
        sa.text("SELECT id FROM m8flow_tenant WHERE slug = :tenant_slug"),
        {"tenant_slug": slug},
    ).scalar()


def upgrade() -> None:
    bind = op.get_bind()

    if _tenant_exists(bind, TENANT_ID):
        return

    slug_owner = _tenant_id_for_slug(bind, TENANT_SLUG)
    if slug_owner is not None and slug_owner != TENANT_ID:
        raise RuntimeError(
            f"Cannot seed tenant '{TENANT_ID}': slug '{TENANT_SLUG}' already belongs to tenant '{slug_owner}'."
        )

    now = int(time.time())
    bind.execute(
        sa.text(
            """
            INSERT INTO m8flow_tenant (
                id,
                name,
                slug,
                created_by,
                modified_by,
                created_at_in_seconds,
                updated_at_in_seconds
            )
            VALUES (
                :tenant_id,
                :tenant_name,
                :tenant_slug,
                :created_by,
                :modified_by,
                :created_at,
                :updated_at
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "tenant_id": TENANT_ID,
            "tenant_name": TENANT_NAME,
            "tenant_slug": TENANT_SLUG,
            "created_by": "system",
            "modified_by": "system",
            "created_at": now,
            "updated_at": now,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM m8flow_tenant
            WHERE id = :tenant_id
              AND slug = :tenant_slug
              AND name = :tenant_name
            """
        ),
        {
            "tenant_id": TENANT_ID,
            "tenant_slug": TENANT_SLUG,
            "tenant_name": TENANT_NAME,
        },
    )
