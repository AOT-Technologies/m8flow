"""Host boot config: permissions already load via identity; templates dir and
SQL echo must be copied from env into the rewrite's own seams (flask config /
create_engine), not left as never-wired overlay helpers."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from m8flow_backend import identity
from m8flow_backend.db import get_engine, reset_engine


def test_packaged_permissions_yml_is_the_import_yaml_default():
    """RBAC is not a live gap: import_yaml's default path is the packaged file,
    independent of the overlay flask-config helper."""
    path = Path(identity.Path_from_package())
    assert path.is_file()
    assert path.name == "m8flow.yml"
    text = path.read_text(encoding="utf-8")
    assert '"editor":' in text
    assert '"reviewer":' in text


def test_create_app_copies_templates_storage_dir_from_env(db_engine, monkeypatch, tmp_path):
    templates = str(tmp_path / "templates")
    monkeypatch.setenv("M8FLOW_TEMPLATES_STORAGE_DIR", templates)
    from m8flow_backend.app import create_app

    application = create_app()
    assert application.app.config.get("M8FLOW_TEMPLATES_STORAGE_DIR") == templates


def test_get_engine_honors_sqlalchemy_echo_env(tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_DATABASE_URI", f"sqlite:///{tmp_path / 'echo.db'}")
    monkeypatch.setenv("M8FLOW_SQLALCHEMY_ECHO", "true")
    reset_engine()
    try:
        assert get_engine().echo is True
    finally:
        reset_engine()


def test_overlay_startup_config_module_is_removed():
    """Dead overlay helpers lived in startup/config.py; the rewrite wires the
    two real concerns (templates dir, SQL echo) at their native seams."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("m8flow_backend.startup.config")
