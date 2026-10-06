"""Join the NATS (M8F-549) and external-form last_error (M8F-538) heads.

The NATS chain and the host/core timestamp-cleanup chain both diverged from the
external-form history, so the chain had multiple heads and ``alembic upgrade head``
refused to run. This merge revision joins the complete current heads. Nothing to do
here; every parent is idempotent.

Revision ID: f3243241c342
Revises: a1b2c3d4e5f6, 7d4b1e9c3a20
"""

from __future__ import annotations

revision = "f3243241c342"
down_revision = ("d4e5f6a7b8c9", "7d4b1e9c3a20")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
