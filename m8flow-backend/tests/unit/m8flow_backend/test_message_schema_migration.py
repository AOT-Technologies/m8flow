"""Ownership and exact FK-layout regressions for the core schema handoff."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


# Synthetic historical namespace used only by migration fixtures.
_LEGACY_CORE_MARKER = "m8f_1_message_correlation"


def _revision(name):
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[3] / "migrations"))
    return scripts.get_revision(name).module


@pytest.mark.parametrize("core_marker", ["k2l3m4n5o6p7", "message_correlation", _LEGACY_CORE_MARKER])
@pytest.mark.parametrize("preexisting", [(), ("signal_publication", "message_delivery_receipt"), "all"])
def test_message_downgrade_preserves_adopted_tables_and_receipts(db_engine, preexisting, core_marker):
    from m8flow_core.models import Base

    revision = _revision("core_message_schema")
    if preexisting == "all":
        preexisting = revision.TABLES
    with db_engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        for name in reversed(revision.TABLES):
            Base.metadata.tables[name].drop(connection)
        for name in preexisting:
            Base.metadata.tables[name].create(connection)
        connection.exec_driver_sql("CREATE TABLE m8flow_core_alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        connection.execute(revision.VERSION.insert().values(version_num=core_marker))
        if "message_delivery_receipt" in preexisting:
            connection.execute(Base.metadata.tables["message_delivery_receipt"].insert().values(
                m8f_tenant_id="existing", delivery_id="keep-me", request_digest="a" * 64,
                delivered_at=datetime.now(UTC),
            ))
        revision.upgrade()
        revision.upgrade()  # Replay must not adopt its own tables as pre-existing.
        revision.downgrade()
        remaining = set(sa.inspect(connection).get_table_names())
        assert set(revision.TABLES) & remaining == set(preexisting)
        assert revision.OWNERSHIP.name not in remaining
        if "message_delivery_receipt" in preexisting:
            assert connection.scalar(sa.text("SELECT delivery_id FROM message_delivery_receipt")) == "keep-me"
        assert connection.scalar(sa.select(revision.VERSION.c.version_num)) == revision.BASELINE
        revision.upgrade()
        assert set(revision.TABLES) <= set(sa.inspect(connection).get_table_names())


@pytest.mark.parametrize("missing_provenance", ["ownership-table", "creation-check", "referenced-parent"])
def test_message_downgrade_keeps_tables_without_provenance_or_with_external_references(db_engine, missing_provenance):
    from m8flow_core.models import Base

    revision = _revision("core_message_schema")
    with db_engine.begin() as connection, Operations.context(MigrationContext.configure(connection)) as operations:
        for name in reversed(revision.TABLES):
            Base.metadata.tables[name].drop(connection)
        connection.exec_driver_sql("CREATE TABLE m8flow_core_alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        connection.execute(revision.VERSION.insert().values(version_num=revision.BASELINE))
        revision.upgrade()
        if missing_provenance == "ownership-table":
            operations.drop_table(revision.OWNERSHIP.name)
            expected = set(revision.TABLES)
        elif missing_provenance == "creation-check":
            # A stale row alone cannot claim ownership of a replacement table.
            operations.drop_table("message_delivery_receipt")
            Base.metadata.tables["message_delivery_receipt"].create(connection)
            expected = {"message_delivery_receipt"}
        else:
            connection.exec_driver_sql(
                "CREATE TABLE runtime_reference (publication_id INTEGER REFERENCES signal_publication(id))"
            )
            expected = {"signal_publication"}
        revision.downgrade()
        assert set(revision.TABLES) & set(sa.inspect(connection).get_table_names()) == expected


@pytest.mark.parametrize(
    "layout", ["legacy", "composite", "both", "reordered", "split", "missing-tenant", "extra", "wrong-target"],
)
def test_compensation_adoption_accepts_only_complete_fk_layouts(db_engine, layout):
    revision = _revision("core_message_schema")
    historical = _revision("fa8b9c0d1e2f")
    metadata = sa.MetaData()
    sa.Table("m8flow_tenant", metadata, sa.Column("id", sa.String(255), primary_key=True))
    sa.Table(
        "process_instance", metadata, sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("m8f_tenant_id", sa.String(255)),
    )
    items = historical._journal_definitions()["compensation_scope"]
    table = sa.Table("compensation_scope", metadata, *items)
    for constraint in tuple(table.foreign_key_constraints):
        table.constraints.remove(constraint)
    if layout != "missing-tenant":
        table.append_constraint(sa.ForeignKeyConstraint(["m8f_tenant_id"], ["m8flow_tenant.id"]))
    if layout in {"legacy", "both", "extra"}:
        table.append_constraint(sa.ForeignKeyConstraint(["process_instance_id"], ["process_instance.id"]))
    if layout in {"composite", "both", "missing-tenant", "reordered", "wrong-target"}:
        columns = ["m8f_tenant_id", "process_instance_id"]
        targets = ["process_instance.m8f_tenant_id", "process_instance.id"]
        if layout == "reordered":
            columns.reverse()
            targets.reverse()
        if layout == "wrong-target":
            targets.reverse()
        table.append_constraint(sa.ForeignKeyConstraint(columns, targets))
    if layout == "split":
        table.append_constraint(sa.ForeignKeyConstraint(["m8f_tenant_id"], ["process_instance.m8f_tenant_id"]))
        table.append_constraint(sa.ForeignKeyConstraint(["process_instance_id"], ["process_instance.id"]))
    if layout == "extra":
        table.append_constraint(sa.ForeignKeyConstraint(["scope_id"], ["m8flow_tenant.id"]))
    with db_engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE compensation_scope")
        table.create(connection)
        if layout in {"legacy", "composite", "both", "reordered"}:
            revision._validate_journal_instance_keys(sa.inspect(connection), "compensation_scope")
        else:
            with pytest.raises(RuntimeError, match="expected foreign keys"):
                revision._validate_journal_instance_keys(sa.inspect(connection), "compensation_scope")
