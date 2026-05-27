"""Temporary intentionally invalid migration for CI failure testing.

Revision ID: k1a2b3c4d5e6
Revises: j1a2b3c4d5e6
Create Date: 2026-05-27
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "k1a2b3c4d5e6"
down_revision = "j1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Intentionally invalid body to fail CI migration validation."""
    this is not valid python


def downgrade() -> None:
    """Intentionally invalid body to fail CI migration validation."""
