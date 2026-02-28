# extensions/startup/migrations.py
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Callable

from extensions.startup.logging_setup import harden_logging

logger = logging.getLogger(__name__)


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "m8flow-backend" / "migrations"


def _ensure_migrations_importable() -> None:
    migrations_dir = _migrations_dir()
    migrations_dir_str = str(migrations_dir)
    if migrations_dir_str not in sys.path:
        sys.path.insert(0, migrations_dir_str)


def load_migration_runner() -> Callable[[], None]:
    _ensure_migrations_importable()
    try:
        from migrate import upgrade_if_enabled
        return upgrade_if_enabled
    except ModuleNotFoundError:
        # fallback: load migrate.py directly
        migrations_dir = _migrations_dir()
        migrate_path = migrations_dir / "migrate.py"
        spec = importlib.util.spec_from_file_location("m8flow_migrate", migrate_path)
        if spec is None or spec.loader is None:
            raise
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.upgrade_if_enabled

def run_migrations_if_enabled(flask_app, upgrade_fn: Callable[[], None]) -> None:
    harden_logging()
    from extensions.startup.flask_hooks import assert_db_engine_bound
    assert_db_engine_bound(flask_app)
    upgrade_fn()
