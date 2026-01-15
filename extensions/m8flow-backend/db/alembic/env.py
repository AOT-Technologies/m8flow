from logging.config import fileConfig
import os
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the db/ folder is importable when running Alembic from repo root.
DB_DIR = Path(__file__).resolve().parents[1]
if str(DB_DIR) not in sys.path:
    sys.path.insert(0, str(DB_DIR))

from models import Base

config = context.config
fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url():
    url = os.environ.get("SPIFFWORKFLOW_BACKEND_DATABASE_URI") or os.environ.get(
        "M8FLOW_DATABASE_URI"
    )
    if not url:
        raise RuntimeError(
            "Set SPIFFWORKFLOW_BACKEND_DATABASE_URI or M8FLOW_DATABASE_URI for Alembic."
        )
    return url

def run_migrations_online():
    connectable = engine_from_config(
        {"sqlalchemy.url": get_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version_m8flow",  # <-- important
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()
