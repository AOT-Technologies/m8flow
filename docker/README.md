# M8Flow Docker

This directory contains the Docker setup for running M8Flow: Compose files, Dockerfiles for app services, and the Keycloak reverse-proxy config.

---

## File reference

| File | Purpose |
|------|--------|
| **m8flow-docker-compose.yml** | Main stack: Postgres, Keycloak, Redis, MinIO, backend, frontend, and optional init jobs. |
| **m8flow-docker-compose.prod.yml** | Override for production: Keycloak `start`, backend `prod` build target, `linux/amd64` platform. |
| **m8flow.backend.Dockerfile** | Builds the Python backend (SpiffWorkflow + m8flow extensions). Stages: `builder`, `prod`, `dev` (default). |
| **m8flow.frontend.Dockerfile** | Builds the frontend: Node build stages, final nginx:alpine serving static assets. |
| **m8flow.keycloak.Dockerfile** | Builds Keycloak 26 with the realm-info-mapper provider and baked-in realm imports. |
| **nginx-keycloak-proxy.conf** | Nginx config for the keycloak-proxy service: listen 7002, proxy to keycloak:8080. |
| **minio.local-dev.docker-compose.yml** | Standalone MinIO for local dev (different ports, mounts local BPMN/templates dirs). |

---

## Containers (m8flow-docker-compose.yml)

### Infrastructure

| Service | Image | Purpose | Ports | Configuration |
|---------|-------|---------|-------|----------------|
| **m8flow-db** | postgres:15 | Main app database (SpiffWorkflow + m8flow tables). | 1111→5432 | `POSTGRES_*` from `.env`. Healthcheck: `pg_isready`. Data: volume `db-data`. |
| **keycloak-db** | postgres:15 | Keycloak’s database. | (internal) | `KEYCLOAK_DB_NAME/USER/PASSWORD` (default keycloak/keycloak). Data: volume `keycloak-db-data`. |
| **keycloak** | Built (m8flow.keycloak.Dockerfile) | IdP: auth, realms, realm-info-mapper for `m8flow_tenant_*` claims. | 7009→9000 (management) | `KEYCLOAK_ADMIN*`, `KC_DB_*`, `KC_HTTP_PORT` (8080), `KC_HOSTNAME` (user-facing URL). Dev: `start-dev --import-realm`; prod override uses `start --import-realm`. Realms imported from image. Runs as user `keycloak`. |
| **keycloak-proxy** | nginx:alpine | Reverse proxy so browser and backend use one URL for Keycloak. | 7002→7002 | Uses `nginx-keycloak-proxy.conf`: listen 7002, `proxy_pass` to keycloak:8080. |
| **keycloak-init** | m8flow-keycloak (same image) | One-off: wait for Keycloak, then set `sslRequired=NONE` on master, tenant-a, identity. | — | Depends on keycloak. `restart: "no"`. |
| **redis** | redis:6-alpine | Celery broker/result backend (optional). | 6379→6379 | Persistence: `redis-data`. |
| **minio** | minio/minio (pinned) | S3-compatible object store for process models and templates. | 9000, 9001 (console) | `MINIO_ROOT_USER/PASSWORD` from `.env`. Data: volume `minio_data`. |

### Init jobs (profile `init`)

| Service | Image | Purpose | Configuration |
|---------|-------|---------|----------------|
| **minio-mc-init** | minio/mc | One-off: create MinIO buckets (via `minio_mc_init.sh`). | Mounts script from `extensions/m8flow-backend/bin/`. |
| **process-models-sync** | rclone/rclone | One-off: sync process models into MinIO (uses `process_models_sync.sh`, `rclone.conf`). | Uses volume `process_models_cache`. |
| **templates-sync** | rclone/rclone | One-off: sync templates into MinIO (uses `templates_sync.sh`, `rclone.conf`). | Uses volume `templates_cache`. |

Run with: `docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build`.

### App services

| Service | Build | Purpose | Ports | Configuration |
|---------|-------|---------|-------|----------------|
| **m8flow-backend** | m8flow.backend.Dockerfile | Flask/uvicorn API (SpiffWorkflow + m8flow extensions). Runs migrations on startup. | M8FLOW_BACKEND_PORT (default 7000)→8000 | DB: `m8flow-db`. Keycloak: `keycloak-proxy:7002`. Redis/Celery, MinIO URLs set for Docker. BPMN/templates dirs: volumes `process_models_cache`, `templates_cache` at `/app/process_models`, `/app/templates`. Entrypoint chowns those dirs then runs app as user `app` (UID 1000). Default build target: `dev`; prod override uses target `prod`. |
| **m8flow-frontend** | m8flow.frontend.Dockerfile | Nginx serving the built React app (core + extension). | M8FLOW_FRONTEND_PORT (default 7001)→8080 | Reads `.env` at build time (e.g. `MULTI_TENANT_ON`, `VITE_BACKEND_BASE_URL`). Listens on 8080 (non-root). Runs as user `nginx`. |

