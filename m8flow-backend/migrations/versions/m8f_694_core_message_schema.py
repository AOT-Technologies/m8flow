"""Install signal and message tables and enforce tenant ownership for journals."""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision = "m8f_694_core_message_schema"
down_revision = "fbcad9e02138"
branch_labels = None
depends_on = None

BASELINE = "k2l3m4n5o6p7"
CORE_HEAD = "m8f_694_message_correlation"
VERSION = sa.table("m8flow_core_alembic_version", sa.column("version_num"))
TABLES = (
    "signal_registry_state", "signal_publication", "signal_subscription", "signal_delivery",
    "message_subscription", "message_delivery_receipt",
)
JOURNAL_TABLES = ("compensation_scope", "compensation_run", "compensation_record")
PARENT_INDEXES = {
    "process_instance": "m8f_process_instance_tenant_id_key",
    "bpmn_process_definition": "m8f_definition_tenant_id_key",
}
OWNERSHIP = sa.table(
    "m8flow_m8f_694_message_ownership",
    sa.column("table_name", sa.String(63)),
    sa.column("creation_marker", sa.String(63)),
)


def _create_owned_tables(bind: sa.Connection, metadata: sa.MetaData) -> None:
    if not sa.inspect(bind).has_table(OWNERSHIP.name):
        # Start SQLite's write transaction before DDL so provenance is atomic.
        bind.execute(VERSION.update().where(sa.false()).values(version_num=BASELINE))
        op.create_table(
            OWNERSHIP.name,
            sa.Column("table_name", sa.String(63), primary_key=True),
            sa.Column("creation_marker", sa.String(63), nullable=False),
        )
        bind.execute(OWNERSHIP.insert().values(table_name=OWNERSHIP.name, creation_marker=revision))

    # Work on copies: ownership checks must not change the installed core ORM.
    copies = sa.MetaData()
    for table in metadata.tables.values():
        table.to_metadata(copies)
    for name in TABLES:
        if not sa.inspect(bind).has_table(name):
            marker = f"ck_m8f_694_{uuid4().hex}"
            bind.execute(OWNERSHIP.delete().where(OWNERSHIP.c.table_name == name))
            table = copies.tables[name]
            table.append_constraint(sa.CheckConstraint("m8f_tenant_id IS NOT NULL", name=marker))
            table.create(bind)
            bind.execute(OWNERSHIP.insert().values(table_name=name, creation_marker=marker))
        _enable_rls(name)


def _drop_owned_tables(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(OWNERSHIP.name):
        return  # Older installations have no provenance; keep their shared tables.
    markers = dict(bind.execute(sa.select(OWNERSHIP)).tuples().all())
    owned = {
        name for name in TABLES
        if markers.get(name) and inspector.has_table(name)
        and any(check["name"] == markers[name] for check in inspector.get_check_constraints(name))
    }
    # An adopted table (or another runtime table) can reference a table created
    # here. Retain all such dependencies rather than cascade or break its FKs.
    references = {
        name: {
            key["referred_table"] for key in inspector.get_foreign_keys(name)
            if key.get("referred_schema") in (None, inspector.default_schema_name)
        }
        for name in inspector.get_table_names()
    }
    while protected := set().union(*(targets for name, targets in references.items() if name not in owned)) & owned:
        owned -= protected
    for name in reversed(TABLES):
        if name in owned:
            op.drop_table(name)
            bind.execute(OWNERSHIP.delete().where(OWNERSHIP.c.table_name == name))
    if markers.get(OWNERSHIP.name) == revision:
        op.drop_table(OWNERSHIP.name)


def _enable_rls(table: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    quote = bind.dialect.identifier_preparer.quote
    target = quote(table)
    tenant_policy = quote(f"{table}_tenant_isolation")
    bypass_policy = quote(f"{table}_super_admin_select")
    tenant = "(m8f_tenant_id = current_setting('app.current_tenant', true))"
    bypass = "(current_setting('app.bypass_rls', true) = 'on')"
    op.execute(sa.DDL(f"ALTER TABLE {target} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {tenant_policy} ON {target}"))
    op.execute(sa.DDL(
        f"CREATE POLICY {tenant_policy} ON {target} FOR ALL USING {tenant} WITH CHECK {tenant}"
    ))
    op.execute(sa.DDL(f"DROP POLICY IF EXISTS {bypass_policy} ON {target}"))
    op.execute(sa.DDL(
        f"CREATE POLICY {bypass_policy} ON {target} FOR SELECT USING {bypass}"
    ))


def _journal_instance_key(table: str) -> str:
    return f"m8f_{table}_tenant_instance_fk"


def _upgrade_journal_instance_keys() -> None:
    tenant_instance = ["m8f_tenant_id", "process_instance_id"]
    inspector = sa.inspect(op.get_bind())
    for table in JOURNAL_TABLES:
        if any(
            key["constrained_columns"] == tenant_instance
            and key["referred_table"] == "process_instance"
            and key["referred_columns"] == ["m8f_tenant_id", "id"]
            for key in inspector.get_foreign_keys(table)
        ):
            continue
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                _journal_instance_key(table), "process_instance", tenant_instance, ["m8f_tenant_id", "id"]
            )


def upgrade() -> None:
    from m8flow_core.models import Base

    bind = op.get_bind()
    if not all(name in Base.metadata.tables for name in TABLES):
        raise RuntimeError("Install the m8flow-core build with message correlation before upgrading.")
    markers = bind.execute(sa.select(VERSION.c.version_num)).scalars().all()
    if markers not in ([BASELINE], [CORE_HEAD]):
        raise RuntimeError(f"Unexpected m8flow-core migration marker: {markers!r}")

    inspector = sa.inspect(bind)
    for table, name in PARENT_INDEXES.items():
        if not any(index["name"] == name for index in inspector.get_indexes(table)):
            op.create_index(name, table, ["m8f_tenant_id", "id"], unique=True)
    _upgrade_journal_instance_keys()
    # Adopt core-installed tables without claiming ownership of them.
    _create_owned_tables(bind, Base.metadata)
    bind.execute(VERSION.update().where(VERSION.c.version_num == BASELINE).values(version_num=CORE_HEAD))


def downgrade() -> None:
    _drop_owned_tables(op.get_bind())
    inspector = sa.inspect(op.get_bind())
    for table in JOURNAL_TABLES:
        name = _journal_instance_key(table)
        if any(key["name"] == name for key in inspector.get_foreign_keys(table)):
            with op.batch_alter_table(table) as batch:
                batch.drop_constraint(name, type_="foreignkey")
    # The shared indexes also support core's native compensation journal foreign keys.
    op.get_bind().execute(
        VERSION.update().where(VERSION.c.version_num == CORE_HEAD).values(version_num=BASELINE)
    )
