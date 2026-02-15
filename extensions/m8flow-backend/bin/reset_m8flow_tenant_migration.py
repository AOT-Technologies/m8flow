#!/usr/bin/env python3
"""Reset M8Flow migration version to 0001 so 0002 re-runs and adds tenant columns.
Used when m8flow migrations ran before SpiffWorkflow tables existed.
Reads M8FLOW_BACKEND_DATABASE_URI from environment."""
import os
import sqlalchemy as sa

db_uri = os.environ.get("M8FLOW_BACKEND_DATABASE_URI", "")
if not db_uri:
    print("M8FLOW_BACKEND_DATABASE_URI not set, skipping tenant migration reset.")
    exit(0)

engine = sa.create_engine(db_uri)
with engine.connect() as conn:
    # Skip if m8flow version table not yet created (e.g. first run)
    version_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'alembic_version_m8flow'"
        )
    ).scalar() is not None
    if not version_exists:
        print("alembic_version_m8flow not present, skipping reset.")
        exit(0)

    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'message_instance' AND column_name = 'm8f_tenant_id'"
        )
    )
    has_tenant_col = result.scalar() is not None
    if not has_tenant_col:
        conn.execute(sa.text("UPDATE alembic_version_m8flow SET version_num = '0001'"))
        conn.commit()
        print("Reset m8flow migration version to 0001")
    else:
        print("Tenant columns already exist, no reset needed")
