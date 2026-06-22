"""Align RBAC schema with m8flow_bpmn_core revision 9d3a7f6c2b41.

Revision ID: k4d5e6f7a8b9
Revises: j2b3c4d5e6f8
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "k4d5e6f7a8b9"
down_revision = "j2b3c4d5e6f8"
branch_labels = None
depends_on = None

PERMISSION_TARGET_TABLE = "permission_target"
PERMISSION_TARGET_BACKUP = "permission_target__rbac_compat_old"
PERMISSION_TARGET_DOWNGRADE_BACKUP = "permission_target__rbac_compat_new"
PERMISSION_TARGET_UNIQUE = "permission_target_uri_command_unique"

USER_GROUP_ASSIGNMENT_TABLE = "user_group_assignment"
USER_GROUP_ASSIGNMENT_UNIQUE = "user_group_assignment_unique"

PRINCIPAL_TABLE = "principal"
PRINCIPAL_BACKUP = "principal__rbac_compat_old"
PRINCIPAL_DOWNGRADE_BACKUP = "principal__rbac_compat_new"
PRINCIPAL_EXACTLY_ONE_SUBJECT = "principal_exactly_one_subject"

PERMISSION_ASSIGNMENT_TABLE = "permission_assignment"
PERMISSION_ASSIGNMENT_BACKUP = "permission_assignment__rbac_compat_old"
PERMISSION_ASSIGNMENT_DOWNGRADE_BACKUP = "permission_assignment__rbac_compat_new"
PERMISSION_ASSIGNMENT_UNIQUE = "permission_assignment_unique"
LEGACY_PERMISSION_ASSIGNMENT_UNIQUE = "permission_assignment_uniq"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _index_exists(table_name: str, columns: list[str], *, unique: bool | None = None) -> bool:
    for index in _inspector().get_indexes(table_name):
        if list(index.get("column_names") or []) != columns:
            continue
        if unique is None or bool(index.get("unique")) is unique:
            return True
    return False


def _unique_exists(table_name: str, columns: list[str], *, name: str | None = None) -> bool:
    for constraint in _inspector().get_unique_constraints(table_name):
        if list(constraint.get("column_names") or []) != columns:
            continue
        if name is None or constraint.get("name") == name:
            return True
    return False


def _check_exists(table_name: str, name: str) -> bool:
    try:
        constraints = _inspector().get_check_constraints(table_name)
    except NotImplementedError:
        return False
    return any(constraint.get("name") == name for constraint in constraints)


def _foreign_key_exists(
    table_name: str,
    constrained_columns: list[str],
    referred_table: str,
    referred_columns: list[str],
) -> bool:
    for foreign_key in _inspector().get_foreign_keys(table_name):
        if foreign_key.get("referred_table") != referred_table:
            continue
        if list(foreign_key.get("constrained_columns") or []) != constrained_columns:
            continue
        if list(foreign_key.get("referred_columns") or []) != referred_columns:
            continue
        return True
    return False


def _scalar(statement: str) -> object | None:
    return op.get_bind().execute(sa.text(statement)).scalar()


def _principal_has_incompatible_rows(table_name: str) -> bool:
    result = _scalar(
        f"""
        SELECT id
        FROM "{table_name}"
        WHERE NOT (
            (user_id IS NOT NULL AND group_id IS NULL)
            OR (user_id IS NULL AND group_id IS NOT NULL)
        )
        LIMIT 1
        """
    )
    return result is not None


def _permission_target_has_duplicate_uris(table_name: str) -> bool:
    result = _scalar(
        f"""
        SELECT uri
        FROM "{table_name}"
        GROUP BY uri
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    )
    return result is not None


def _assert_no_backup_tables(*table_names: str) -> None:
    existing = [table_name for table_name in table_names if _table_exists(table_name)]
    if existing:
        raise RuntimeError(
            "RBAC compatibility migration cannot proceed because backup tables already exist: "
            + ", ".join(existing)
        )


def _drop_indexes(table_name: str) -> None:
    unique_constraint_names = {
        constraint.get("name")
        for constraint in _inspector().get_unique_constraints(table_name)
        if constraint.get("name")
    }
    for index in _inspector().get_indexes(table_name):
        index_name = index.get("name")
        if index_name and index_name not in unique_constraint_names:
            op.drop_index(index_name, table_name=table_name)


def _reset_postgres_sequence(table_name: str) -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    connection.execute(
        sa.text(
            f"""
            SELECT setval(
                pg_get_serial_sequence('{table_name}', 'id'),
                COALESCE((SELECT MAX(id) FROM "{table_name}"), 1),
                EXISTS(SELECT 1 FROM "{table_name}")
            )
            """
        )
    )


