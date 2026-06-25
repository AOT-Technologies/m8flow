# M8Flow Docker

This directory contains the Docker setup for running M8Flow: Compose files, Dockerfiles for app services, and the Keycloak reverse-proxy config.

**Environment variables:** Full meanings and examples live in [docs/env-reference.md](../docs/env-reference.md). This README only adds Docker Compose-specific behavior; do not duplicate the env reference here.

---

## File reference

| File | Purpose |
|------|--------|
| **m8flow-docker-compose.yml** | Main stack: Postgres, Keycloak, Redis, MinIO, backend, frontend, and optional init jobs. |
| **m8flow-docker-compose.prod.yml** | Override for production: Keycloak `start`, backend `prod` build target, `linux/amd64` platform. |
| **m8flow.backend.Dockerfile** | Builds the Python backend (SpiffWorkflow + m8flow extensions). Stages: `builder`, `prod`, `dev` (default). |
| **m8flow.frontend.Dockerfile** | Builds the frontend: Node build stages, final nginx:alpine serving static assets. |
| **m8flow.keycloak.Dockerfile** | Builds Keycloak 26 with the realm-info-mapper provider and baked-in realm imports. |
| **nginx-keycloak-proxy.conf** | Nginx config for the keycloak-proxy service: listen **6842** (container), proxy to keycloak:8080. |
| **minio.local-dev.docker-compose.yml** | Standalone MinIO for local dev (host ports `${MINIO_LOCAL_DEV_API_PORT:-16846}` / `${MINIO_LOCAL_DEV_CONSOLE_PORT:-16847}`, mounts local BPMN/templates dirs). |
| **m8flow-nats-docker-compose.yml** | NATS infrastructure: NATS server (with JetStream) and NATS UI. |

---

## Containers (m8flow-docker-compose.yml)

### Infrastructure

| Service | Image | Purpose | Ports | Configuration |
|---------|-------|---------|-------|----------------|
| **m8flow-db** | postgres:15 | Main app database (SpiffWorkflow + m8flow tables). | `${POSTGRES_HOST_PORT:-6843}` -> 5432 | `POSTGRES_*` from `.env`. Healthcheck: `pg_isready`. Data: volume `db-data`. |
| **keycloak-db** | postgres:15 | Keycloak's database. | (internal) | `KEYCLOAK_DB_NAME/USER/PASSWORD` (default keycloak/keycloak). Data: volume `keycloak-db-data`. |
| **keycloak** | Built (m8flow.keycloak.Dockerfile) | IdP: auth, shared realm, admin realm, and realm-info-mapper support. | `${KEYCLOAK_MGMT_PORT:-6849}` -> 9000 (management) | `KEYCLOAK_ADMIN*`, `KC_DB_*`, `KC_HTTP_PORT` (8080), `KC_HOSTNAME` (user-facing URL). Dev: `start-dev --import-realm`; prod override uses `start --import-realm`. Realms imported from image. Runs as user `keycloak`. |
| **keycloak-proxy** | nginx:alpine | Reverse proxy so browser and backend use one URL for Keycloak. | `${KEYCLOAK_PROXY_PORT:-6842}` -> 6842 | Uses `nginx-keycloak-proxy.conf`: listen 6842, `proxy_pass` to keycloak:8080. |
| **keycloak-init** | m8flow-keycloak (same image) | One-off: wait for Keycloak, then set `sslRequired=NONE`, enforce shared-realm org policy, and ensure the default shared-realm organization exists. | - | Depends on keycloak. `restart: "no"`. |
| **redis** | redis:6-alpine | Celery broker/result backend (optional). | 6379 -> 6379 | Persistence: `redis-data`. |
| **minio** | minio/minio (pinned) | S3-compatible object store for process models and templates. | 9000, 9001 (console) | `MINIO_ROOT_USER/PASSWORD` from `.env`. Data: volume `minio_data`. |

### Init jobs (profile `init`)

| Service | Image | Purpose | Configuration |
|---------|-------|---------|----------------|
| **minio-mc-init** | minio/mc | One-off: create MinIO buckets (via `minio_mc_init.sh`). | Mounts script from `docker/minio_mc_init.sh`. |
| **process-models-sync** | rclone/rclone | One-off: sync process models into MinIO (uses `process_models_sync.sh`, `rclone.conf`). | Uses volume `process_models_cache`. |
| **templates-sync** | rclone/rclone | One-off: sync templates into MinIO (uses `templates_sync.sh`, `rclone.conf`). | Uses volume `templates_cache`. |

