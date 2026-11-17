"""Join process model versioning with the main host migration chain.

To roll back to main's pre-versioning schema, first downgrade to
``fbcad9e02138`` to unmerge, then to ``e2f3a4b5c6d7@d1e2f3a4b5c6``
to remove only the versioning branch. Rolling back drops versioned catalog data.
"""

revision = "9f2c6d4b8e71"
down_revision = ("fbcad9e02138", "e2f3a4b5c6d7")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
