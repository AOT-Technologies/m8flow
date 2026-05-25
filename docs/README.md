# m8flow Documentation

This folder contains project documentation for setup, architecture, and development workflows.

## Index

- [Repository structure](#repository-structure)
- [Prerequisites (local dev, without Docker)](#prerequisites-local-dev-without-docker)
- [Running locally (without Docker for backend/frontend)](#running-locally-without-docker-for-backendfrontend)
  - [Step 1 — Fetch upstream SpiffWorkflow source](#step-1--fetch-upstream-spiffworkflow-source-required)
  - [Step 2 — Start infrastructure services (Docker)](#step-2--start-infrastructure-services-docker)
  - [Step 3 — Start the backend](#step-3--start-the-backend)
  - [Step 4 — Start the frontend](#step-4--start-the-frontend)
  - [Step 5 — Run a Celery worker](#step-5--run-a-celery-worker)
- [Access the application with multitenant mode off](#access-the-application-with-multitenant-mode-off)
- [Sample Templates](#sample-templates)
- [Integration Services](#integration-services)
- [Troubleshooting](#troubleshooting)

---

## Repository Structure

```text
m8flow/
├── bin/                          # Developer helper scripts
│   ├── fetch-upstream.sh         # Fetch upstream source folders on demand (Bash)
│   ├── fetch-upstream.ps1        # Fetch upstream source folders on demand (PowerShell)
│   └── diff-from-upstream.sh     # Report local vs upstream divergence
│
├── docker/                       # All Docker and Compose files
│   ├── m8flow-docker-compose.yml         # Primary local dev stack
│   ├── m8flow-docker-compose.prod.yml    # Production overrides
│   ├── m8flow.backend.Dockerfile
│   ├── m8flow.frontend.Dockerfile
│   ├── m8flow.keycloak.Dockerfile
│   ├── minio.local-dev.docker-compose.yml
│   └── minio.production.docker-compose.yml
│
├── docs/                         # Documentation and images
│   └── env-reference.md          # Canonical environment variable reference
│
├── m8flow-backend/               # m8flow backend layer (Apache 2.0)
│   ├── bin/                      # Backend run/migration scripts
│   ├── keycloak/                 # Realm exports and Keycloak setup scripts
│   ├── migrations/               # Alembic migrations for m8flow-owned tables
│   ├── src/m8flow_backend/       # Backend source code (incl. startup + ASGI entry)
│   │   ├── app.py                # ASGI entry point (uvicorn target)
│   │   ├── bootstrap.py          # Pre/post-app patch bootstrap helpers
│   │   └── startup/              # Backend startup wiring (env mapping, patches, hooks)
│   └── tests/
│
├── m8flow-frontend/              # m8flow frontend layer (Apache 2.0)
│   └── src/
│
├── keycloak-extensions/          # Keycloak realm-info-mapper provider (JAR)
│
├── m8flow-connector-proxy/       # m8flow connector proxy service (Apache 2.0)
│
├── m8flow-nats-consumer/         # NATS event consumer service
│
├── upstream.sources.json         # Canonical upstream repo/ref/folder config
├── sample.env                    # Environment variable template
└── LICENSE                       # Apache License 2.0

# -- Gitignored, fetched via bin/fetch-upstream.sh / bin/fetch-upstream.ps1 --
# spiffworkflow-backend/          Upstream LGPL-2.1 workflow engine
# spiffworkflow-frontend/         Upstream LGPL-2.1 BPMN modeler UI
# spiff-arena-common/             Upstream LGPL-2.1 shared utilities
```

**Why are those directories missing?**
`spiffworkflow-backend`, `spiffworkflow-frontend`, and `spiff-arena-common` come from [AOT-Technologies/m8flow-core](https://github.com/AOT-Technologies/m8flow-core) (LGPL-2.1). They are not stored here to keep m8flow's Apache 2.0 license boundary clean. Run `./bin/fetch-upstream.sh` or `.\bin\fetch-upstream.ps1` once after cloning to populate them.

---

## Prerequisites (local dev, without Docker)

The list below assumes a **clean machine**. If a tool is already installed, skip its install step and continue — instructions throughout this guide call out the resume point. Verify with the version commands at the end of each row.

| Tool | Minimum version | Verify with | Why it's needed |
|------|-----------------|-------------|-----------------|
| **Git** | any recent | `git --version` | Cloning the repo and fetching upstream |
| **Docker Desktop** / Docker Engine + Compose v2 | Compose v2 | `docker compose version` | Runs the infrastructure containers (Postgres, Keycloak, MinIO, Redis) |
| **Python** | 3.11+ | `python --version` | Backend runtime |
| **[uv](https://docs.astral.sh/uv/)** | latest | `uv --version` | Python env + dependency manager used by the backend launcher |
| **jq** | any | `jq --version` | Required by `bin/fetch-upstream.sh` to parse `upstream.sources.json` |
| **Node.js + npm** | Node 18+ (LTS) | `node --version`, `npm --version` | Frontend dev server (`m8flow-frontend`) |
| **curl** | any | `curl --version` | Health-check the backend `/v1.0/status` endpoint |

### Install commands per platform

> **These are either/or — run only the section for your OS.** Don't run them all.

#### macOS (Homebrew)

```bash
brew install git jq uv node
# Docker Desktop: install from https://www.docker.com/products/docker-desktop/
```

#### Ubuntu / Debian / WSL (Ubuntu)

A clean Ubuntu or WSL install is typically missing several of these. Install everything in one go:

```bash
sudo apt-get update
sudo apt-get install -y git jq curl build-essential python3 python3-venv python3-dev
# uv (single-line installer):
curl -LsSf https://astral.sh/uv/install.sh | sh
# Node.js (NodeSource LTS):
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs
```

> **Note:** `build-essential` and `python3-dev` are required so Python packages with native extensions can build from source on a clean Ubuntu/WSL install. Skipping them produces the *"Failed building wheel"* / *"missing package metadata"* errors documented in [Troubleshooting](#troubleshooting).

#### Windows (PowerShell, via winget)

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
winget install --id jqlang.jq -e
winget install --id OpenJS.NodeJS.LTS -e
# Docker Desktop: install from https://www.docker.com/products/docker-desktop/
```

> Restart your shell after installing so new tools are on `PATH`.

---

## Running Locally (without Docker for backend/frontend)

Use this mode for active development of m8flow extensions. Make sure you have completed the [Prerequisites](#prerequisites-local-dev-without-docker) above.

### Step 1 — Fetch upstream SpiffWorkflow source (required)

> **Don't skip this step.** The upstream `spiffworkflow-backend`, `spiffworkflow-frontend`, and `spiff-arena-common` directories are **gitignored** and not present after a fresh clone. The backend will not start without them.

Run **only the command for your OS** — these are either/or, not sequential:

**Linux / macOS / WSL**

```bash
./bin/fetch-upstream.sh
```

**Windows (PowerShell)**

```powershell
.\bin\fetch-upstream.ps1
```

This populates `spiffworkflow-backend/`, `spiffworkflow-frontend/`, and `spiff-arena-common/` at the upstream tag pinned in [`upstream.sources.json`](../upstream.sources.json).

### Step 2 — Start infrastructure services (Docker)

Start the infrastructure containers (database, Keycloak, MinIO, Redis), one-time init jobs (`minio-mc-init`, `keycloak-master-admin-init`), and the connector proxy — **but not** the `m8flow-backend` or `m8flow-frontend` containers, since those will run locally.

Run **only the command for your shell** — these are either/or, not sequential:

**Linux / macOS / WSL (bash, `\` continuation)**

```bash
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build \
  m8flow-db keycloak-db keycloak keycloak-proxy redis minio \
  minio-mc-init keycloak-master-admin-init \
  m8flow-connector-proxy
```

**Windows (PowerShell, backtick `` ` `` continuation)**

```powershell
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build `
  m8flow-db keycloak-db keycloak keycloak-proxy redis minio `
  minio-mc-init keycloak-master-admin-init `
  m8flow-connector-proxy
```

> **PowerShell users:** do not paste the bash version — `\` is not a line-continuation in PowerShell and each wrapped line will be interpreted as a separate command. If unsure, run the single-line form instead:
>
> ```powershell
> docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build m8flow-db keycloak-db keycloak keycloak-proxy redis minio minio-mc-init keycloak-master-admin-init m8flow-connector-proxy
> ```

What each service is for:

| Service | Role |
|---|---|
| `m8flow-db`, `keycloak-db` | PostgreSQL for m8flow app data and Keycloak |
| `keycloak`, `keycloak-proxy` | Identity provider |
| `redis`, `minio` | Celery broker and object storage |
| `minio-mc-init` *(init)* | Creates required MinIO buckets |
| `keycloak-master-admin-init` *(init)* | **Required for "Global admin sign in".** Creates the `m8flow-backend` client and `super-admin` user in the **master** realm. Without it, the master-realm login flow fails with *"Client not found"*. |
| `m8flow-connector-proxy` | Backend dispatches connector commands here (SMTP, Slack, HTTP). Without it, the backend logs `WinError 10061` on port 6844. |

> If you previously ran the full Docker stack, **stop the `m8flow-backend` and `m8flow-frontend` containers** before continuing — otherwise the local dev servers will collide on ports 6840/6841.

### Step 3 — Start the backend

Run **only the command for your OS** — these are either/or:

**Linux / macOS / WSL**

```bash
./m8flow-backend/bin/run_m8flow_backend.sh 6840 --reload
```

**Windows (PowerShell)**

```powershell
.\m8flow-backend\bin\run_m8flow_backend.ps1 6840
```

When `uv` is available locally, the backend launcher syncs backend dependencies automatically before starting and runs the backend through `uv`. Set `M8FLOW_BACKEND_SYNC_DEPS=false` to skip sync, or `M8FLOW_BACKEND_USE_UV=false` to use the current Python environment directly.

Verify the backend is up:

```bash
curl http://localhost:6840/v1.0/status
```

Expected response:

```json
{ "ok": true, "can_access_frontend": true }
```

### Step 4 — Start the frontend

> **If `npm install` has already been run for this checkout, skip directly to `npm start`.** The `node_modules/` directory under `m8flow-frontend/` is the signal — if it exists and is recent, you can resume from `npm start`.

```bash
cd m8flow-frontend
npm install   # skip if node_modules/ is already populated for this checkout
npm start
```

Docker bind-mounts the repo `process_models/` directory into the backend and Celery containers, so a locally started backend and a containerized worker read the same process-model files by default.

If the frontend fails with a missing Rollup native package such as `@rollup/rollup-win32-x64-msvc`, reinstall `m8flow-frontend` dependencies on that machine with `npm install`.

### Step 5 — Run a Celery worker

**Linux / macOS / WSL**

```bash
./m8flow-backend/bin/run_m8flow_celery_worker.sh
```

**Windows (no POSIX shell available)**

Run the Celery worker via Docker instead. Since the Celery worker shares code with `m8flow-backend`, make sure the `m8flow-backend` container is **stopped** (you are running the backend locally) before building the worker container:

```bash
docker compose -f docker/m8flow-docker-compose.yml up -d --build m8flow-celery-worker
```

---

## Access the Application with Multitenant mode OFF


Although m8flow is designed as a fully multitenant system, you can configure it to present as a single-tenant UI by setting the environment variable `MULTI_TENANT_ON=false`. 

With this setting, open `http://localhost:6841/` in your browser. You will be redirected directly to the Keycloak login page.

<div align="center">
    <img src="./images/access-m8flow-1.png" />
</div>

<div align="center">
    <img src="./images/access-m8flow-2.png" />
</div>

Default test users (password = username):

| Username | Role |
|----------|------|
| `admin` | Administrator |
| `editor` | Create and edit process models |
| `viewer` | Read-only access |
| `integrator` | Service task / connector access |
| `reviewer` | Review and approve tasks |
| `submitter` | Submit work |

## Sample Templates

m8flow includes sample workflow templates that can help teams get started quickly with common approval, notification, escalation, and integration scenarios.

The sample templates package includes pre-built workflows and guidance for:

- automatically loading templates during startup
- using integration-focused templates such as Salesforce, Slack, SMTP, and PostgreSQL examples

For the full template catalog and setup instructions, refer to [m8flow-backend/sample_templates/README.md](m8flow-backend/sample_templates/README.md).

## Integration Services

m8flow includes supporting services for connector execution and event-driven workflow processing. These components can be run alongside the core platform depending on your deployment needs.

For service-specific setup, configuration, and usage details, refer to:

- [m8flow-connector-proxy/README.md](m8flow-connector-proxy/README.md) for connector proxy support such as SMTP, Slack, HTTP, and related integrations
- [m8flow-nats-consumer/README.md](m8flow-nats-consumer/README.md) for NATS-based event consumption and event-driven workflow execution

---

## Troubleshooting

Common issues encountered when running m8flow locally and how to resolve them.

### `jq: command not found` when running `bin/fetch-upstream.sh`

`fetch-upstream.sh` uses `jq` to parse [`upstream.sources.json`](../upstream.sources.json). Install it:

- **macOS:** `brew install jq`
- **Ubuntu / WSL:** `sudo apt-get install -y jq`
- **Windows:** `winget install --id jqlang.jq -e`

### Backend startup fails with "Failed building wheel" or "missing package metadata"

This typically happens on a **clean Ubuntu/WSL environment** where Python build tooling and headers are missing. Install the build prerequisites and retry:

```bash
sudo apt-get update
sudo apt-get install -y build-essential python3-dev python3-venv
```

Then re-run the backend launcher. If the error persists, clear the local virtualenv and let `uv` rebuild it:

```bash
rm -rf spiffworkflow-backend/.venv
./m8flow-backend/bin/run_m8flow_backend.sh 6840 --reload
```

### Backend startup fails on tenant migration with `UPDATE "refresh_token" SET m8f_tenant_id = ...`

This error appears when an older Keycloak/database state coexists with a newer tenant migration. The migration tries to renumber `m8f_tenant_id` on a `refresh_token` row whose `old_tenant_id` no longer exists in the new schema.

Workarounds, in order of preference:

1. **Fresh local data** (development only — destroys local state):

   ```bash
   docker compose -f docker/m8flow-docker-compose.yml down -v
   docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build m8flow-db keycloak-db keycloak keycloak-proxy redis minio minio-mc-init
   ```

   Then restart the backend so migrations run against an empty database.

2. **Skip M8Flow migrations on next start** (temporary, for diagnostics only):

   ```bash
   M8FLOW_BACKEND_UPGRADE_DB=false ./m8flow-backend/bin/run_m8flow_backend.sh 6840 --reload
   ```

3. **Inspect the offending row** before re-running migrations:

   ```bash
   docker compose -f docker/m8flow-docker-compose.yml exec m8flow-db \
     psql -U spiffworkflow_backend spiffworkflow_backend_local_development \
     -c 'SELECT id, m8f_tenant_id FROM refresh_token;'
   ```

   Reach out on the project tracker with the row contents if you need a non-destructive fix.

### Frontend fails with missing `@rollup/rollup-win32-x64-msvc` (or another Rollup native package)

npm's optional-dependency resolution sometimes skips the platform-specific Rollup binary. Reinstall from a clean `node_modules`:

```bash
cd m8flow-frontend
rm -rf node_modules package-lock.json
npm install
npm start
```

### Port already in use (6840 / 6841 / 6842 / 6843 / 6849)

A leftover Docker container or another local process is bound to one of m8flow's ports. Check the [Default host ports](../README.md#default-host-ports) table in the main README to identify the service, then either stop the conflicting container (`docker compose -f docker/m8flow-docker-compose.yml stop m8flow-backend`) or change the port in `.env` (see [Port conflicts](../README.md#3-port-conflicts-read-this-first)).

### `spiffworkflow-backend` directory not found

You skipped [Step 1 — Fetch upstream SpiffWorkflow source](#step-1--fetch-upstream-spiffworkflow-source-required). Run `./bin/fetch-upstream.sh` (Linux/macOS) or `.\bin\fetch-upstream.ps1` (Windows) and retry.

### "Global admin sign in" fails with *"Client not found"* on `realms/master`

The master realm has no `m8flow-backend` client because the `keycloak-master-admin-init` service was never run. This service is **init-profile** and provisions both the master-realm client and the `super-admin` user.

```bash
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d keycloak-master-admin-init
```

It exits when done (`restart: "no"`). Verify it succeeded:

```bash
docker compose -f docker/m8flow-docker-compose.yml logs keycloak-master-admin-init
```

Then retry "Global admin sign in" in a **fresh private window** (your previous tab is holding a stale auth code from the failed attempt).

### Backend logs `WinError 10061` / `Connection refused` to `localhost:6844`

`m8flow-connector-proxy` is not running. The backend uses it to dispatch connector service-task commands (SMTP, Slack, HTTP). Start it:

```bash
docker compose -f docker/m8flow-docker-compose.yml up -d --build m8flow-connector-proxy
```

If you don't need connector tasks for what you're testing, you can ignore the warning — it's not fatal to startup.
