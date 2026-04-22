from alembic import op
import sqlalchemy as sa
import time

from m8flow_backend.tenancy import DEFAULT_TENANT_ID

revision = "f6a7b8c9d0e1"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "pkce_code_verifier",
    "configuration",
    "refresh_token",
    "typeahead",
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _column_exists(table: str, column: str) -> bool:
    insp = _inspector()
    return column in [c["name"] for c in insp.get_columns(table)]


def _index_exists(table: str, index_name: str) -> bool:
    insp = _inspector()
    return any(idx["name"] == index_name for idx in insp.get_indexes(table))


def _fk_names_for_column(table: str, column: str) -> list[str]:
    insp = _inspector()
    names = []
    for fk in insp.get_foreign_keys(table):
        if column in fk.get("constrained_columns", []):
            if fk.get("name"):
                names.append(fk["name"])
    return names


def _drop_unique_by_columns(table: str, columns: list[str]) -> None:
    insp = _inspector()
    for uc in insp.get_unique_constraints(table):
        if uc.get("column_names") == columns:
            op.drop_constraint(uc["name"], table, type_="unique")
    for idx in insp.get_indexes(table):
        if idx.get("unique") and idx.get("column_names") == columns:
            op.drop_index(idx["name"], table_name=table)


def _drop_unique_by_name(table: str, name: str) -> None:
    insp = _inspector()
    for uc in insp.get_unique_constraints(table):
        if uc.get("name") == name:
            op.drop_constraint(name, table, type_="unique")


def _ensure_rls(table: str) -> None:
    policy_name = f"{table}_tenant_isolation"
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {policy_name} ON {table} "
            "USING (m8f_tenant_id = current_setting('app.current_tenant', true)) "
            "WITH CHECK (m8f_tenant_id = current_setting('app.current_tenant', true))"
        )
    )


def _get_backfill_tenant_id() -> str:
    conn = op.get_bind()
    now = round(time.time())
    conn.execute(
        sa.text(
            "INSERT INTO m8flow_tenant "
            "(id, name, slug, created_by, modified_by, created_at_in_seconds, updated_at_in_seconds) "
            "VALUES (:tenant_id, :tenant_name, :tenant_slug, :created_by, :modified_by, :created_at, :updated_at) "
            "ON CONFLICT (id) DO NOTHING"
        ).bindparams(
            tenant_id=DEFAULT_TENANT_ID,
            tenant_name=DEFAULT_TENANT_ID,
            tenant_slug=DEFAULT_TENANT_ID,
            created_by="system",
            modified_by="system",
            created_at=now,
            updated_at=now,
        )
    )
    tenant_id = conn.execute(
        sa.text("SELECT id FROM m8flow_tenant WHERE id = :tenant_id").bindparams(
            tenant_id=DEFAULT_TENANT_ID
        )
    ).scalar()
    if tenant_id != DEFAULT_TENANT_ID:
        raise RuntimeError(
            "Missing default tenant. Insert id='default' into m8flow_tenant before applying this migration."
        )
    return tenant_id


def upgrade() -> None:
    tenant_id = _get_backfill_tenant_id()

    for table in TENANT_TABLES:
        if not _column_exists(table, "m8f_tenant_id"):
            with op.batch_alter_table(table) as batch_op:
                batch_op.add_column(sa.Column("m8f_tenant_id", sa.String(255), nullable=True))

        op.execute(
            sa.text(f"UPDATE {table} SET m8f_tenant_id = :tenant_id WHERE m8f_tenant_id IS NULL")
            .bindparams(tenant_id=tenant_id)
        )

        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("m8f_tenant_id", nullable=False)

        fk_name = f"{table}_m8f_tenant_id_fkey"
        if not _fk_names_for_column(table, "m8f_tenant_id"):
            op.create_foreign_key(
                fk_name,
                table,
                "m8flow_tenant",
                ["m8f_tenant_id"],
                ["id"],
                ondelete="RESTRICT",
            )

        index_name = f"ix_{table}_m8f_tenant_id"
        if not _index_exists(table, index_name):
            op.create_index(index_name, table, ["m8f_tenant_id"])

        if _is_postgres():
            _ensure_rls(table)

    _drop_unique_by_columns("pkce_code_verifier", ["pkce_id"])
    _drop_unique_by_name("pkce_code_verifier", "pkce_code_verifier_pkce_id_tenant_unique")
    op.create_unique_constraint(
        "pkce_code_verifier_pkce_id_tenant_unique",
        "pkce_code_verifier",
        ["m8f_tenant_id", "pkce_id"],
    )

    _drop_unique_by_columns("refresh_token", ["user_id"])
    _drop_unique_by_name("refresh_token", "refresh_token_user_id_tenant_unique")
    op.create_unique_constraint(
        "refresh_token_user_id_tenant_unique",
        "refresh_token",
        ["m8f_tenant_id", "user_id"],
    )


def downgrade() -> None:
    if _is_postgres():
        for table in TENANT_TABLES:
            if not _column_exists(table, "m8f_tenant_id"):
                continue
            policy_name = f"{table}_tenant_isolation"
            op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {table}"))
            op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))

    _drop_unique_by_name("refresh_token", "refresh_token_user_id_tenant_unique")
    _drop_unique_by_columns("refresh_token", ["m8f_tenant_id", "user_id"])
    op.create_unique_constraint(
        "refresh_token_user_id_unique",
        "refresh_token",
        ["user_id"],
    )

    _drop_unique_by_name("pkce_code_verifier", "pkce_code_verifier_pkce_id_tenant_unique")
    _drop_unique_by_columns("pkce_code_verifier", ["m8f_tenant_id", "pkce_id"])
    op.create_unique_constraint(
        "pkce_code_verifier_pkce_id_unique",
        "pkce_code_verifier",
        ["pkce_id"],
    )

    for table in TENANT_TABLES:
        index_name = f"ix_{table}_m8f_tenant_id"
        if _index_exists(table, index_name):
            op.drop_index(index_name, table_name=table)

        for fk_name in _fk_names_for_column(table, "m8f_tenant_id"):
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_constraint(fk_name, type_="foreignkey")

        if _column_exists(table, "m8f_tenant_id"):
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_column("m8f_tenant_id")
