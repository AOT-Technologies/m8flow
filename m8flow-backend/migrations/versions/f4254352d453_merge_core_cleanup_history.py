"""Join the preserved merge revision with the core cleanup chain.

``f3243241c342`` was deployed with the NATS and external-form parents. Keep
that revision's ancestry immutable and use this follow-up merge to include the
core timestamp-cleanup revision. This also repairs databases that were already
stamped at ``f3243241c342`` before the cleanup branch was added.
"""

from __future__ import annotations

revision = "f4254352d453"
down_revision = ("f3243241c342", "d4e5f6a7b8c9")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
