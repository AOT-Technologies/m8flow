"""Remove the legacy default tenant row after canonical shared-realm migration.

Revision ID: i2b3c4d5e6f7
Revises: h1a2b3c4d5e6
Create Date: 2026-05-08
"""

from __future__ import annotations

import os
import time

from alembic import op
import sqlalchemy as sa


revision = "i2b3c4d5e6f7"
down_revision = "h1a2b3c4d5e6"
branch_labels = None
depends_on = None

LEGACY_TENANT_ID = "default"


def _legacy_tenant_exists(conn: sa.Connection) -> bool:
    return (
        conn.execute(
            sa.text("SELECT 1 FROM m8flow_tenant WHERE id = :tenant_id"),
            {"tenant_id": LEGACY_TENANT_ID},
        ).scalar()
        is not None
    )


def _shared_realm_slug() -> str:
    return (
        os.environ.get("M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS")
        or os.environ.get("M8FLOW_KEYCLOAK_SHARED_REALM")
        or "m8flow"
    ).strip()


def _canonical_shared_realm_tenant_id(conn: sa.Connection) -> str:
    shared_realm_slug = _shared_realm_slug()
    row = conn.execute(
        sa.text(
            """
            SELECT id
            FROM m8flow_tenant
            WHERE slug = :tenant_slug OR id = :tenant_slug
            ORDER BY CASE WHEN slug = :tenant_slug THEN 0 ELSE 1 END, id
            """
        ),
        {"tenant_slug": shared_realm_slug},
    ).mappings().first()

    if row is None:
        raise RuntimeError(
            f"Cannot remove legacy tenant '{LEGACY_TENANT_ID}': no canonical shared-realm tenant "
            f"row exists for slug/id '{shared_realm_slug}'."
        )

    canonical_tenant_id = str(row["id"]).strip()
    if not canonical_tenant_id or canonical_tenant_id == LEGACY_TENANT_ID:
        raise RuntimeError(
            f"Cannot remove legacy tenant '{LEGACY_TENANT_ID}': canonical shared-realm tenant "
            f"resolved to '{canonical_tenant_id or '<empty>'}'."
        )

    return canonical_tenant_id


def _tenant_scoped_table_names(conn: sa.Connection) -> list[str]:
    inspector = sa.inspect(conn)
    table_names: list[str] = []
    for table_name in inspector.get_table_names():
        if table_name == "m8flow_tenant":
            continue
        try:
            column_names = {column["name"] for column in inspector.get_columns(table_name)}
        except Exception:
            continue
        if "m8f_tenant_id" in column_names:
            table_names.append(table_name)
    return table_names


def _repoint_tenant_scoped_rows(conn: sa.Connection, target_tenant_id: str) -> None:
    for table_name in _tenant_scoped_table_names(conn):
        conn.execute(
            sa.text(
                f'UPDATE "{table_name}" '
                "SET m8f_tenant_id = :target_tenant_id "
                "WHERE m8f_tenant_id = :legacy_tenant_id"
            ),
            {
                "target_tenant_id": target_tenant_id,
                "legacy_tenant_id": LEGACY_TENANT_ID,
            },
        )


def _principal_id_for_group(conn: sa.Connection, group_id: int) -> int | None:
    value = conn.execute(
        sa.text("SELECT id FROM principal WHERE group_id = :group_id"),
        {"group_id": group_id},
    ).scalar()
    return int(value) if value is not None else None


def _merge_permission_assignments(conn: sa.Connection, source_principal_id: int, target_principal_id: int) -> None:
    assignments = conn.execute(
        sa.text(
            """
            SELECT id, permission_target_id, grant_type, permission
            FROM permission_assignment
            WHERE principal_id = :principal_id
            ORDER BY id
            """
        ),
        {"principal_id": source_principal_id},
    ).mappings().all()

    for assignment in assignments:
        existing_id = conn.execute(
            sa.text(
                """
                SELECT id
                FROM permission_assignment
                WHERE principal_id = :principal_id
                  AND permission_target_id = :permission_target_id
                  AND grant_type = :grant_type
                  AND permission = :permission
                """
            ),
            {
                "principal_id": target_principal_id,
                "permission_target_id": assignment["permission_target_id"],
                "grant_type": assignment["grant_type"],
                "permission": assignment["permission"],
            },
        ).scalar()
        if existing_id is None:
            conn.execute(
                sa.text(
                    "UPDATE permission_assignment SET principal_id = :target_principal_id WHERE id = :assignment_id"
                ),
                {
                    "target_principal_id": target_principal_id,
                    "assignment_id": assignment["id"],
                },
            )
            continue

        conn.execute(
            sa.text("DELETE FROM permission_assignment WHERE id = :assignment_id"),
            {"assignment_id": assignment["id"]},
        )