Run with: `docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build`.

### App services

| Service | Build | Purpose | Ports | Configuration |
|---------|-------|---------|-------|----------------|
| **m8flow-backend** | m8flow.backend.Dockerfile | Flask/uvicorn API (SpiffWorkflow + m8flow extensions). Runs migrations on startup. | `${M8FLOW_BACKEND_PORT:-6840}` -> `${M8FLOW_BACKEND_PORT:-6840}` | DB: `m8flow-db`. Keycloak: `keycloak-proxy:6842`. Redis/Celery, MinIO URLs set for Docker. BPMN/templates dirs: volumes `process_models_cache`, `templates_cache` at `/app/data/process_models`, `/app/data/templates`. Entrypoint chowns those dirs then runs app as user `app` (UID 1000). Default build target: `dev`; prod override uses target `prod`. |
| **m8flow-frontend** | m8flow.frontend.Dockerfile | Nginx serving the built React app (core + extension). | `${M8FLOW_FRONTEND_PORT:-6841}` -> 8080 | Reads `.env` at build time (for example `MULTI_TENANT_ON`, `VITE_BACKEND_BASE_URL`). Listens on 8080 (non-root). Runs as user `nginx`. |

---

## Dockerfiles (summary)

### m8flow.python-base.Dockerfile

- Shared prebuilt base image (`docker.io/m8flow/m8flow-python-base:ubuntu24.04-py3.12`) carrying the OS toolchain (build-essential, libpq/mysql dev headers, gosu, git/curl/ssl) + Python 3.12 + pinned `uv`. Consumed by `m8flow.backend.Dockerfile` via the `PYTHON_BASE` build arg so service builds don't reinstall the toolchain every time. Built/pushed by `.github/workflows/build-base-image.yml`. **See [docs/docker-base-image.md](../docs/docker-base-image.md)** for dependency ownership, tagging, and the rebuild process.

### m8flow.backend.Dockerfile

All three stages start `FROM ${PYTHON_BASE}` (the shared base above), so the OS toolchain and `uv` are inherited rather than reinstalled.

- **builder:** copies `spiffworkflow-backend` + `spiff-arena-common` + `m8flow-backend`, creates `/opt/venv`, installs backend editable. Used only for `prod`.
- **prod:** Copies venv + app from builder. Creates user `app` (1000:1000). Entrypoint: chown `/app/data/process_models` and `/app/data/templates`, then `gosu app` to run CMD.
- **dev (default):** Full repo, editable install (`uv pip install --system`), then purges build-essential and CVE-prone packages from the final image. Same entrypoint and `app` user so volume permissions match prod.

### m8flow.frontend.Dockerfile

- **base:** Node 24 slim, build deps.
- **deps-core / deps-ext:** Install npm deps from lockfile only (for cache).
- **build-core / build-ext:** Copy source, build core and extension frontends; extension uses core's `python.ts` worker.
- **Final:** `nginx:alpine`. Copies built assets to `/usr/share/nginx/html` (extension at `/`, core at `/spiff`). Start script writes nginx config with `listen 0.0.0.0:8080`, then `exec nginx`. `chown` for user `nginx`, then `USER nginx`.

### m8flow.keycloak.Dockerfile

- **builder:** Eclipse Temurin 17 JDK, Maven 3.9.9. Builds `keycloak-extensions/realm-info-mapper` JAR.
- **Final:** `quay.io/keycloak/keycloak:26.6.1`. Copies JAR to `/opt/keycloak/providers/`, realm JSONs to `/opt/keycloak/data/import/`. Runs as `keycloak`. Health and feature flags set for dev/prod use.

---

## nginx-keycloak-proxy.conf

Used by the **keycloak-proxy** service. Listens on port **6842** inside the container and proxies all traffic to **keycloak:8080**. Host mapping is `${KEYCLOAK_PROXY_PORT:-6842}:6842`. Users and the backend use `http://<host>:<KEYCLOAK_PROXY_PORT>` on the host; inside Compose the backend uses `KEYCLOAK_URL` / `M8FLOW_KEYCLOAK_URL` -> `http://keycloak-proxy:6842`.