def _permission_target_is_compatible() -> bool:
    if not _table_exists(PERMISSION_TARGET_TABLE):
        return False
    if _column_names(PERMISSION_TARGET_TABLE) != {"id", "uri", "command"}:
        return False
    if not _unique_exists(PERMISSION_TARGET_TABLE, ["uri", "command"], name=PERMISSION_TARGET_UNIQUE):
        return False
    if _unique_exists(PERMISSION_TARGET_TABLE, ["uri"]):
        return False
    if not _index_exists(PERMISSION_TARGET_TABLE, ["uri"]):
        return False
    if not _index_exists(PERMISSION_TARGET_TABLE, ["command"]):
        return False
    return True


def _principal_is_compatible() -> bool:
    if not _table_exists(PRINCIPAL_TABLE):
        return False
    if _column_names(PRINCIPAL_TABLE) != {"id", "user_id", "group_id"}:
        return False
    if not _check_exists(PRINCIPAL_TABLE, PRINCIPAL_EXACTLY_ONE_SUBJECT):
        return False
    if not _foreign_key_exists(PRINCIPAL_TABLE, ["user_id"], "user", ["id"]):
        return False
    if not _foreign_key_exists(PRINCIPAL_TABLE, ["group_id"], "group", ["id"]):
        return False
    if not _index_exists(PRINCIPAL_TABLE, ["user_id"], unique=True):
        return False
    if not _index_exists(PRINCIPAL_TABLE, ["group_id"], unique=True):
        return False
    return True


def _permission_assignment_is_compatible() -> bool:
    if not _table_exists(PERMISSION_ASSIGNMENT_TABLE):
        return False
    if _column_names(PERMISSION_ASSIGNMENT_TABLE) != {
        "id",
        "principal_id",
        "permission_target_id",
        "grant_type",
        "permission",
    }:
        return False
    if not _foreign_key_exists(PERMISSION_ASSIGNMENT_TABLE, ["principal_id"], PRINCIPAL_TABLE, ["id"]):
        return False
    if not _foreign_key_exists(PERMISSION_ASSIGNMENT_TABLE, ["permission_target_id"], PERMISSION_TARGET_TABLE, ["id"]):
        return False
    if not _unique_exists(
        PERMISSION_ASSIGNMENT_TABLE,
        ["principal_id", "permission_target_id", "permission"],
        name=PERMISSION_ASSIGNMENT_UNIQUE,
    ):
        return False
    if not _index_exists(PERMISSION_ASSIGNMENT_TABLE, ["principal_id"]):
        return False
    if not _index_exists(PERMISSION_ASSIGNMENT_TABLE, ["permission_target_id"]):
        return False
    return True


def _user_group_assignment_is_compatible() -> bool:
    if not _table_exists(USER_GROUP_ASSIGNMENT_TABLE):
        return False
    if _column_names(USER_GROUP_ASSIGNMENT_TABLE) != {"id", "user_id", "group_id"}:
        return False
    if not _foreign_key_exists(USER_GROUP_ASSIGNMENT_TABLE, ["user_id"], "user", ["id"]):
        return False
    if not _foreign_key_exists(USER_GROUP_ASSIGNMENT_TABLE, ["group_id"], "group", ["id"]):
        return False
    if not _unique_exists(
        USER_GROUP_ASSIGNMENT_TABLE,
        ["user_id", "group_id"],
        name=USER_GROUP_ASSIGNMENT_UNIQUE,
    ):
        return False
    if not _index_exists(USER_GROUP_ASSIGNMENT_TABLE, ["user_id"]):
        return False
    if not _index_exists(USER_GROUP_ASSIGNMENT_TABLE, ["group_id"]):
        return False
    return True


def _core_tables_need_upgrade() -> bool:
    return not (
        _permission_target_is_compatible()
        and _principal_is_compatible()
        and _permission_assignment_is_compatible()
    )


