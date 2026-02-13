import logging
import os
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the migrations/ folder is importable when running Alembic from repo root.
MIGRATIONS_DIR = Path(__file__).resolve().parent
if str(MIGRATIONS_DIR) not in sys.path:
    sys.path.insert(0, str(MIGRATIONS_DIR))

M8FLOW_BACKEND_DIR = MIGRATIONS_DIR.parent
SRC_DIR = M8FLOW_BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from m8flow_backend.services import model_override_patch

model_override_patch.apply()

import spiffworkflow_backend.load_database_models  # noqa: F401
from spiffworkflow_backend.models.db import db

config = context.config

# IMPORTANT: Do not call fileConfig(config.config_file_name).
# Let the app's logging configuration (uvicorn-log.yaml) control formatting.
for name in ("alembic", "alembic.runtime.migration"):
    lg = logging.getLogger(name)
    lg.handlers = []
    lg.propagate = True

target_metadata = db.Model.metadata


def get_url():
    """Get the database URL from environment variables."""
    url = os.environ.get("M8FLOW_BACKEND_DATABASE_URI") or os.environ.get("M8FLOW_DATABASE_URI")
    if not url:
        raise RuntimeError("Set M8FLOW_BACKEND_DATABASE_URI or M8FLOW_DATABASE_URI for Alembic.")
    return url


def run_migrations_online():
    """Run migrations in 'online' mode."""
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
