# Troubleshoot m8flow

Find the symptom you see, then follow the fix. If your problem isn't here,
search the [issue tracker](https://github.com/AOT-Technologies/m8flow/issues)
or open an issue with the bug report template.

## First checks

Before you look up a symptom, collect the following:

- **Container status.** Run
  `docker compose --env-file .env -f docker/m8flow-docker-compose.yml ps`.
  A service that is `exited` or `restarting` is usually the cause.
- **Backend health.** Run `curl http://localhost:6840/v1.0/status`. A healthy
  backend answers `{ "healthy": true, "ok": true, "status": "ok" }`.
- **Backend logs.** Run
  `docker compose --env-file .env -f docker/m8flow-docker-compose.yml logs --tail 200 m8flow-backend`.
  The backend logs the reason for most startup failures.
- **The user and tenant.** Many problems depend on the signed-in user's role
  and on the active tenant. Note both.

## Starting the stack

The following problems stop the stack from starting or signing in the first
time:

| Symptom | Cause | Fix |
|---|---|---|
| `docker compose up` fails with "port is already allocated" | Another program or container holds one of the ports 6840 to 6853 | Stop the other program, or change the port in `.env`. See [Services and ports](../reference/services-and-ports.md). |
| Platform admin sign-in fails with "Client not found" | The `keycloak-master-admin-init` job didn't run, so the master realm has no backend client | Start the stack with `--profile init`, as in the [quick start](../tutorials/quick-start.md). |
| Keycloak asks for a new password at first sign-in | The seeded users have temporary passwords | Expected. Choose a new password. |
| The backend logs "Connection refused" on port 6844 | `m8flow-node-wire-proxy` isn't running | Start it. The backend only needs it for service tasks. See [Run from source](run-from-source.md#the-backend-logs-connection-refused-on-port-6844). |
| The backend exits during startup while it migrates the database | A migration found data it can't convert safely | Read the migration's error in the backend log. Restore from your backup or fix the data it names, then start the backend again. See [Upgrade m8flow](upgrade.md). |

## Signing in and permissions

The following problems affect what a signed-in user can see or do:

| Symptom | Cause | Fix |
|---|---|---|
| An action is missing from the designer | The designer shows only the actions the backend allows for your role in the active tenant | Check the user's role in [Roles and permissions](../reference/roles-and-permissions.md), and that the right tenant is selected. |
| A user in two organizations sees the wrong tenant's data, or none | No tenant is selected, or the wrong one is | Select the tenant from the tenant picker. The active tenant comes from the `m8flow_selected_tenant` cookie, not from browser storage. |

## Processes and tasks

The following problems affect starting processes and working their tasks:

| Symptom | Cause | Fix |
|---|---|---|
| A process model can't be started | It's a draft or paused | Publish it. See [About process execution](../explanation/process-execution.md). |
| A user task doesn't appear in anyone's inbox | The task's lane doesn't map to a group the user belongs to | Check the lane's group, and the user's groups in the tenant. |
| Timers never fire | No Celery worker is running | Start `m8flow-celery-worker`, or run `./m8flow-backend/bin/run_m8flow_celery_worker.sh`. |
| A service task fails with a connection error | The connector proxy is down, or the connector profile has wrong credentials | Check `m8flow-node-wire-proxy` is running, then the profile. See [Call an external service from a process](call-external-services.md). |

## Event triggers

The following problems affect processes started by NATS triggers:

| Symptom | Cause | Fix |
|---|---|---|
| `POST /v1.0/m8flow/events/m8flow-trigger` answers `503 nats_signing_not_configured` | `M8FLOW_NATS_TOKEN_SALT` is unset, a published placeholder, or shorter than 32 characters | Generate one with `openssl rand -hex 32` and set the same value on the backend and `m8flow-nats-consumer`. Changing the salt invalidates issued API keys, so issue new ones. |
| `m8flow-nats-consumer` refuses to start | The same salt problem, or `M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS` isn't a positive whole number | Fix the setting named in the consumer's log. |
| Triggers are recorded as **Rejected: stale** | Events waited in the stream longer than `M8FLOW_NATS_TRIGGER_MAX_AGE_SECONDS`, for example during a consumer outage | Send them again. See the [consumer runbook](../../m8flow-nats-consumer/README.md#runbook-triggers-dropped-as-rejected_stale). |

[Trigger processes from external systems](trigger-processes-with-api-keys.md#check-delivery)
explains how to follow a trigger end to end.

## MCP server and the MCP Tools page

[Set up the MCP server and the MCP Tools page](set-up-mcp-tools.md#troubleshooting)
has a troubleshooting table for every banner the MCP Tools page shows.

## Running from source

The following problems affect running the backend and designer on your
machine:

| Symptom | Cause | Fix |
|---|---|---|
| The backend fails with "Failed building wheel" | The machine lacks build tools for native Python packages | See [Run from source](run-from-source.md#the-backend-fails-with-failed-building-wheel). |
| The designer fails with a missing Rollup package | npm skipped the platform-specific Rollup binary | See [Run from source](run-from-source.md#the-designer-fails-with-a-missing-rollup-package). |
| Designer tests fail on `localStorage` with Node.js 25 or later | Node's built-in Web Storage shadows jsdom's | Use Node.js 24, or run `NODE_OPTIONS=--no-webstorage npx vitest run`. |

## Still stuck

Open an issue with the
[bug report template](https://github.com/AOT-Technologies/m8flow/issues/new/choose).
Include the m8flow version, the signed-in user's role, the steps to reproduce,
and the relevant logs with passwords, tokens, and secrets removed. Report
security problems privately, as described in [SECURITY.md](../../SECURITY.md).
