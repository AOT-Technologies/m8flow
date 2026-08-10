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
   `docker compose --env-file .env -f docker/m8flow-docker-compose.yml up -d --force-recreate m8flow-backend m8flow-connector-proxy`
   (The dev backend image bakes `.env` at build time; compose now bind-mounts the host file.)
3. Use the app for a minute, then refresh dashboards. Service log panels expect OTLP labels like `service_name="m8flow-backend"`.
4. **Backend HTTP metrics:** rebuild the backend image after telemetry changes (`docker compose ... build m8flow-backend`) — the image must include `m8flow-telemetry[flask,asgi]` for Uvicorn/ASGI. Dashboards use `job="m8flow-backend"` and `http_server_duration_milliseconds_*`.
5. In **Explore → Loki**, try `{service_name="keycloak"}` or `{container=~".*keycloak.*"}` for Docker-tailed stdout before OTLP is enabled.
