# Grafana / Loki — unified logs for M8Flow services

This stack combines:

1. **OTLP logs** from Python services (`m8flow-backend`, `m8flow-celery-worker`, `m8flow-connector-proxy`) → OpenTelemetry Collector inside [`grafana/otel-lgtm`](https://hub.docker.com/r/grafana/otel-lgtm) → **Loki**.
2. **Docker container logs** from JVM/nginx/Flower (no OTLP log export in-repo) via **Promtail** → Loki.

Configuration lives in:

- [`docker/m8flow-docker-compose.yml`](../docker/m8flow-docker-compose.yml) — `otel-lgtm`, `promtail`, OTLP env vars.
- [`docker/promtail-config.yaml`](../docker/promtail-config.yaml) — which containers are scraped (avoid duplicating OTLP stdout).
- [`docker/grafana/dashboards/m8flow-unified-logs.json`](../docker/grafana/dashboards/m8flow-unified-logs.json) — starter dashboard (mounted into Grafana).

## Quick start

```bash
docker compose -f docker/m8flow-docker-compose.yml up -d otel-lgtm promtail m8flow-backend m8flow-celery-worker m8flow-connector-proxy keycloak
```

Open Grafana at [`http://localhost:${GRAFANA_HTTP_PORT:-3000}`](http://localhost:3000) → **Dashboards → M8Flow → M8Flow Unified Logs**.

Default Grafana credentials for `grafana/otel-lgtm` are typically **`admin` / `admin`** unless you changed auth via [`docs/grafana-keycloak.md`](grafana-keycloak.md).

## Label cheat sheet

| Source | Primary selectors | Notes |
|--------|-------------------|--------|
| OTLP (Python) | `service_name` | Compose sets `OTEL_SERVICE_NAME`: `m8flow-backend`, `m8flow-celery-worker`, `m8flow-connector-proxy`. |
| Promtail (Docker) | `compose_service` | Matches Compose service name: `keycloak`, `keycloak-proxy`, `m8flow-celery-flower`. |

If **Explore → Loki → Label browser** shows different keys (e.g. `service.name` vs `service_name`), adjust dashboard queries — the LGTM image maps OTLP resource attributes to Loki labels.

### Avoiding duplicate logs

Promtail **does not** scrape stdout for `m8flow-backend`, `m8flow-celery-worker`, or `m8flow-connector-proxy`, because those apps already export logs over OTLP; scraping Docker logs too would duplicate lines.

## Connector-specific logs

The connector proxy prefixes log lines with `m8flow_connector=<token>` (see [`m8flow-connector-proxy/m8flow_connector_context.py`](../m8flow-connector-proxy/m8flow_connector_context.py)).

Example LogQL:

```logql
{service_name="m8flow-connector-proxy"} |= "m8flow_connector=smtp"
```

Adjust the `|= "..."` filter for `slack`, `http`, etc.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Promtail errors connecting to Loki | `otel-lgtm` must be running; Loki listens on **3100** inside that container (`http://otel-lgtm:3100`). |
| Promtail cannot read Docker | Mount `/var/run/docker.sock` (see compose). On rootless Docker, paths may differ. |
| Empty OTLP panels | Confirm `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-lgtm:4317` on the service and that the app process started OTEL (`otel_setup`). |
| Empty Promtail panels | Confirm container names match the allowlist regex in `promtail-config.yaml`. |

## Related

- Grafana Sign-In / env switches: [`grafana-keycloak.md`](grafana-keycloak.md)
- Environment variables reference: [`env-reference.md`](env-reference.md)
