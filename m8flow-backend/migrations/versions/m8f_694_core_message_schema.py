"""Install signal and message tables and enforce tenant ownership for journals."""

from __future__ import annotations

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
    # Some deployments already have the signal or message schema from core.
    for name in TABLES:
        Base.metadata.tables[name].create(bind, checkfirst=True)
        _enable_rls(name)
    bind.execute(VERSION.update().where(VERSION.c.version_num == BASELINE).values(version_num=CORE_HEAD))


def downgrade() -> None:
    for name in reversed(TABLES):
        op.drop_table(name)
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