---

## Dockerfiles (summary)

### m8flow.backend.Dockerfile

- **builder:** Python 3.12 slim, build deps, copies `spiffworkflow-backend` + `extensions`, creates `/opt/venv`, installs backend non-editable. Used only for `prod`.
- **prod:** Slim runtime (libpq5, ca-certificates, gosu). Copies venv + app from builder. Creates user `app` (1000:1000). Entrypoint: chown `/app/process_models` and `/app/templates`, then `gosu app` to run CMD. No build tools.
- **dev (default):** Full repo, build deps, editable install (`uv pip install -e .`). Same entrypoint and `app` user so volume permissions match prod.

### m8flow.frontend.Dockerfile

- **base:** Node 24 slim, build deps.
- **deps-core / deps-ext:** Install npm deps from lockfile only (for cache).
- **build-core / build-ext:** Copy source, build core and extension frontends; extension uses core’s `python.ts` worker.
- **Final:** nginx:alpine. Copies built assets to `/usr/share/nginx/html` (extension at `/`, core at `/spiff`). Start script writes nginx config with `listen 0.0.0.0:8080`, then `exec nginx`. `chown` for user `nginx`, then `USER nginx`.

### m8flow.keycloak.Dockerfile

- **builder:** Eclipse Temurin 17 JDK, Maven 3.9.9. Builds `keycloak-extensions/realm-info-mapper` JAR.
- **Final:** quay.io/keycloak/keycloak:26.0.7. Copies JAR to `/opt/keycloak/providers/`, realm JSONs to `/opt/keycloak/data/import/`. Runs as `keycloak`. Health and feature flags set for dev/prod use.

---

## nginx-keycloak-proxy.conf

Used by the **keycloak-proxy** service. Listens on port **7002**, proxies all traffic to **keycloak:8080**. So users and the backend use `http://<host>:7002` for Keycloak; the backend is configured with `KEYCLOAK_URL` / `M8FLOW_KEYCLOAK_URL` pointing at keycloak-proxy:7002.

---

## minio.local-dev.docker-compose.yml

Standalone MinIO for local development when not using the full stack:

- Ports **19000** (API) and **19001** (console) to avoid clashing with main compose.
- Mounts `M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR` and `M8FLOW_TEMPLATES_STORAGE_DIR` (or defaults) so you can point the backend at local dirs instead of MinIO in the main stack.

Run with: `docker compose -f docker/minio.local-dev.docker-compose.yml up -d`.

---

## Production override (m8flow-docker-compose.prod.yml)

Use with: `docker compose -f docker/m8flow-docker-compose.yml -f docker/m8flow-docker-compose.prod.yml up -d`.

- **keycloak:** `command: ["start", "--import-realm"]` (production mode).
- **m8flow-backend:** `build.target: prod`, `platform: linux/amd64`.
- **m8flow-frontend:** `platform: linux/amd64`.

Set production values in `.env` (e.g. `KEYCLOAK_HOSTNAME`, `M8FLOW_BACKEND_DATABASE_URI`, secrets) before running.

---

## Non-root and ports

- **Backend:** Runs as user `app` (UID 1000). Entrypoint runs as root only to chown the two volume mount dirs, then execs the app via gosu.
- **Frontend:** Runs as user `nginx`, listens on **8080** inside the container; host port (e.g. 7001) is mapped to 8080.
- **Keycloak:** Base image runs as user `keycloak`; we keep that.

---

## Quick commands

From the repository root:

```bash
# Full stack (dev backend, no init)
docker compose -f docker/m8flow-docker-compose.yml up -d --build

# Full stack + first-time init (MinIO buckets, process-models and templates sync)
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build

# Production (AWS Linux style)
docker compose -f docker/m8flow-docker-compose.yml -f docker/m8flow-docker-compose.prod.yml up -d --build

# Stop and remove volumes
docker compose -f docker/m8flow-docker-compose.yml down -v
```

Access the app at **http://localhost:7001** (or the host/port you set for the frontend). Keycloak admin and auth: **http://localhost:7002**.
