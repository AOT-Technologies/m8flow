# m8flow-bpmn-core 0.2.1 breaking migration

M8Flow must be upgraded as one coordinated deployment with
`m8flow-bpmn-core==0.2.1`. Stop API processes, workers, schedulers, and other
workflow writers before applying the database migrations.

## Order

1. Back up the database and verify the backup.
2. Upgrade all M8Flow processes to the 0.2.1 wheel.
3. Start the normal M8Flow migration command (`alembic upgrade head`, or the
   backend startup migration). The host migration creates the core marker for
   a fresh database and performs the equivalent final core operation before
   stamping `k2l3m4n5o6p7` for an existing database with no core marker.
4. Start the upgraded services and verify representative process, task,
   event, authorization, and tenant-isolation operations.

The core wheel does not package Alembic scripts, so DevOps does not need a
separate core checkout or a second migration command. If an existing
`alembic_version` table contains a non-empty revision other than
`k2l3m4n5o6p7`, M8Flow stops instead of overwriting it; resolve that partially
upgraded environment before retrying.

The M8Flow revision is intentionally destructive. It validates before changing
schema and aborts when it finds ambiguous process digests, orphaned task
assignments, incomplete work-item mappings, invalid permission targets, or
events that cannot be assigned a canonical category/timestamp.

## Data changes

- `human_task` assignments are copied to `work_item_user` and `human_task` /
  `human_task_user` are removed.
- Legacy process digest, serializer, tenant-identity, URI-target, and epoch
  columns are removed after their canonical replacements are validated.
- Events use `occurred_at`, `category`, `ProcessLifecycleEventType`, and
  `TaskEventType`.
- Permission targets use explicit `(resource_type, resource_id)` pairs.

## Downgrade and rollback

Downgrade restores the legacy column/table shape where practical, but removed
values are not reconstructed. Restore the verified database backup for a
data-preserving rollback. Do not run old application binaries against the
0.2.1 schema.
