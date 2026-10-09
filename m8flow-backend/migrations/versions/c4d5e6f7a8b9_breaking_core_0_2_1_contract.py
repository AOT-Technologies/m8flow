"""Apply the final breaking m8flow-bpmn-core 0.2.1 contract.

This is intentionally a destructive, coordinated migration.  It must run only
after every M8Flow process, worker, scheduler and API has been upgraded to the
0.2.1 wheel.  The core repository's required migration marker is
``k2l3m4n5o6p7``.  Core migrations are not part of the wheel, so this host
migration completes the equivalent final core operation when the core marker is
absent, then records the marker after all changes succeed.

The migration validates all lossy conversions before changing schema.  A
downgrade can restore nullable legacy columns for structural rollback only; it
cannot reconstruct values removed by this migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b7e1c2d3f4a5"
branch_labels = None
depends_on = None

REQUIRED_CORE_MIGRATION = "k2l3m4n5o6p7"
CORE_VERSION_TABLE = "m8flow_core_alembic_version"
LEGACY_CORE_VERSION_TABLE = "alembic_version"

CORE_EPOCH_COLUMNS: dict[str, tuple[str, ...]] = {
    "user": ("created_at_in_seconds", "updated_at_in_seconds"),
    "m8flow_tenant": ("created_at_in_seconds", "updated_at_in_seconds"),
    "bpmn_process_definition": ("created_at_in_seconds", "updated_at_in_seconds"),
    "bpmn_process": ("start_in_seconds", "end_in_seconds"),
    "task_definition": ("created_at_in_seconds", "updated_at_in_seconds"),
    "task": ("start_in_seconds", "end_in_seconds"),
    "process_instance": (
        "start_in_seconds",
        "end_in_seconds",
        "task_updated_at_in_seconds",
        "created_at_in_seconds",
        "updated_at_in_seconds",
    ),
    "future_task": ("run_at_in_seconds", "queued_to_run_at_in_seconds", "updated_at_in_seconds"),
    "process_instance_event": ("timestamp",),
    "process_instance_metadata": ("created_at_in_seconds", "updated_at_in_seconds"),
    "process_model_bpmn_version": ("created_at_in_seconds",),
    "scheduler_job": (
        "locked_at_in_seconds",
        "run_at_in_seconds",
        "created_at_in_seconds",
        "updated_at_in_seconds",
    ),
    "work_item": ("updated_at_in_seconds", "created_at_in_seconds"),
}


def _bind():
    return op.get_bind()


def _tables() -> set[str]:
    return set(sa.inspect(_bind()).get_table_names())


def _has_table(name: str) -> bool:
    return name in _tables()


def _columns(name: str) -> set[str]:
    if not _has_table(name):
        return set()
    return {column["name"] for column in sa.inspect(_bind()).get_columns(name)}


def _table(name: str, *columns: str) -> sa.TableClause:
    """Build a SQLAlchemy Core table clause for migration-only SQL."""
    return sa.table(name, *(sa.column(column) for column in columns))


def _quote(name: str) -> str:
    return _bind().dialect.identifier_preparer.quote(name)


def _drop_columns(table: str, names: list[str]) -> None:
    existing = [name for name in names if name in _columns(table)]
    if not existing:
        return
    if _bind().dialect.name == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch:
            for name in existing:
                batch.drop_column(name)
        return
    for name in existing:
        op.drop_column(table, name)


def _add_column(table: str, column: sa.Column) -> None:
    if _has_table(table) and column.name not in _columns(table):
        op.add_column(table, column)


def _rename_column(table: str, old: str, new: str) -> None:
    columns = _columns(table)
    if old not in columns or new in columns:
        return
    if _bind().dialect.name == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.alter_column(old, new_column_name=new)
    else:
        op.alter_column(table, old, new_column_name=new)


def _set_not_null(table: str, column: str) -> None:
    """Make a validated canonical column non-null on every supported dialect."""
    if not _has_table(table) or column not in _columns(table):
        return
    column_info = next(
        item for item in sa.inspect(_bind()).get_columns(table) if item["name"] == column
    )
    if not column_info.get("nullable", True):
        return
    if _bind().dialect.name == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch:
            batch.alter_column(column, nullable=False)
    else:
        op.alter_column(table, column, nullable=False)


def _drop_work_item_legacy_foreign_keys() -> None:
    """Remove the 0.2.0 compatibility FK before deleting human_task."""
    if not _has_table("work_item"):
        return
    foreign_keys = sa.inspect(_bind()).get_foreign_keys("work_item")
    names = [
        fk.get("name")
        for fk in foreign_keys
        if fk.get("referred_table") == "human_task" and fk.get("name")
    ]
    if not names:
        return
    if _bind().dialect.name == "sqlite":
        with op.batch_alter_table("work_item", recreate="always") as batch:
            for name in names:
                batch.drop_constraint(name, type_="foreignkey")
    else:
        for name in names:
            op.drop_constraint(name, "work_item", type_="foreignkey")


def _rename_group_table() -> None:
    if _has_table("group") and not _has_table("m8f_group"):
        op.rename_table("group", "m8f_group")


def _validate_process_digests() -> None:
    table = "bpmn_process_definition"
    columns = _columns(table)
    if not _has_table(table) or "process_xml_digest" in columns:
        return
    candidates = [name for name in ("full_process_model_hash", "single_process_hash") if name in columns]
    if not candidates:
        raise RuntimeError("bpmn_process_definition has no legacy digest to migrate")
    source = candidates[0]
    process_definition = sa.table(
        table,
        sa.column("id"),
        sa.column("m8f_tenant_id"),
        sa.column("single_process_hash"),
        sa.column("full_process_model_hash"),
    )
    if len(candidates) == 2:
        conflicts = _bind().execute(
            sa.select(process_definition.c.id)
            .where(
                process_definition.c.single_process_hash.is_not(None),
                process_definition.c.full_process_model_hash.is_not(None),
                process_definition.c.single_process_hash != process_definition.c.full_process_model_hash,
            )
            .limit(5)
        ).scalars().all()
        if conflicts:
            raise RuntimeError(f"Process digest aliases disagree for rows {conflicts}")
    duplicates = _bind().execute(
        sa.select(
            process_definition.c.m8f_tenant_id,
            process_definition.c[source],
            sa.func.count(),
        )
        .where(process_definition.c[source].is_not(None))
        .group_by(process_definition.c.m8f_tenant_id, process_definition.c[source])
        .having(sa.func.count() > 1)
    ).all()
    if duplicates:
        raise RuntimeError(f"Canonical process digest collisions: {duplicates[:5]}")


def _migrate_process_digests() -> None:
    table = "bpmn_process_definition"
    if not _has_table(table):
        return
    columns = _columns(table)
    if "process_xml_digest" not in columns:
        _add_column(table, sa.Column("process_xml_digest", sa.String(length=255), nullable=True))
        source = "full_process_model_hash" if "full_process_model_hash" in columns else "single_process_hash"
        if source not in columns:
            raise RuntimeError("Cannot backfill process_xml_digest: legacy digest is absent")
        process_definition = sa.table(
            table,
            sa.column("process_xml_digest"),
            sa.column(source),
        )
        op.execute(
            sa.update(process_definition)
            .where(process_definition.c.process_xml_digest.is_(None))
            .values(process_xml_digest=process_definition.c[source])
        )
    process_definition = _table("bpmn_process_definition", "id", "process_xml_digest")
    missing = _bind().execute(
        sa.select(process_definition.c.id)
        .where(process_definition.c.process_xml_digest.is_(None))
        .limit(5)
    ).scalars().all()
    if missing:
        raise RuntimeError(f"Process definitions are missing canonical digests: {missing}")
    _set_not_null(table, "process_xml_digest")
    _drop_columns(table, ["single_process_hash", "full_process_model_hash"])


def _migrate_work_items() -> None:
    if not _has_table("work_item") and not _has_table("human_task"):
        return
    if not _has_table("work_item"):
        op.create_table(
            "work_item",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("process_instance_id", sa.Integer(), nullable=False),
            sa.Column("task_guid", sa.String(length=36), nullable=True),
            sa.Column("lane_assignment_id", sa.Integer(), nullable=True),
            sa.Column("completed_by_user_id", sa.Integer(), nullable=True),
            sa.Column("actual_owner_id", sa.Integer(), nullable=True),
            sa.Column("task_status", sa.String(length=50), nullable=False),
            sa.Column("completed", sa.Boolean(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
            sa.PrimaryKeyConstraint("id", name="m8f_work_item_pk"),
        )
        human_task = _table(
            "human_task",
            "id",
            "process_instance_id",
            "task_guid",
            "lane_assignment_id",
            "completed_by_user_id",
            "actual_owner_id",
            "task_status",
            "completed",
            "updated_at",
            "created_at",
            "m8f_tenant_id",
        )
        work_item = _table(
            "work_item",
            "id",
            "process_instance_id",
            "task_guid",
            "lane_assignment_id",
            "completed_by_user_id",
            "actual_owner_id",
            "task_status",
            "completed",
            "updated_at",
            "created_at",
            "m8f_tenant_id",
        )
        work_item_columns = [
            work_item.c.id,
            work_item.c.process_instance_id,
            work_item.c.task_guid,
            work_item.c.lane_assignment_id,
            work_item.c.completed_by_user_id,
            work_item.c.actual_owner_id,
            work_item.c.task_status,
            work_item.c.completed,
            work_item.c.updated_at,
            work_item.c.created_at,
            work_item.c.m8f_tenant_id,
        ]
        op.execute(
            sa.insert(work_item).from_select(
                work_item_columns,
                sa.select(*work_item_columns).select_from(human_task),
            )
        )
    if _has_table("human_task"):
        human_task = _table("human_task", "id").alias("h")
        work_item = _table("work_item", "id").alias("w")
        missing = _bind().execute(
            sa.select(human_task.c.id)
            .select_from(human_task.outerjoin(work_item, work_item.c.id == human_task.c.id))
            .where(work_item.c.id.is_(None))
            .limit(5)
        ).scalars().all()
        if missing:
            raise RuntimeError(f"Human tasks without exactly one work item: {missing}")

    work_columns = _columns("work_item")
    _drop_columns("work_item", ["task_id", *CORE_EPOCH_COLUMNS["work_item"]])
    if "task_guid" not in work_columns:
        raise RuntimeError("work_item is missing task_guid")


def _migrate_assignments() -> None:
    if not _has_table("human_task_user"):
        return
    if not _has_table("work_item_user"):
        op.create_table(
            "work_item_user",
            sa.Column("work_item_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("added_by", sa.String(length=20), nullable=True),
            sa.Column("m8f_tenant_id", sa.String(length=255), nullable=False),
            sa.PrimaryKeyConstraint("work_item_id", "user_id", name="m8f_work_item_user_pk"),
        )
    source_columns = _columns("human_task_user")
    required = {"human_task_id", "user_id", "m8f_tenant_id"}
    if not required.issubset(source_columns):
        raise RuntimeError("human-task assignments cannot be mapped to work-item assignments")
    human_task_user = _table("human_task_user", "human_task_id", "user_id").alias("h")
    work_item = _table("work_item", "id").alias("w")
    orphaned = _bind().execute(
        sa.select(human_task_user.c.human_task_id, human_task_user.c.user_id)
        .select_from(
            human_task_user.outerjoin(
                work_item, work_item.c.id == human_task_user.c.human_task_id
            )
        )
        .where(work_item.c.id.is_(None))
        .limit(5)
    ).all()
    if orphaned:
        raise RuntimeError(f"Human-task assignments without a work item: {orphaned}")
    human_task_user = _table(
        "human_task_user",
        "human_task_id",
        "user_id",
        "added_by",
        "m8f_tenant_id",
    ).alias("h")
    work_item = _table("work_item", "id").alias("w")
    work_item_user = _table(
        "work_item_user", "work_item_id", "user_id", "added_by", "m8f_tenant_id"
    )
    existing_assignment = work_item_user.alias("x")
    source = (
        sa.select(
            human_task_user.c.human_task_id,
            human_task_user.c.user_id,
            human_task_user.c.added_by,
            human_task_user.c.m8f_tenant_id,
        )
        .select_from(
            human_task_user.join(work_item, work_item.c.id == human_task_user.c.human_task_id)
        )
        .where(
            ~sa.exists(
                sa.select(1)
                .select_from(existing_assignment)
                .where(
                    existing_assignment.c.work_item_id == human_task_user.c.human_task_id,
                    existing_assignment.c.user_id == human_task_user.c.user_id,
                    existing_assignment.c.m8f_tenant_id == human_task_user.c.m8f_tenant_id,
                )
            )
        )
    )
    op.execute(
        sa.insert(work_item_user).from_select(
            [
                work_item_user.c.work_item_id,
                work_item_user.c.user_id,
                work_item_user.c.added_by,
                work_item_user.c.m8f_tenant_id,
            ],
            source,
        )
    )


def _migrate_permission_targets() -> None:
    table = "permission_target"
    if not _has_table(table):
        return
    columns = _columns(table)
    if "resource_type" not in columns:
        _add_column(table, sa.Column("resource_type", sa.String(length=100), nullable=True))
    if "resource_id" not in columns:
        _add_column(table, sa.Column("resource_id", sa.String(length=255), nullable=True))
    columns = _columns(table)
    if "uri" in columns:
        # A route is an explicit resource pair, not a URI fallback.  Empty
        # targets cannot be converted safely and must stop the deployment.
        permission_target = _table("permission_target", "id", "uri")
        invalid = _bind().execute(
            sa.select(permission_target.c.id)
            .where(
                sa.or_(
                    permission_target.c.uri.is_(None),
                    sa.func.trim(permission_target.c.uri) == "",
                )
            )
            .limit(5)
        ).scalars().all()
        if invalid:
            raise RuntimeError(f"Permission targets cannot be mapped to resource pairs: {invalid}")
        permission_target = _table(
            "permission_target", "uri", "resource_type", "resource_id"
        )
        op.execute(
            sa.update(permission_target)
            .where(
                sa.or_(
                    permission_target.c.resource_type.is_(None),
                    permission_target.c.resource_id.is_(None),
                )
            )
            .values(resource_type="tenant", resource_id=permission_target.c.uri)
        )
    permission_target = _table("permission_target", "id", "resource_type", "resource_id", "command")
    unresolved = _bind().execute(
        sa.select(permission_target.c.id)
        .where(
            sa.or_(
                permission_target.c.resource_type.is_(None),
                permission_target.c.resource_id.is_(None),
            )
        )
        .limit(5)
    ).scalars().all()
    if unresolved:
        raise RuntimeError(f"Permission targets have no explicit resource pair: {unresolved}")
    command = sa.func.coalesce(permission_target.c.command, "").label("command")
    duplicates = _bind().execute(
        sa.select(
            permission_target.c.resource_type,
            permission_target.c.resource_id,
            command,
            sa.func.count(),
        )
        .group_by(permission_target.c.resource_type, permission_target.c.resource_id, command)
        .having(sa.func.count() > 1)
    ).all()
    if duplicates:
        raise RuntimeError(f"Permission resource-pair collisions: {duplicates[:5]}")
    _drop_columns(table, ["uri"])


def _migrate_events() -> None:
    table = "process_instance_event"
    if not _has_table(table):
        return
    columns = _columns(table)
    if "occurred_at" not in columns:
        _add_column(table, sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True))
        if "timestamp" in columns:
            dialect = _bind().dialect.name
            event = sa.table(
                table,
                sa.column("occurred_at"),
                sa.column("timestamp"),
            )
            expression = {
                "sqlite": sa.func.datetime(event.c.timestamp, "unixepoch"),
                "postgresql": sa.func.to_timestamp(event.c.timestamp),
                "mysql": sa.func.from_unixtime(event.c.timestamp),
                "mariadb": sa.func.from_unixtime(event.c.timestamp),
            }.get(dialect)
            if expression is None:
                raise RuntimeError(f"Unsupported dialect for event timestamp conversion: {dialect}")
            op.execute(
                sa.update(event)
                .where(event.c.occurred_at.is_(None))
                .values(occurred_at=expression)
            )
    if "category" not in columns:
        _add_column(table, sa.Column("category", sa.String(length=20), nullable=True))
    event = _table("process_instance_event", "id", "event_type", "category", "occurred_at")
    unknown = _bind().execute(
        sa.select(event.c.event_type)
        .distinct()
        .where(
            sa.or_(
                event.c.event_type.is_(None),
                sa.and_(
                    ~event.c.event_type.like("task_%"),
                    ~event.c.event_type.like("process_%"),
                ),
            )
        )
    ).all()
    if unknown:
        raise RuntimeError(f"Event types cannot be assigned a category: {unknown}")
    op.execute(
        sa.update(event)
        .where(event.c.category.is_(None))
        .values(
            category=sa.case(
                (event.c.event_type.like("task_%"), "task"),
                else_="process",
            )
        )
    )
    missing = _bind().execute(
        sa.select(event.c.id)
        .where(sa.or_(event.c.category.is_(None), event.c.occurred_at.is_(None)))
        .limit(5)
    ).scalars().all()
    if missing:
        raise RuntimeError(f"Event rows are missing canonical category/timestamp: {missing}")
    _set_not_null(table, "occurred_at")
    _set_not_null(table, "category")
    _drop_columns(table, ["timestamp"])


def _enforce_identity_and_names() -> None:
    _rename_column("user", "tenant_specific_field_1", "realm_identifier")
    _rename_column("user", "tenant_specific_field_2", "external_org_id")
    _rename_column("user", "tenant_specific_field_3", "external_user_id")
    _rename_column("process_instance", "spiff_serializer_version", "workflow_engine_version")


def _core_marker_revisions() -> list[str] | None:
    """Return core revisions without taking ownership of host Alembic state.

    New databases use the dedicated core table. The legacy table is consulted
    only for compatibility with databases upgraded before the dedicated marker
    was introduced. Unrelated rows in that legacy table are treated as host
    state; a mixed legacy table containing the core marker is rejected because
    ownership cannot be determined safely.
    """
    if _has_table(CORE_VERSION_TABLE):
        core_version = _table(CORE_VERSION_TABLE, "version_num")
        revisions = list(
            _bind().execute(sa.select(core_version.c.version_num)).scalars().all()
        )
        if revisions:
            return revisions

    if not _has_table(LEGACY_CORE_VERSION_TABLE):
        return [] if _has_table(CORE_VERSION_TABLE) else None

    legacy_version = _table(LEGACY_CORE_VERSION_TABLE, "version_num")
    legacy_revisions = list(
        _bind().execute(sa.select(legacy_version.c.version_num)).scalars().all()
    )
    if REQUIRED_CORE_MIGRATION not in legacy_revisions:
        return []
    if legacy_revisions != [REQUIRED_CORE_MIGRATION]:
        raise RuntimeError(
            "Legacy alembic_version contains mixed host/core revisions; "
            f"move the core marker to {CORE_VERSION_TABLE} before upgrading: "
            f"found {legacy_revisions!r}"
        )
    return [REQUIRED_CORE_MIGRATION]


def _require_core_breaking_head() -> bool:
    """Validate an existing core marker and report whether it was present.

    The core wheel intentionally excludes Alembic scripts.  A missing marker
    therefore means this host migration must perform the final core operation
    itself.  An existing marker is still strict: never overwrite a partially
    upgraded or otherwise incompatible core revision.
    """
    revisions = _core_marker_revisions()
    if not revisions:
        return False
    if revisions != [REQUIRED_CORE_MIGRATION]:
        raise RuntimeError(
            "m8flow-bpmn-core must be at exactly "
            f"{REQUIRED_CORE_MIGRATION}; found {revisions!r}"
        )
    return True


def _drop_core_source_is_open_id() -> None:
    """Apply core revision k2l3m4n5o6p7 when the wheel has no scripts."""
    if _has_table("m8f_group"):
        _drop_columns("m8f_group", ["source_is_open_id"])


def _validate_core_handoff_schema() -> None:
    """Avoid stamping an unrelated or incompletely bootstrapped database."""
    required_tables = {
        "m8flow_tenant",
        "user",
        "process_instance",
        "task",
        "permission_target",
        "process_instance_event",
    }
    missing = sorted(required_tables - _tables())
    if missing:
        raise RuntimeError(
            "Cannot complete the core 0.2.1 handoff; required tables are missing: "
            + ", ".join(missing)
        )


def _record_core_breaking_head() -> None:
    """Idempotently stamp the dedicated core head."""
    if not _has_table(CORE_VERSION_TABLE):
        op.create_table(
            CORE_VERSION_TABLE,
            sa.Column("version_num", sa.String(length=32), nullable=False),
            sa.PrimaryKeyConstraint("version_num"),
        )
    core_version = _table(CORE_VERSION_TABLE, "version_num")
    exists = _bind().execute(
        sa.select(core_version.c.version_num)
        .where(core_version.c.version_num == REQUIRED_CORE_MIGRATION)
        .limit(1)
    ).scalar()
    if exists is None:
        _bind().execute(
            sa.insert(core_version).values(version_num=REQUIRED_CORE_MIGRATION)
        )


def upgrade() -> None:
    core_head_was_present = _require_core_breaking_head()
    if not core_head_was_present:
        _validate_core_handoff_schema()
    _rename_group_table()
    if not core_head_was_present and not _has_table("m8f_group"):
        raise RuntimeError(
            "Cannot complete the core 0.2.1 handoff: neither group nor m8f_group exists"
        )
    _validate_process_digests()
    _migrate_work_items()
    _migrate_assignments()
    _migrate_permission_targets()
    _migrate_events()
    _enforce_identity_and_names()
    for table, columns in CORE_EPOCH_COLUMNS.items():
        _drop_columns(table, list(columns))
    if not core_head_was_present:
        _drop_core_source_is_open_id()
    _drop_work_item_legacy_foreign_keys()
    if _has_table("human_task_user"):
        op.drop_table("human_task_user")
    if _has_table("human_task"):
        op.drop_table("human_task")
    # Always ensure the dedicated marker exists. This also migrates a legacy
    # database whose sole core marker lived in ``alembic_version``.
    _record_core_breaking_head()


def downgrade() -> None:
    # Structural rollback only.  Removed values are intentionally not restored.
    if _has_table("m8f_group") and "source_is_open_id" not in _columns("m8f_group"):
        _add_column(
            "m8f_group",
            sa.Column("source_is_open_id", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if _has_table(CORE_VERSION_TABLE):
        core_version = _table(CORE_VERSION_TABLE, "version_num")
        _bind().execute(
            sa.delete(core_version).where(
                core_version.c.version_num == REQUIRED_CORE_MIGRATION
            )
        )
        if not _bind().execute(sa.select(core_version.c.version_num).limit(1)).scalar():
            op.drop_table(CORE_VERSION_TABLE)
    for table, columns in CORE_EPOCH_COLUMNS.items():
        if _has_table(table):
            for column in columns:
                _add_column(table, sa.Column(column, sa.BigInteger(), nullable=True))
    if _has_table("process_instance"):
        _rename_column("process_instance", "workflow_engine_version", "spiff_serializer_version")
    if _has_table("user"):
        _rename_column("user", "realm_identifier", "tenant_specific_field_1")
        _rename_column("user", "external_org_id", "tenant_specific_field_2")
        _rename_column("user", "external_user_id", "tenant_specific_field_3")
    if _has_table("m8f_group") and not _has_table("group"):
        op.rename_table("m8f_group", "group")
