"""Store process-model working copies and published releases."""

from collections.abc import Iterator
from contextlib import contextmanager

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
VERSION_TABLES = (STATE, RELEASE, CALLED_RELEASES)


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
        for table in VERSION_TABLES:
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


@contextmanager
def _import_step(tenant_id: str, operation: str) -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        raise RuntimeError(f"Process model migration failed for tenant {tenant_id!r} while {operation}") from exc


def _import_existing_catalog(bind: sa.Connection) -> None:
    from m8flow_backend.catalog import legacy_model_ids, versions
    from m8flow_backend.workflow import _retire_stale_timer_starts

    inspector = sa.inspect(bind)
    if not inspector.has_table("m8flow_tenant"):
        return
    has_scheduler = inspector.has_table("scheduler_job")
    tenants = bind.execute(sa.text("SELECT id FROM m8flow_tenant ORDER BY id")).scalars().all()
    is_postgres = bind.dialect.name == "postgresql"
    for tenant_id in tenants:
        if is_postgres:
            with _import_step(tenant_id, "setting the tenant context"):
                bind.execute(sa.text("SELECT set_config('app.current_tenant', :tenant_id, true)"), {
                    "tenant_id": tenant_id,
                })
        with Session(bind=bind, autoflush=False, join_transaction_mode="create_savepoint") as session:
            with _import_step(tenant_id, "preparing the tenant import"):
                if is_postgres:
                    # Check after the session's transaction hooks have run.
                    active_tenant = session.connection().scalar(
                        sa.text("SELECT current_setting('app.current_tenant', true)")
                    )
                    if active_tenant != tenant_id:
                        raise RuntimeError("PostgreSQL tenant context does not match the tenant being imported")
                model_ids = legacy_model_ids(tenant_id=tenant_id)
            for model_id in model_ids:
                with _import_step(tenant_id, f"importing model {model_id!r}"):
                    versions.import_legacy(session, tenant_id, model_id)
                    session.flush()
            if has_scheduler:
                with _import_step(tenant_id, "retiring stale timer starts"):
                    _retire_stale_timer_starts(session, tenant_id)
            with _import_step(tenant_id, "releasing the tenant savepoint"):
                # This commits the session's savepoint within Alembic's outer transaction.
                session.commit()


def downgrade() -> None:
    is_postgres = op.get_bind().dialect.name == "postgresql"
    for table in reversed(VERSION_TABLES):
        if is_postgres:
            op.execute(sa.DDL(f"DROP POLICY IF EXISTS tenant_read_all ON {table}"))
            op.execute(sa.DDL(f"DROP POLICY IF EXISTS tenant_scope ON {table}"))
            op.execute(sa.DDL(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
        op.drop_table(table)
