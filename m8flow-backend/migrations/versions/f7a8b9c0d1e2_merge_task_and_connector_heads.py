"""Join task-completion and connector-variable migration heads.

The task-completion event migration and connector-variable index migration
were developed on parallel branches. This no-op revision joins their history
without changing either migration's already-published ancestry.
"""

from __future__ import annotations

revision = "f7a8b9c0d1e2"
down_revision = ("d1e2f3a4b5c6", "e3f5a7c9d1b2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
