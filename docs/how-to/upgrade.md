# Upgrade m8flow

Move a Docker Compose deployment of m8flow to a newer release while keeping
its data. The backend migrates the database when it starts, so most upgrades
are a backup, a checkout, and a rebuild.

## Before you start

Before you upgrade, follow these steps:

1. Pick the release to upgrade to from the
   [releases page](https://github.com/AOT-Technologies/m8flow/releases).
2. Read every changelog section between your version and that release in
   [CHANGELOG.md](../../CHANGELOG.md). Do every step listed under
   **Breaking**. Within a major version there are none; see the
   [versioning policy](../reference/versioning.md).
3. Plan a maintenance window. Users can't sign in while Keycloak and the
   backend restart.

## Back up the databases

m8flow keeps its state in two PostgreSQL databases: m8flow's own and
Keycloak's. Back up both.

To back up both databases, run the following commands from the repository
root:

```bash
docker compose --env-file .env -f docker/m8flow-docker-compose.yml \
    exec -T m8flow-db pg_dump -U <postgres-user> <postgres-db> > m8flow-backup.sql
docker compose --env-file .env -f docker/m8flow-docker-compose.yml \
    exec -T keycloak-db pg_dump -U <keycloak-db-user> <keycloak-db-name> > keycloak-backup.sql
```

Replace the following:

- `<postgres-user>` and `<postgres-db>`: the `POSTGRES_USER` and `POSTGRES_DB`
  values in your `.env`.
- `<keycloak-db-user>` and `<keycloak-db-name>`: the `KEYCLOAK_DB_USER` and
  `KEYCLOAK_DB_NAME` values in your `.env`.

Also back up `data/process_models`, which holds the process model files.

## Upgrade

To upgrade, follow these steps:

1. Fetch the release and check out its tag:

   ```bash
   git fetch --tags
   git checkout <version>
   ```

   Replace `<version>` with the release, for example `2.1.0`.

2. Compare your `.env` with the new `sample.env`, and add any new settings the
   changelog says you need:

   ```bash
   diff <(grep -oE '^[A-Z_]+=' sample.env | sort) <(grep -oE '^[A-Z_]+=' .env | sort)
   ```

   Lines that start with `<` are settings in `sample.env` that your `.env`
   doesn't set. [Configuration](../reference/configuration.md) explains each one.

3. Rebuild and restart the stack:

   ```bash
   docker compose --env-file .env -f docker/m8flow-docker-compose.yml up -d --build
   ```

   The backend applies database migrations at startup. If you set
   `M8FLOW_BACKEND_UPGRADE_DB=false`, run them yourself with
   `./m8flow-backend/bin/run_m8flow_alembic.sh` first.

4. If the changelog says the Keycloak realm changed, re-import it as the
   changelog describes.

## Upgrade from 1.0.x to 2.0

The 2.0 upgrade runs a destructive migration, `c4d5e6f7a8b9`, that moves the
database to the `m8flow-bpmn-core` 0.2.1 contract. Read this section before
you start, and follow these steps in place of step 3 in
[Upgrade](#upgrade).

The migration does the following:

- It checks the data before it changes anything. It aborts if it finds data it
  can't convert safely: ambiguous or colliding process digests, task
  assignments that have no work item, human tasks that don't map to exactly
  one work item, permission targets that don't map to a resource, or events
  that can't get a category or timestamp. Fix the reported rows, restore the
  backup if needed, and run it again.
- It loses data. It copies `human_task` assignments to `work_item_user`, then
  drops `human_task`, `human_task_user`, and the old digest, serializer,
  tenant-identity, URI-target, and epoch timestamp columns.
- A downgrade restores the old tables and columns but not the values that
  were removed. To roll back with your data, restore the backup.

To upgrade from 1.0.x to 2.0, follow these steps:

1. Take and check the backups described in
   [Back up the databases](#back-up-the-databases).
2. Stop every process that writes to the database: the backend, the Celery
   worker and Flower, the NATS consumer, and the notification worker.

   ```bash
   docker compose --env-file .env -f docker/m8flow-docker-compose.yml stop \
       m8flow-backend m8flow-celery-worker m8flow-celery-flower \
       m8flow-nats-consumer m8flow-notification-worker
   ```

   Don't run 1.0.x and 2.0 processes against the database at the same time.
   1.0.x can't run against the migrated schema.
3. Build the new images, then start only the backend so that it runs the
   migrations while nothing else writes:

   ```bash
   docker compose --env-file .env -f docker/m8flow-docker-compose.yml build
   docker compose --env-file .env -f docker/m8flow-docker-compose.yml up -d m8flow-backend
   docker compose --env-file .env -f docker/m8flow-docker-compose.yml logs -f m8flow-backend
   ```

   Wait until the logs show that the migrations have finished and the backend
   is serving requests.
4. Start the rest of the stack:

   ```bash
   docker compose --env-file .env -f docker/m8flow-docker-compose.yml up -d
   ```

If the migration fails on PostgreSQL, the whole migration rolls back, so you
can fix the reported data and start the backend again.

MySQL and MariaDB commit schema changes as they go, so a failed migration can
leave the schema half changed. Don't retry the migration. Restore the backup,
fix the reported data, and start again from step 2.

## Check the upgrade

To check that the upgrade worked, follow these steps:

1. Check that the backend is healthy:

   ```bash
   curl http://localhost:6840/v1.0/status
   ```

2. Sign in to the designer as a non-admin user, such as an `editor`, and open
   **Home** and the task inbox.
3. Sign in as a tenant admin and open the tenant's members.
4. Start an instance of a published process model and complete its first task.

## Roll back

If the upgrade fails, stop the stack, check out your previous version, restore
both databases from the backups, and start the stack again. A migration can
change the schema, so don't start an older version against an upgraded
database.

## Related pages

- [Versioning and deprecation policy](../reference/versioning.md)
- [Troubleshoot m8flow](troubleshoot.md)
- [Configuration](../reference/configuration.md)
