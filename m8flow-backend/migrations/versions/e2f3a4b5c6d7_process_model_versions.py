"""Store process-model working copies and published releases."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

STATE = "m8flow_process_model_state"
RELEASE = "m8flow_process_model_release"
CALLED_RELEASES = "m8flow_process_instance_called_releases"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite" and not bind.connection.driver_connection.in_transaction:
        # sqlite3 legacy transaction mode needs BEGIN before DDL and SAVEPOINT.
        bind.exec_driver_sql("BEGIN")
    op.create_table(
        STATE,
        sa.Column("m8f_tenant_id", sa.String(255), primary_key=True),
        sa.Column("model_id", sa.String(255), primary_key=True),
        sa.Column("generation", sa.String(32), nullable=False),
        sa.Column("working_revision", sa.String(32), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("working", sa.JSON(), nullable=False),
        sa.Column("latest_version", sa.Integer()),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        RELEASE,
        sa.Column("m8f_tenant_id", sa.String(255), primary_key=True),
        sa.Column("model_id", sa.String(255), primary_key=True),
        sa.Column("generation", sa.String(32), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("contents", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("published_by", sa.String(255)),
        if_not_exists=True,
    )
    op.create_table(
        CALLED_RELEASES,
        sa.Column("m8f_tenant_id", sa.String(255), primary_key=True),
        sa.Column("process_instance_id", sa.Integer(), primary_key=True),
        sa.Column("releases", sa.JSON(), nullable=False),
        if_not_exists=True,
    )
    if bind.dialect.name == "postgresql":
        for table in (STATE, RELEASE, CALLED_RELEASES):
            predicate = "m8f_tenant_id = current_setting('app.current_tenant', true)"
            op.execute(sa.DDL(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            op.execute(sa.DDL(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            op.execute(sa.DDL(f"DROP POLICY IF EXISTS tenant_scope ON {table}"))
            op.execute(sa.DDL(f"CREATE POLICY tenant_scope ON {table} USING ({predicate}) WITH CHECK ({predicate})"))
            op.execute(sa.DDL(f"DROP POLICY IF EXISTS tenant_read_all ON {table}"))
            op.execute(sa.DDL(
                f"CREATE POLICY tenant_read_all ON {table} FOR SELECT "
                "USING (current_setting('app.bypass_rls', true) = 'on')"
            ))
    _import_existing_catalog(bind)


def _import_existing_catalog(bind) -> None:
    from m8flow_backend.catalog import legacy_model_ids, versions
    from m8flow_backend.workflow import _retire_stale_timer_starts

    inspector = sa.inspect(bind)
    if not inspector.has_table("m8flow_tenant"):
        return
    has_scheduler = inspector.has_table("scheduler_job")
    tenants = bind.execute(sa.text("SELECT id FROM m8flow_tenant ORDER BY id")).scalars().all()
    for tenant_id in tenants:
        phase = "setting up the tenant import"
        try:
            # Releasing the savepoint leaves the revision under Alembic's outer transaction.
            with Session(bind=bind, autoflush=False, join_transaction_mode="create_savepoint") as session:
                with session.begin():
                    if bind.dialect.name == "postgresql":
                        session.execute(sa.text("SELECT set_config('app.current_tenant', :tenant_id, true)"), {
                            "tenant_id": tenant_id,
                        })
                    phase = "listing legacy process models"
                    for model_id in legacy_model_ids(tenant_id=tenant_id):
                        phase = f"importing model {model_id!r}"
                        versions.import_legacy(session, tenant_id, model_id)
                        session.flush()
                    if has_scheduler:
                        phase = "retiring stale timer starts"
                        _retire_stale_timer_starts(session, tenant_id)
                    phase = "releasing the tenant savepoint"
        except Exception as exc:
            raise RuntimeError(f"Process model migration failed for tenant {tenant_id!r} while {phase}") from exc


def downgrade() -> None:
    op.drop_table(CALLED_RELEASES)
    op.drop_table(RELEASE)
    op.drop_table(STATE)
