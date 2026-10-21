# Enable logs, metrics, and traces

Run the optional observability stack next to m8flow to see logs, metrics,
traces, and ready-made dashboards in Grafana. The stack uses Grafana Alloy,
Loki, Tempo, and Prometheus, and it is off by default.

## Prerequisites

You need the main Compose stack running, because the observability stack
joins its network.

## Start the stack

To send telemetry to Grafana, follow these steps:

1. Start the observability stack:

   ```bash
   docker compose --env-file .env \
       -f docker/m8flow-observability-docker-compose.yml up -d
   ```

2. In `.env`, turn on the OpenTelemetry SDK and point it at Alloy:

   ```bash
   OTEL_SDK_DISABLED=false
   OTEL_EXPORTER_OTLP_ENDPOINT=http://m8flow-alloy:4317
   ```

3. Recreate the app containers so they read the new values:

   ```bash
   docker compose --env-file .env -f docker/m8flow-docker-compose.yml \
       up -d --force-recreate m8flow-backend m8flow-node-wire-proxy
   ```

4. Open Grafana at `http://localhost:6868` and sign in with
   `M8FLOW_GRAFANA_ADMIN_USER` and `M8FLOW_GRAFANA_ADMIN_PASSWORD` from `.env`.

Use m8flow for a minute, then refresh the dashboards.

## Dashboards

Grafana loads the dashboards from `docker/observability/grafana/` at startup.
The main ones are:

| Dashboard | Shows |
|---|---|
| M8Flow Application Health | Service up or down, HTTP rate, 5xx errors, p99 latency, process instances created and completed, tasks completed |
| M8Flow SQL / Postgres | Query rate, statement latency, cache hits, sequential scans, slow queries |
| M8Flow NATS Trigger Consumer Overview | Trigger deliveries and failures by outcome |
| M8Flow NATS Notification Worker Overview | Notification stream and worker health |

Each dashboard has a tenant filter that defaults to all tenants.

## Query the logs

`m8flow-backend` writes one JSON object per line, with fields such as `level`,
`tenant_id`, `request_id`, `trace_id`, `error_code`, and `http_status`. In
**Explore** > **Loki**, parse the JSON and filter on those fields.

The following queries are useful starting points:

```logql
{service_name="m8flow-backend"} | json | __error__="" | level=~"ERROR|CRITICAL"
{service_name="m8flow-backend"} | json | __error__="" | tenant_id="acme"
{service_name="m8flow-backend"} | json | __error__="" | request_id="<request-id>"
{service_name="m8flow-backend"} |= "sql query slow" | json | __error__=""
```

Replace `<request-id>` with the request ID from an error response or log line.

Celery, the connector proxy, MCP, NATS, and the designer's nginx write plain
text. Don't add `| json` to queries for those services.

## Tune slow-query logging

The backend logs a `sql query slow` line for any statement slower than
`M8FLOW_SQL_SLOW_MS` milliseconds (100 by default). Set it to `0` to log every
statement, or to `off` to stop statement lines.

## Troubleshoot empty dashboards

If dashboards stay empty, check the following:

- `OTEL_SDK_DISABLED` is `false` in the repository-root `.env`.
- You recreated the app containers after you changed `.env`.
- The service has produced log lines. A quiet service shows as down until it
  logs something.

## Related pages

- [Services and ports](../reference/services-and-ports.md)
- [Configuration](../reference/configuration.md)
