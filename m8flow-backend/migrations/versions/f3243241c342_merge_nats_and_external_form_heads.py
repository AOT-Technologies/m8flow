"""Join the NATS (M8F-549) and external-form last_error (M8F-538) heads.

Both branches were cut from the root revision 1518b05122bc, so the chain had two heads
and ``alembic upgrade head`` refused to run. A merge revision, not re-parenting
2c7e9a41d5f3, so a database already stamped at either head upgrades correctly: one at
7d4b1e9c3a20 still gets a1b2c3d4e5f6, and one at a1b2c3d4e5f6 still gets the NATS
revisions. Nothing to do here; every parent is idempotent.

Revision ID: f3243241c342
Revises: a1b2c3d4e5f6, 7d4b1e9c3a20
"""

from __future__ import annotations

revision = "f3243241c342"
down_revision = ("a1b2c3d4e5f6", "7d4b1e9c3a20")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