---

## minio.local-dev.docker-compose.yml

Standalone MinIO for local development when not using the full stack:

- Ports **`${MINIO_LOCAL_DEV_API_PORT:-16846}`** (API) and **`${MINIO_LOCAL_DEV_CONSOLE_PORT:-16847}`** (console) to avoid clashing with the main stack's MinIO host ports (6846/6847 by default).
- Mounts `M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR` and `M8FLOW_TEMPLATES_STORAGE_DIR` (or defaults) so you can point the backend at local dirs instead of MinIO in the main stack.

Run with: `docker compose -f docker/minio.local-dev.docker-compose.yml up -d`.

---

## Production override (m8flow-docker-compose.prod.yml)

Use with: `docker compose -f docker/m8flow-docker-compose.yml -f docker/m8flow-docker-compose.prod.yml up -d`.

- **keycloak:** `command: ["start", "--import-realm"]` (production mode).
- **m8flow-backend:** `build.target: prod`, `platform: linux/amd64`.
- **m8flow-frontend:** `platform: linux/amd64`.

Set production values in `.env` (for example `KEYCLOAK_HOSTNAME`, `M8FLOW_BACKEND_DATABASE_URI`, secrets) before running.

**Docker Compose caveat:** The `m8flow-backend` service sets `KEYCLOAK_URL` and `M8FLOW_KEYCLOAK_URL` to `http://keycloak-proxy:6842` so server-side calls use the proxy, while browsers use the public URL (often `http://localhost:6842` or `http://<host>:6842`). For all other env semantics, see [docs/env-reference.md](../docs/env-reference.md).

---

## Non-root and ports

- **Backend:** Runs as user `app` (UID 1000). Entrypoint runs as root only to chown the two volume mount dirs, then execs the app via gosu.
- **Frontend:** Runs as user `nginx`, listens on **8080** inside the container; host port (default **6841**) is mapped to 8080.
- **Keycloak:** Base image runs as user `keycloak`; we keep that.

---

## Quick commands

From the repository root:

```bash
# Full stack (dev backend, no init)
docker compose -f docker/m8flow-docker-compose.yml up -d --build

# Full stack + first-time init (MinIO buckets, process-models and templates sync)
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build

# Production
docker compose -f docker/m8flow-docker-compose.yml -f docker/m8flow-docker-compose.prod.yml up -d --build

# Stop and remove volumes
docker compose -f docker/m8flow-docker-compose.yml down -v
```

Access the app at **http://localhost:6841** (or the host/port you set for the frontend). Keycloak admin and auth: **http://localhost:6842**.

---

## NATS Infrastructure (Optional)

If you require event-driven features, you can start the NATS infrastructure (server and UI) using the dedicated compose file.

### Prerequisites

The NATS stack expects the `m8flow_default` network (created when you start the main stack).

1. **Ensure the network exists**:
   The `m8flow_default` network is automatically created when you start the main `m8flow-docker-compose.yml` stack.

### Running NATS

1. **Start NATS and NATS UI**:

   ```bash
   docker compose -f docker/m8flow-nats-docker-compose.yml up -d
   ```

2. **Configure M8Flow**:
   Set `M8FLOW_NATS_ENABLED=true` in your `.env` file to enable NATS features in the backend.

3. **Start the NATS Consumer**:
   The `m8flow-nats-consumer` service is included in the main stack under the `nats` profile. Start it with:
   ```bash
   docker compose --profile nats -f docker/m8flow-docker-compose.yml up -d
   ```

NATS Client: `nats://${M8FLOW_NATS_USER:-admin}:${M8FLOW_NATS_PASSWORD:-admin}@localhost:${M8FLOW_NATS_PORT:-6845}`
NATS Monitoring: `http://localhost:${M8FLOW_NATS_MONITORING_PORT:-6851}`
NATS UI (NUI): `http://localhost:${M8FLOW_NATS_UI_PORT:-6852}`

**NATS Credentials**:
The default username/password is `admin:admin`. You can customize these in your `.env` file via `M8FLOW_NATS_USER` and `M8FLOW_NATS_PASSWORD`.