def _merge_group_memberships(conn: sa.Connection, table_name: str, key_column: str, source_group_id: int, target_group_id: int) -> None:
    rows = conn.execute(
        sa.text(
            f"""
            SELECT id, {key_column}
            FROM {table_name}
            WHERE group_id = :group_id
            ORDER BY id
            """
        ),
        {"group_id": source_group_id},
    ).mappings().all()

    for row in rows:
        existing_id = conn.execute(
            sa.text(
                f"""
                SELECT id
                FROM {table_name}
                WHERE {key_column} = :key_value
                  AND group_id = :target_group_id
                """
            ),
            {
                "key_value": row[key_column],
                "target_group_id": target_group_id,
            },
        ).scalar()
        if existing_id is None:
            conn.execute(
                sa.text(f"UPDATE {table_name} SET group_id = :target_group_id WHERE id = :row_id"),
                {
                    "target_group_id": target_group_id,
                    "row_id": row["id"],
                },
            )
            continue

        conn.execute(
            sa.text(f"DELETE FROM {table_name} WHERE id = :row_id"),
            {"row_id": row["id"]},
        )


def _merge_groups(conn: sa.Connection, target_tenant_id: str) -> None:
    legacy_prefix = f"{LEGACY_TENANT_ID}:"
    target_prefix = f"{target_tenant_id}:"

    legacy_groups = conn.execute(
        sa.text(
            """
            SELECT id, identifier
            FROM "group"
            WHERE identifier LIKE :legacy_prefix
            ORDER BY id
            """
        ),
        {"legacy_prefix": f"{legacy_prefix}%"},
    ).mappings().all()

    for legacy_group in legacy_groups:
        source_group_id = int(legacy_group["id"])
        old_identifier = str(legacy_group["identifier"])
        suffix = old_identifier[len(legacy_prefix) :].strip()
        if not suffix:
            continue

        new_identifier = f"{target_prefix}{suffix}"
        target_group = conn.execute(
            sa.text('SELECT id FROM "group" WHERE identifier = :identifier'),
            {"identifier": new_identifier},
        ).mappings().first()

        if target_group is None:
            conn.execute(
                sa.text('UPDATE "group" SET identifier = :new_identifier WHERE id = :group_id'),
                {
                    "new_identifier": new_identifier,
                    "group_id": source_group_id,
                },
            )
            continue

        target_group_id = int(target_group["id"])
        if target_group_id == source_group_id:
            continue

        conn.execute(
            sa.text("UPDATE human_task SET lane_assignment_id = :target_group_id WHERE lane_assignment_id = :source_group_id"),
            {
                "target_group_id": target_group_id,
                "source_group_id": source_group_id,
            },
        )
        _merge_group_memberships(conn, "user_group_assignment", "user_id", source_group_id, target_group_id)
        _merge_group_memberships(conn, "user_group_assignment_waiting", "username", source_group_id, target_group_id)

        source_principal_id = _principal_id_for_group(conn, source_group_id)
        target_principal_id = _principal_id_for_group(conn, target_group_id)
        if source_principal_id is not None:
            if target_principal_id is None:
                conn.execute(
                    sa.text("UPDATE principal SET group_id = :target_group_id WHERE id = :principal_id"),
                    {
                        "target_group_id": target_group_id,
                        "principal_id": source_principal_id,
                    },
                )
            else:
                _merge_permission_assignments(conn, source_principal_id, target_principal_id)
                conn.execute(
                    sa.text("DELETE FROM principal WHERE id = :principal_id"),
                    {"principal_id": source_principal_id},
                )

        conn.execute(
            sa.text('DELETE FROM "group" WHERE id = :group_id'),
            {"group_id": source_group_id},
        )


def upgrade() -> None:
    conn = op.get_bind()

    if not _legacy_tenant_exists(conn):
        return

    canonical_tenant_id = _canonical_shared_realm_tenant_id(conn)
    _repoint_tenant_scoped_rows(conn, canonical_tenant_id)
    _merge_groups(conn, canonical_tenant_id)
    conn.execute(
        sa.text("DELETE FROM m8flow_tenant WHERE id = :tenant_id"),
        {"tenant_id": LEGACY_TENANT_ID},
    )


def downgrade() -> None:
    conn = op.get_bind()

    if _legacy_tenant_exists(conn):
        return

    now = int(time.time())
    conn.execute(
        sa.text(
            """
            INSERT INTO m8flow_tenant (
                id,
                name,
                slug,
                created_by,
                modified_by,
                created_at_in_seconds,
                updated_at_in_seconds
            )
            VALUES (
                :tenant_id,
                :tenant_name,
                :tenant_slug,
                :created_by,
                :modified_by,
                :created_at,
                :updated_at
            )
            """
        ),
        {
            "tenant_id": LEGACY_TENANT_ID,
            "tenant_name": LEGACY_TENANT_ID,
            "tenant_slug": LEGACY_TENANT_ID,
            "created_by": "system",
            "modified_by": "system",
            "created_at": now,
            "updated_at": now,
        },
    )
