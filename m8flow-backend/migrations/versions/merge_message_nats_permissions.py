# SPDX-License-Identifier: Apache-2.0
"""Join the message schema and upstream NATS permission histories."""

revision = "merge_message_nats_permissions"
down_revision = ("merge_message_host_heads", "c7e9a1b3d5f7")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