def _create_permission_target_table() -> None:
    op.create_table(
        PERMISSION_TARGET_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uri", sa.String(length=255), nullable=False),
        sa.Column("command", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uri", "command", name=PERMISSION_TARGET_UNIQUE),
    )
    op.create_index("ix_permission_target_uri", PERMISSION_TARGET_TABLE, ["uri"], unique=False)
    op.create_index("ix_permission_target_command", PERMISSION_TARGET_TABLE, ["command"], unique=False)


def _create_principal_table() -> None:
    op.create_table(
        PRINCIPAL_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND group_id IS NULL) OR (user_id IS NULL AND group_id IS NOT NULL)",
            name=PRINCIPAL_EXACTLY_ONE_SUBJECT,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["group.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_principal_user_id", PRINCIPAL_TABLE, ["user_id"], unique=True)
    op.create_index("ix_principal_group_id", PRINCIPAL_TABLE, ["group_id"], unique=True)


def _create_permission_assignment_table(unique_name: str) -> None:
    op.create_table(
        PERMISSION_ASSIGNMENT_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("principal_id", sa.Integer(), nullable=False),
        sa.Column("permission_target_id", sa.Integer(), nullable=False),
        sa.Column("grant_type", sa.String(length=50), nullable=False),
        sa.Column("permission", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(["permission_target_id"], [f"{PERMISSION_TARGET_TABLE}.id"]),
        sa.ForeignKeyConstraint(["principal_id"], [f"{PRINCIPAL_TABLE}.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "principal_id",
            "permission_target_id",
            "permission",
            name=unique_name,
        ),
    )
    op.create_index("ix_permission_assignment_principal_id", PERMISSION_ASSIGNMENT_TABLE, ["principal_id"], unique=False)
    op.create_index(
        "ix_permission_assignment_permission_target_id",
        PERMISSION_ASSIGNMENT_TABLE,
        ["permission_target_id"],
        unique=False,
    )


def _copy_upgrade_data(
    permission_target_source: str | None,
    principal_source: str | None,
    permission_assignment_source: str | None,
) -> None:
    connection = op.get_bind()

    if permission_target_source is not None:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO "{PERMISSION_TARGET_TABLE}" (id, uri, command)
                SELECT id, uri, NULL
                FROM "{permission_target_source}"
                """
            )
        )

    if principal_source is not None:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO "{PRINCIPAL_TABLE}" (id, user_id, group_id)
                SELECT id, user_id, group_id
                FROM "{principal_source}"
                """
            )
        )

    if permission_assignment_source is not None:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO "{PERMISSION_ASSIGNMENT_TABLE}" (
                    id,
                    principal_id,
                    permission_target_id,
                    grant_type,
                    permission
                )
                SELECT id, principal_id, permission_target_id, grant_type, permission
                FROM "{permission_assignment_source}"
                """
            )
        )

    _reset_postgres_sequence(PERMISSION_TARGET_TABLE)
    _reset_postgres_sequence(PRINCIPAL_TABLE)
    _reset_postgres_sequence(PERMISSION_ASSIGNMENT_TABLE)


def _copy_downgrade_data(
    permission_target_source: str | None,
    principal_source: str | None,
    permission_assignment_source: str | None,
) -> None:
    connection = op.get_bind()

    if permission_target_source is not None:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO "{PERMISSION_TARGET_TABLE}" (id, uri)
                SELECT id, uri
                FROM "{permission_target_source}"
                """
            )
        )

    if principal_source is not None:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO "{PRINCIPAL_TABLE}" (id, user_id, group_id)
                SELECT id, user_id, group_id
                FROM "{principal_source}"
                """
            )
        )

    if permission_assignment_source is not None:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO "{PERMISSION_ASSIGNMENT_TABLE}" (
                    id,
                    principal_id,
                    permission_target_id,
                    grant_type,
                    permission
                )
                SELECT id, principal_id, permission_target_id, grant_type, permission
                FROM "{permission_assignment_source}"
                """
            )
        )

    _reset_postgres_sequence(PERMISSION_TARGET_TABLE)
    _reset_postgres_sequence(PRINCIPAL_TABLE)
    _reset_postgres_sequence(PERMISSION_ASSIGNMENT_TABLE)


def _rebuild_core_tables_for_upgrade() -> None:
    _assert_no_backup_tables(PERMISSION_TARGET_BACKUP, PRINCIPAL_BACKUP, PERMISSION_ASSIGNMENT_BACKUP)

    if _table_exists(PRINCIPAL_TABLE) and _principal_has_incompatible_rows(PRINCIPAL_TABLE):
        raise RuntimeError(
            "Cannot align principal table with m8flow_bpmn_core compatibility rules because "
            "existing rows do not satisfy the exactly-one-of(user_id, group_id) requirement."
        )

    permission_assignment_source: str | None = None
    principal_source: str | None = None
    permission_target_source: str | None = None

    if _table_exists(PERMISSION_ASSIGNMENT_TABLE):
        op.rename_table(PERMISSION_ASSIGNMENT_TABLE, PERMISSION_ASSIGNMENT_BACKUP)
        permission_assignment_source = PERMISSION_ASSIGNMENT_BACKUP
        _drop_indexes(PERMISSION_ASSIGNMENT_BACKUP)

    if _table_exists(PRINCIPAL_TABLE):
        op.rename_table(PRINCIPAL_TABLE, PRINCIPAL_BACKUP)
        principal_source = PRINCIPAL_BACKUP

    if _table_exists(PERMISSION_TARGET_TABLE):
        op.rename_table(PERMISSION_TARGET_TABLE, PERMISSION_TARGET_BACKUP)
        permission_target_source = PERMISSION_TARGET_BACKUP

    _create_permission_target_table()
    _create_principal_table()
    _create_permission_assignment_table(PERMISSION_ASSIGNMENT_UNIQUE)
    _copy_upgrade_data(permission_target_source, principal_source, permission_assignment_source)

    if permission_assignment_source is not None:
        op.drop_table(permission_assignment_source)
    if principal_source is not None:
        op.drop_table(principal_source)
    if permission_target_source is not None:
        op.drop_table(permission_target_source)


