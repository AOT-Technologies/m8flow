from __future__ import annotations

from collections import defaultdict

from alembic import op
import sqlalchemy as sa


revision = "h1a2b3c4d5e6"
down_revision = "h8c9d0e1f2g3"
branch_labels = None
depends_on = None

TABLE_NAME = "user"
CONSTRAINT_NAME = "uq_user_username_realm"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _get_username_max_length() -> int:
    for col in _inspector().get_columns(TABLE_NAME):
        if col["name"] == "username":
            col_type = col.get("type")
            if hasattr(col_type, "length") and col_type.length:
                return int(col_type.length)
    return 255


def _unique_exists(table: str, name: str) -> bool:
    insp = _inspector()
    return any(constraint.get("name") == name for constraint in insp.get_unique_constraints(table))


def _user_recency_key(row: dict[str, object]) -> tuple[int, int, int]:
    return (
        int(row.get("updated_at_in_seconds", 0) or 0),
        int(row.get("created_at_in_seconds", 0) or 0),
        int(row.get("id", 0) or 0),
    )


def _pick_survivor_and_losers(rows: list[dict[str, object]]) -> tuple[dict[str, object], list[dict[str, object]]]:
    ordered_rows = sorted(rows, key=_user_recency_key, reverse=True)
    return ordered_rows[0], ordered_rows[1:]


def _next_available_username(base_username: str, used_usernames: set[str], max_length: int) -> str:
    suffix = 2
    while True:
        suffix_str = str(suffix)
        truncated_base = base_username[: max_length - len(suffix_str)]
        candidate = f"{truncated_base}{suffix_str}"
        if candidate not in used_usernames:
            used_usernames.add(candidate)
            return candidate
        suffix += 1


def _load_users() -> list[dict[str, object]]:
    conn = op.get_bind()
    user_table = sa.table(
        TABLE_NAME,
        sa.column("id", sa.Integer),
        sa.column("username", sa.String),
        sa.column("service", sa.String),
        sa.column("created_at_in_seconds", sa.Integer),
        sa.column("updated_at_in_seconds", sa.Integer),
    )
    result = conn.execute(
        sa.select(
            user_table.c.id,
            user_table.c.username,
            user_table.c.service,
            user_table.c.created_at_in_seconds,
            user_table.c.updated_at_in_seconds,
        )
    )
    return [dict(row) for row in result.mappings()]


def _update_username(user_id: int, username: str) -> None:
    conn = op.get_bind()
    user_table = sa.table(
        TABLE_NAME,
        sa.column("id", sa.Integer),
        sa.column("username", sa.String),
    )
    stmt = (
        user_table.update()
        .where(user_table.c.id == sa.bindparam("target_id"))
        .values(username=sa.bindparam("new_username"))
    )
    conn.execute(stmt, {"target_id": user_id, "new_username": username})


def _rename_duplicate_usernames_for_exact_service() -> None:
    """Rename users that share (username, service) — the key enforced by the constraint.

    Rows where service IS NULL are intentionally skipped: PostgreSQL treats each NULL as
    distinct in a UNIQUE constraint, so (username, NULL) rows can never violate
    UNIQUE(username, service) regardless of how many exist.
    """
    max_length = _get_username_max_length()
    rows = _load_users()
    rows_by_key: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    used_usernames_by_service: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        username = row.get("username")
        service = row.get("service")
        if not isinstance(username, str):
            continue
        if not isinstance(service, str):
            continue
        used_usernames_by_service[service].add(username)
        rows_by_key[(username, service)].append(row)

    for (_username, service), duplicate_rows in rows_by_key.items():
        if len(duplicate_rows) < 2:
            continue

        survivor, losers = _pick_survivor_and_losers(duplicate_rows)
        survivor_username = survivor.get("username")
        if not isinstance(survivor_username, str):
            continue

        used_usernames = used_usernames_by_service[service]
        for loser in losers:
            loser_id = loser.get("id")
            if not isinstance(loser_id, int):
                continue
            renamed_username = _next_available_username(survivor_username, used_usernames, max_length)
            _update_username(loser_id, renamed_username)


def upgrade() -> None:
    _rename_duplicate_usernames_for_exact_service()

    if not _unique_exists(TABLE_NAME, CONSTRAINT_NAME):
        op.create_unique_constraint(CONSTRAINT_NAME, TABLE_NAME, ["username", "service"])


def downgrade() -> None:
    if _unique_exists(TABLE_NAME, CONSTRAINT_NAME):
        op.drop_constraint(CONSTRAINT_NAME, TABLE_NAME, type_="unique")
