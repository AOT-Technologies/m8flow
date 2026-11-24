"""Merge external message schema and process error timestamp histories."""

revision = "merge_message_error_timestamp"
down_revision = ("merge_message_run_stats", "d8e9f0a1b2c3")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
