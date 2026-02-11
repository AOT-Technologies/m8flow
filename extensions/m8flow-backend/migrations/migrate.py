import os
from pathlib import Path
from alembic import command
from alembic.config import Config

def upgrade_if_enabled():
    """Upgrade the M8Flow database if the M8FLOW_BACKEND_UPGRADE_DB env var is set."""
    if os.environ.get("M8FLOW_BACKEND_UPGRADE_DB", "").lower() not in ("1", "true", "yes"):
        return

    ini_path = Path(__file__).parent / "alembic.ini"
    if not ini_path.exists():
        raise RuntimeError(f"Alembic ini not found: {ini_path}")

    cfg = Config(str(ini_path))

    # 🔒 Force script_location to the folder containing env.py + versions/
    cfg.set_main_option("script_location", str(ini_path.parent))

    command.upgrade(cfg, "head")
