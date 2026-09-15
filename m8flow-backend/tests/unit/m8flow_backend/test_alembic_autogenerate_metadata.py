"""Alembic autogenerate must diff host tables as well as core tables.

The historical bug: migrations/env.py built a combined target_metadata list
but passed only CoreBase.metadata into context.configure, so
`alembic revision --autogenerate` never saw HostBase tables. Host models that
live outside models/native.py (external-form requests, tenant invitations) were
a second miss: they never even registered on HostBase.metadata.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from m8flow_backend.db import alembic_target_metadata

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_ENV_PY = _BACKEND_ROOT / "migrations" / "env.py"

# Host tables that live outside models/native.py — the ones a native-only
# import would silently drop from autogenerate.
_HOST_TABLES_OUTSIDE_NATIVE = (
    "m8flow_external_form_requests",
    "m8flow_tenant_invitation",
    "m8flow_connector_configuration",
)
_HOST_TABLE_IN_NATIVE = "secret"


def _compact_source(path: Path) -> str:
    return "".join(path.read_text(encoding="utf-8").split())


def test_env_py_configure_does_not_pin_autogenerate_to_core_metadata_only():
    """The configure() call must not hardcode CoreBase.metadata (the bug)."""
    compact = _compact_source(_ENV_PY)
    assert "version_table=\"alembic_version_m8flow\"" in compact or "version_table='alembic_version_m8flow'" in compact
    assert "compare_type=True" in compact
    assert "target_metadata=CoreBase.metadata" not in compact


def test_alembic_target_metadata_includes_host_tables_outside_native():
    metadatas = alembic_target_metadata()
    table_names = {name for md in metadatas for name in md.tables}
    for table in (*_HOST_TABLES_OUTSIDE_NATIVE, _HOST_TABLE_IN_NATIVE):
        assert table in table_names


def test_autogenerate_against_empty_db_proposes_creating_host_tables(tmp_path):
    """Behavioral check: autogenerate with the combined metadata notices host tables."""
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diffs = compare_metadata(context, alembic_target_metadata())

    proposed_create = set()
    for diff in diffs:
        # compare_metadata yields (directive, object) pairs; add_table carries the Table.
        if not isinstance(diff, tuple) or len(diff) < 2:
            continue
        if diff[0] == "add_table":
            proposed_create.add(diff[1].name)

    for table in (*_HOST_TABLES_OUTSIDE_NATIVE, _HOST_TABLE_IN_NATIVE):
        assert table in proposed_create


def test_broken_in_app_startup_runner_is_removed():
    """The overlay wrapper (flask_hooks + never-wired create_app hook) is
    retired. Boot migrations stay on bin/run_m8flow_backend.sh; the
    programmatic gate stays on migrations/migrate.py."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("m8flow_backend.startup.migrations")
