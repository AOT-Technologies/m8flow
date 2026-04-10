from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e4f5a6b7c8d9"
down_revision = "d2b8f0d1a4c5"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _drop_unique_by_columns(table: str, columns: list[str]) -> None:
    insp = _inspector()
    for constraint in insp.get_unique_constraints(table):
        if constraint.get("column_names") == columns and constraint.get("name"):
            op.drop_constraint(constraint["name"], table, type_="unique")
    for index in insp.get_indexes(table):
        if index.get("unique") and index.get("column_names") == columns and index.get("name"):
            op.drop_index(index["name"], table_name=table)


def _unique_exists(table: str, name: str) -> bool:
    insp = _inspector()
    return any(constraint.get("name") == name for constraint in insp.get_unique_constraints(table))


def _extract_realm_from_service(service: str | None) -> str | None:
    if isinstance(service, str) and "/realms/" in service:
        return service.split("/realms/")[-1].split("/")[0]
    return None


def _strip_realm_suffix(username: str | None, service: str | None) -> str | None:
    if not isinstance(username, str):
        return username
    realm = _extract_realm_from_service(service)
    if not realm:
        return username
    suffix = f"@{realm}"
    if username.endswith(suffix):
        return username[: -len(suffix)]
    return username


def _load_users() -> list[dict[str, object]]:
    conn = op.get_bind()
    user_table = sa.table(
        "user",
        sa.column("id", sa.Integer),
        sa.column("username", sa.String),
        sa.column("service", sa.String),
    )
    result = conn.execute(sa.select(user_table.c.id, user_table.c.username, user_table.c.service))
    return [dict(row) for row in result.mappings()]


def _update_username(user_id: int, username: str) -> None:
    conn = op.get_bind()
    user_table = sa.table(
        "user",
        sa.column("id", sa.Integer),
        sa.column("username", sa.String),
    )
    stmt = (
        user_table.update()
        .where(user_table.c.id == sa.bindparam("target_id"))
        .values(username=sa.bindparam("new_username"))
    )
    conn.execute(stmt, {"target_id": user_id, "new_username": username})


def upgrade() -> None:
    _drop_unique_by_columns("user", ["username"])

    for row in _load_users():
        user_id = row["id"]
        username = row["username"]
        service = row["service"]
        if not isinstance(user_id, int) or not isinstance(username, str):
            continue
        normalized_username = _strip_realm_suffix(username, service if isinstance(service, str) else None)
        if normalized_username is not None and normalized_username != username:
            _update_username(user_id, normalized_username)


def downgrade() -> None:
    users = _load_users()
    username_counts: dict[str, int] = {}
    for row in users:
        username = row["username"]
        if isinstance(username, str):
            username_counts[username] = username_counts.get(username, 0) + 1

    used_usernames = {
        row["username"]
        for row in users
        if isinstance(row.get("username"), str)
    }

    for row in users:
        user_id = row["id"]
        username = row["username"]
        service = row["service"]
        if not isinstance(user_id, int) or not isinstance(username, str):
            continue
        if username_counts.get(username, 0) < 2:
            continue

        realm = _extract_realm_from_service(service if isinstance(service, str) else None) or "unknown"
        base_candidate = username if username.endswith(f"@{realm}") else f"{username}@{realm}"
        candidate = base_candidate
        counter = 2
        while candidate in used_usernames:
            candidate = f"{base_candidate}_{counter}"
            counter += 1

        used_usernames.add(candidate)
        used_usernames.discard(username)
        _update_username(user_id, candidate)

    if not _unique_exists("user", "uq_user_username"):
        op.create_unique_constraint("uq_user_username", "user", ["username"])
