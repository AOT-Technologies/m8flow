# m8flow-bpmn-core 0.2.1 breaking migration

M8Flow must be upgraded as one coordinated deployment with
`m8flow-bpmn-core==0.2.1`. Stop API processes, workers, schedulers, and other
workflow writers before applying the database migrations.

## Order

1. Back up the database and verify the backup.
2. Apply the core repository migration through `k2l3m4n5o6p7`.
3. Upgrade all M8Flow processes to the 0.2.1 wheel.
4. Apply M8Flow Alembic revision `c4d5e6f7a8b9` (the first M8Flow revision after
   the required core migration). The revision refuses to run unless the core
   `alembic_version` table is exactly at `k2l3m4n5o6p7`.
5. Start the upgraded services and verify representative process, task,
   event, authorization, and tenant-isolation operations.

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
