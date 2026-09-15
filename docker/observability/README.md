# M8Flow observability stack (opt-in)

Start alongside the main app stack:

```bash
docker compose -f docker/m8flow-docker-compose.yml up -d
docker compose -f docker/m8flow-observability-docker-compose.yml up -d
```

Set in `.env` (see `sample.env`):

- `OTEL_EXPORTER_OTLP_ENDPOINT=http://m8flow-alloy:4317` for app containers on `m8flow_default`
- `M8FLOW_FRONTEND_FARO_COLLECTOR_URL=http://localhost:6865/collect` for browser-reachable Faro

Grafana: `http://localhost:6868` (default admin/admin from env).

Dashboards and datasources are provisioned from this directory at startup.

**Logs look empty?**

1. Set `OTEL_SDK_DISABLED=false` in the repo-root `.env` (not only in the UI).
2. Recreate app containers so Compose picks up env **and** the mounted `/app/.env` matches:
   `docker compose --env-file .env -f docker/m8flow-docker-compose.yml up -d --force-recreate m8flow-backend m8flow-node-wire-proxy`
   (The dev backend image bakes `.env` at build time; compose now bind-mounts the host file.)
3. Use the app for a minute, then refresh dashboards. Service log panels expect OTLP labels like `service_name="m8flow-backend"`.
4. **Application Health dashboard:** `M8Flow Application Health` (`m8flow-application`) is service UP/DOWN (backend, frontend, celery, nats, nats-consumer, node-wire, keycloak, postgres), HTTP rate/5xx/p99, and **process instances created / completed / tasks completed**. Latency and instance duration need a backend image that emits `request completed` (`duration_ms`) and `process instance completed` (`duration_seconds`).
5. **SQL / Postgres dashboard:** `M8Flow SQL / Postgres` (`m8flow-postgres`) is query rate, statement latency, cache hit, sequential scans, and slow-query logs. It needs `postgres_exporter` (this stack), `pg_stat_statements` on `m8flow-db` (compose enables it), and a backend image that emits `sql_duration_ms` / `sql_query_count` on `request completed`.
6. In **Explore → Loki**, try `{service_name="keycloak"}` or `{container=~".*keycloak.*"}` for Docker-tailed stdout before OTLP is enabled.

## LogQL (structured logs)

`m8flow-backend` stdout is one JSON object per line (`level`, `tenant_id`, `request_id`, `trace_id`, `error_code`, `error_kind`, `http_status`). Keycloak uses Quarkus JSON (`level`, `loggerName`, `message`). `| json | __error__=""` keeps those lines and drops OTLP/plaintext duplicates that are not JSON.

Do **not** `| json` Celery, connector-proxy, MCP, NATS, or frontend nginx access logs (plaintext — that query returns `JSONParserErr`).

```logql
{service_name="m8flow-backend"} | json | __error__="" | level=~"ERROR|CRITICAL"
{service_name="m8flow-backend"} | json | __error__="" | tenant_id="acme"
{service_name="m8flow-backend"} | json | __error__="" | error_code="permission_denied"
{service_name="m8flow-backend"} | json | __error__="" | request_id="…"
{service_name="m8flow-backend"} |= "sql query slow" | json | __error__=""
{service_name="keycloak"} | json | __error__="" | level="ERROR"
{service_name="m8flow-db"} |~ "duration:|still waiting"
```

The tenant textbox on dashboards defaults to `.*` (all). Replace it with a tenant id to filter.

`error_code` / `error_kind` (`client` = 4xx, `server` = 5xx) are the existing API error codes on the log line — not a second taxonomy.

**Process instances created / Task completed** live on **M8Flow Application Health**, not Backend Overview. They count JSON logs (`Initialized workflow`; UserTask/ServiceTask `State changed to COMPLETED`) and show **0** when nothing happened in the range. **HTTP p99** and **avg process duration** need `request completed` (`duration_ms`) and `process instance completed` (`duration_seconds`). **Log ERROR** uses `level` ERROR|CRITICAL — a substring match on `error` falsely counts INFO lines whose payload contains `"error": null`. **Service UP/DOWN** is “Loki saw logs from that container in the last hour” (range query). A 2-minute instant query is empty in this Loki setup, and quiet services (frontend nginx) look DOWN until Alloy is tailing them and they emit a line.

## SQL / Postgres dashboard

`M8Flow SQL / Postgres` (`m8flow-postgres`) is separate from Application Health and Backend Overview.

| Signal | Source | What it answers |
|--------|--------|-----------------|
| Commit / statement rate, cache hit, backends, temp files, deadlocks | Prometheus `postgres_exporter` | Is the database busy, cache-cold, or spilling to disk? |
| Hottest / top / slowest statements (full `query` text, inspect a cell) | Grafana Postgres datasource (`pg_stat_statements`) | Which SQL to optimize. Text is Postgres-normalized (`$1` placeholders); bind values are not stored |
| `sql_duration_ms`, `sql_query_count`, pool checked-out | Backend JSON `request completed` | HTTP vs SQL split and N+1 |
| `sql query slow` | Backend JSON (threshold `M8FLOW_SQL_SLOW_MS`, default 100ms) | The statement preview that crossed the bar |
| `duration:` / lock waits | `m8flow-db` stdout (`log_min_duration_statement=250`) | Server-side slow queries and blocking |

`pg_stat_statements` is enabled on `m8flow-db` (`shared_preload_libraries` + a one-shot `CREATE EXTENSION`). Restart Postgres after pulling that compose change; existing `db-data` is kept. The Grafana Postgres datasource talks to `m8flow-db` as `POSTGRES_USER` (local-dev only). Prometheus panels on this dashboard use datasource **Prometheus cluster** (`prometheus-cluster` → `m8flow-prometheus:9090`) because SQL metrics are not tenant-scoped. Tenant orgs may still have a **Prometheus** uid that goes through `m8flow-prom-label-proxy` (often 502).
