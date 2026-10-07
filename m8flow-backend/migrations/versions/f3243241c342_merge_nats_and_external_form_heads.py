"""Join the NATS (M8F-549) and external-form last_error (M8F-538) heads.

The NATS and external-form histories originally had two heads. This revision was
already introduced with ``a1b2c3d4e5f6`` and ``7d4b1e9c3a20`` as parents, so those
parents are intentionally preserved. The later core timestamp-cleanup chain is
joined by the follow-up merge revision ``f4254352d453``; mutating this revision's
ancestry would strand databases already stamped at this revision.

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
