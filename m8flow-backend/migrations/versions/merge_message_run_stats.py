# SPDX-License-Identifier: Apache-2.0
"""Join the correlation schema and upstream process run statistics histories."""

revision = "merge_message_run_stats"
down_revision = ("merge_message_nats_permissions", "e9c4b2a71f53")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