def _ensure_user_group_assignment_table() -> None:
    if not _table_exists(USER_GROUP_ASSIGNMENT_TABLE):
        op.create_table(
            USER_GROUP_ASSIGNMENT_TABLE,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("group_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["group_id"], ["group.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "group_id", name=USER_GROUP_ASSIGNMENT_UNIQUE),
        )
        op.create_index("ix_user_group_assignment_user_id", USER_GROUP_ASSIGNMENT_TABLE, ["user_id"], unique=False)
        op.create_index("ix_user_group_assignment_group_id", USER_GROUP_ASSIGNMENT_TABLE, ["group_id"], unique=False)
        _reset_postgres_sequence(USER_GROUP_ASSIGNMENT_TABLE)
        return

    if not _unique_exists(USER_GROUP_ASSIGNMENT_TABLE, ["user_id", "group_id"], name=USER_GROUP_ASSIGNMENT_UNIQUE):
        op.create_unique_constraint(
            USER_GROUP_ASSIGNMENT_UNIQUE,
            USER_GROUP_ASSIGNMENT_TABLE,
            ["user_id", "group_id"],
        )

    if not _index_exists(USER_GROUP_ASSIGNMENT_TABLE, ["user_id"]):
        op.create_index("ix_user_group_assignment_user_id", USER_GROUP_ASSIGNMENT_TABLE, ["user_id"], unique=False)

    if not _index_exists(USER_GROUP_ASSIGNMENT_TABLE, ["group_id"]):
        op.create_index("ix_user_group_assignment_group_id", USER_GROUP_ASSIGNMENT_TABLE, ["group_id"], unique=False)


def upgrade() -> None:
    if _core_tables_need_upgrade():
        _rebuild_core_tables_for_upgrade()
    _ensure_user_group_assignment_table()


def _create_legacy_permission_target_table() -> None:
    op.create_table(
        PERMISSION_TARGET_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uri", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uri"),
    )


def _create_legacy_principal_table() -> None:
    op.create_table(
        PRINCIPAL_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("NOT(user_id IS NULL AND group_id IS NULL)"),
        sa.ForeignKeyConstraint(["group_id"], ["group.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id"),
        sa.UniqueConstraint("user_id"),
    )


def _rebuild_core_tables_for_downgrade() -> None:
    _assert_no_backup_tables(
        PERMISSION_TARGET_DOWNGRADE_BACKUP,
        PRINCIPAL_DOWNGRADE_BACKUP,
        PERMISSION_ASSIGNMENT_DOWNGRADE_BACKUP,
    )

    if _table_exists(PERMISSION_TARGET_TABLE) and _permission_target_has_duplicate_uris(PERMISSION_TARGET_TABLE):
        raise RuntimeError(
            "Cannot downgrade RBAC compatibility migration because permission_target contains "
            "multiple rows with the same uri and downgrade restores uri-only uniqueness."
        )

    permission_assignment_source: str | None = None
    principal_source: str | None = None
    permission_target_source: str | None = None

    if _table_exists(PERMISSION_ASSIGNMENT_TABLE):
        op.rename_table(PERMISSION_ASSIGNMENT_TABLE, PERMISSION_ASSIGNMENT_DOWNGRADE_BACKUP)
        permission_assignment_source = PERMISSION_ASSIGNMENT_DOWNGRADE_BACKUP
        _drop_indexes(PERMISSION_ASSIGNMENT_DOWNGRADE_BACKUP)

    if _table_exists(PRINCIPAL_TABLE):
        op.rename_table(PRINCIPAL_TABLE, PRINCIPAL_DOWNGRADE_BACKUP)
        principal_source = PRINCIPAL_DOWNGRADE_BACKUP

    if _table_exists(PERMISSION_TARGET_TABLE):
        op.rename_table(PERMISSION_TARGET_TABLE, PERMISSION_TARGET_DOWNGRADE_BACKUP)
        permission_target_source = PERMISSION_TARGET_DOWNGRADE_BACKUP

    _create_legacy_permission_target_table()
    _create_legacy_principal_table()
    _create_permission_assignment_table(LEGACY_PERMISSION_ASSIGNMENT_UNIQUE)
    _copy_downgrade_data(permission_target_source, principal_source, permission_assignment_source)

    if permission_assignment_source is not None:
        op.drop_table(permission_assignment_source)
    if principal_source is not None:
        op.drop_table(principal_source)
    if permission_target_source is not None:
        op.drop_table(permission_target_source)


def downgrade() -> None:
    _rebuild_core_tables_for_downgrade()
