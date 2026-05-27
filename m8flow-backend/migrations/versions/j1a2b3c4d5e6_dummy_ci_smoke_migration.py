"""Temporary no-op migration for CI validation.

Revision ID: j1a2b3c4d5e6
Revises: i2b3c4d5e6f7
Create Date: 2026-05-27
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "j1a2b3c4d5e6"
down_revision = "i2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op migration used only to exercise CI migration checks."""


def downgrade() -> None:
    """Revert the no-op CI migration."""
