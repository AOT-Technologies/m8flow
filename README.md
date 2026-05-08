# m8flow — Python-based workflow engine
<div align="center">
    <img src="./docs/images/m8flow_logo.png" alt-text="m8flow"/>
</div>

**m8flow** is an open-source workflow engine implemented in pure Python.
It is built on the proven foundation of SpiffWorkflow, with a vision shaped by **8 guiding principles** for flow orchestration:

**Merge flows effectively** – streamline complex workflows
**Make apps faster** – speed up development and deployment
**Manage processes better** – bring structure and clarity to execution
**Minimize errors** – reduce mistakes through automation
**Maximize efficiency** – get more done with fewer resources
**Model workflows visually** – design with simplicity and clarity
**Modernize systems** – upgrade legacy processes seamlessly
**Mobilize innovation** – empower teams to build and experiment quickly

---

## Why m8flow?

**Future-proof alternative** →  A modern, Python-based workflow engine that can serve as a strong option alongside platforms like Camunda 7

**Enterprise-grade integrations** → tight alignment with **formsflow.ai**, **caseflow**, and the **SLED360** automation suite

**Open and extensible** → open source by default, extensible for enterprise-grade use cases

**Principles-first branding** → "m8" = 8 principles for flow, consistent with the product family (caseflow, formsflow.ai)

---

## Features

**BPMN 2.0**: pools, lanes, multi-instance tasks, sub-processes, timers, signals, messages, boundary events, loops
**DMN**: baseline implementation integrated with the Python execution engine
**Forms support**: extract form definitions (Camunda XML extensions → JSON) for CLI or web UI generation
**Python-native workflows**: run workflows via Python code or JSON structures
**Integration-ready**: designed to plug into formsflow, caseflow, decision engines, and enterprise observability tools

_A complete list of the latest features is available in our [release notes](https://github.com/AOT-Technologies/m8flow/releases)._

---

## Repository Structure

```
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

# ── Gitignored — fetched via bin/fetch-upstream.sh / bin/fetch-upstream.ps1 ─
# spiffworkflow-backend/          Upstream LGPL-2.1 workflow engine
# spiffworkflow-frontend/         Upstream LGPL-2.1 BPMN modeler UI
# spiff-arena-common/             Upstream LGPL-2.1 shared utilities
```

> **Why are those directories missing?**
> `spiffworkflow-backend`, `spiffworkflow-frontend`, and `spiff-arena-common` come from [AOT-Technologies/m8flow-core](https://github.com/AOT-Technologies/m8flow-core) (LGPL-2.1). They are not stored here to keep m8flow's Apache 2.0 licence boundary clean. Run `./bin/fetch-upstream.sh` or `.\bin\fetch-upstream.ps1` once after cloning to populate them. See the [License note](#license-note) for details.

---

## Pre-requisites

Ensure the following tools are installed:

- Git
- Docker and Docker Compose
- Python 3.12.1 and [uv](https://docs.astral.sh/uv/) _(for local backend development only)_
- Node.js 20.19+ or 22.12+ and npm _(for local frontend development only)_

---

## Quick Start Guide

Getting started with m8flow is simple! Follow the steps below to set up your local environment and launch the platform.

### 1. Clone the Repository

First, clone the repository from GitHub and navigate into the project directory:

```bash
git clone https://github.com/AOT-Technologies/m8flow.git
cd m8flow
```

### 2. Set Up Your Environment

Copy the provided environment template and customize it for your setup:

```bash
cp sample.env .env
```

You can find comprehensive environment variable explanations in the [docs/env-reference.md](docs/env-reference.md) file.

---

### 3. Start m8flow with Docker

To bring up all required services (PostgreSQL, Keycloak, MinIO, Redis, NATS, and initialization steps), run:

```bash
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build
```

> **Note:** Run the above command only the first time to perform initialization. For future starts, skip the init profile:

```bash
docker compose -f docker/m8flow-docker-compose.yml up -d --build
```

Once started, open [http://localhost:7001/](http://localhost:7001/) in your browser to access m8flow.

---

## Signing In — Application Usage

1. **Tenant Selection:**  
   When you visit the application, you'll be prompted to select or enter your tenant slug (e.g., `m8flow` which is installed by default).

   <div align="center">
       <img src="./docs/images/access-m8flow-tenant-selection.png" />
   </div>

2. **Log In:**  
   After choosing your tenant, you'll be redirected to the login page.

   <div align="center">
       <img src="./docs/images/access-m8flow-1.png" />
   </div>

   <div align="center">
       <img src="./docs/images/access-m8flow-2.png" />
   </div>

3. **Try the Default Test Users:**  
   Each tenant comes with a set of default users for you to explore the platform. The password for each is the same as the username.

   | Username     | Role                                  |
   |--------------|---------------------------------------|
   | `admin`      | Tenant administrator                  |
   | `editor`     | Create and edit process models        |
   | `viewer`     | Read-only access                      |
   | `integrator` | Service task / connector access       |
   | `reviewer`   | Review and approve tasks              |

You’re all set! Continue with [Tenant creation](#tenant-creation) to add your own tenants or explore the rich features of m8flow.

---

## Tenant creation

1. **Open the Application:**  
   Go to [http://localhost:7001/](http://localhost:7001/) in your web browser.

2. **Sign in as Global Admin:**  
   Click on **"Global admin sign in"**.  
   <div align="center">
      <img src="./docs/images/access-m8flow-tenant-selection.png" alt="Tenant Selection Screen"/>
   </div>

   Log in using the following credentials:
   ```
   Username: super-admin
   Password: super-admin
   ```

3. **Add a Tenant:**  
   After signing in, click the **"Add tenant"** button to create a new tenant.

    <div align="center">
        <img src="./docs/images/tenant-creation.png" alt="Tenant Creation Screen"/>
    </div>

---

## Docker Compose services

The Keycloak image is built with the **m8flow realm-info-mapper** provider, so tokens include `m8flow_tenant_id` and `m8flow_tenant_name`. No separate build of the keycloak-extensions JAR is required. Realm import can be done manually in the Keycloak Admin Console (see Keycloak Setup below) or by running `./m8flow-backend/keycloak/start_keycloak.sh` once after Keycloak is up; the script imports the `m8flow` realm only (expects Keycloak on ports 7002 and 7009, e.g. when using Docker Compose).

| Service | Description | Port |
|---------|-------------|------|
| `m8flow-db` | PostgreSQL — m8flow application database | 1111 |
| `keycloak-db` | PostgreSQL — Keycloak database | — |
| `keycloak` | Keycloak identity provider (with m8flow realm mapper) | 7002, 7009 |
| `keycloak-proxy` | Nginx proxy in front of Keycloak | 7002 |
| `redis` | Redis — Celery broker and cache | 6379 |
| `nats` | NATS messaging server _(optional profile)_ | 4222 |
| `minio` | MinIO object storage (process models, templates) | 9000, 9001 |
| `m8flow-backend` | SpiffWorkflow backend + m8flow extensions | 7000 |
| `m8flow-frontend` | SpiffWorkflow frontend + m8flow extensions | 7001 |
| `m8flow-connector-proxy` | m8flow connector proxy (SMTP, Slack, HTTP, etc.) | 8004 |
| `m8flow-celery-worker` | Celery background task worker | — |
| `m8flow-celery-flower` | Celery monitoring UI | 5555 |
| `m8flow-nats-consumer` | NATS event consumer | — |

**Init-only services** (run once via `--profile init`):

| Service | Purpose |
|---------|---------|
| `fetch-upstream` | Fetches upstream spiff-arena code into the working tree |
| `keycloak-master-admin-init` | Sets up Keycloak master realm admin |
| `minio-mc-init` | Creates MinIO buckets (`m8flow-process-models`, `m8flow-templates`) |
| `process-models-sync` | Syncs process models into MinIO |
| `templates-sync` | Syncs templates into MinIO |

### Stop and clean up

```bash
# Stop containers (preserves volumes)
docker compose -f docker/m8flow-docker-compose.yml down

# Stop and delete all data volumes
docker compose -f docker/m8flow-docker-compose.yml down -v
```

---

## Running Locally (without Docker for backend/frontend)

Use this mode for active development of m8flow extensions.

### 1. Start infrastructure services

Start only the infrastructure (database, Keycloak, MinIO, Redis) as containers:

```bash
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build m8flow-db keycloak-db keycloak keycloak-proxy redis minio minio-mc-init
```

### 2. Start the backend

bash
```
bin/fetch-upstream.sh
./m8flow-backend/bin/run_m8flow_backend.sh 7000 --reload
```

powershell
```
bin/fetch-upstream.ps1
.\m8flow-backend\bin\run_m8flow_backend.ps1 7000
```
Verify the backend

```bash
curl http://localhost:7000/v1.0/status
```
Expected response:
```json
{ "ok": true, "can_access_frontend": true }
```
When `uv` is available locally, the backend launcher syncs backend dependencies automatically before starting and runs the backend through `uv`. Set `M8FLOW_BACKEND_SYNC_DEPS=false` to skip sync, or `M8FLOW_BACKEND_USE_UV=false` to use the current Python environment directly.

### 3. Start the frontend:

Install frontend dependencies first if you have not already done so for this checkout and then start the frontend:

```
cd m8flow-frontend
npm install
npm start
```

This flow expects the Docker dependencies to be running, but not the Docker `m8flow-backend` or `m8flow-frontend` services on the same ports. If those containers are still up, stop them before launching the local dev servers.

Docker bind-mounts the repo `process_models/` directory into the backend and Celery containers, so a locally started backend and a containerized worker read the same process-model files by default.

If the frontend fails with a missing Rollup native package such as `@rollup/rollup-win32-x64-msvc`, reinstall `m8flow-frontend` dependencies on that machine with `npm install`.

> **macOS note:** Port 7000 may be claimed by AirPlay Receiver. Disable it in
> System Settings → General → AirDrop & Handoff → AirPlay Receiver.


### 4. Running a Celery worker

bash
```
./m8flow-backend/bin/run_m8flow_celery_worker.sh
```

If you’re on Windows and don’t have access to a shell (`sh`), you can start the Celery worker with Docker instead. Since the Celery worker relies on `m8flow-backend`, make sure to stop the `m8flow-backend` container if you plan to run the backend locally as described in [Start backend](#2-start-the-backend) above, after building the `m8flow-celery-worker` container.

```
docker compose -f docker/m8flow-docker-compose.yml up -d --build  m8flow-backend m8flow-celery-worker
```

---

## Access the Application with Multitenant mode OFF

Open `http://localhost:7001/` in your browser. You will be redirected to Keycloak login.

<div align="center">
    <img src="./docs/images/access-m8flow-1.png" />
</div>

<div align="center">
    <img src="./docs/images/access-m8flow-2.png" />
</div>

Default test users (password = username):

| Username | Role |
|----------|------|
| `admin` | Administrator |
| `editor` | Create and edit process models |
| `viewer` | Read-only access |
| `integrator` | Service task / connector access |
| `reviewer` | Review and approve tasks |

---

## Sample Templates

m8flow includes sample workflow templates that can help teams get started quickly with common approval, notification, escalation, and integration scenarios.

The sample templates package includes pre-built workflows and guidance for:

- automatically loading templates during startup
- using integration-focused templates such as Salesforce, Slack, SMTP, and PostgreSQL examples

For the full template catalog and setup instructions, refer to [m8flow-backend/sample_templates/README.md](m8flow-backend/sample_templates/README.md).

---

## Integration Services

m8flow includes supporting services for connector execution and event-driven workflow processing. These components can be run alongside the core platform depending on your deployment needs.

For service-specific setup, configuration, and usage details, refer to:

- [m8flow-connector-proxy/README.md](m8flow-connector-proxy/README.md) for connector proxy support such as SMTP, Slack, HTTP, and related integrations
- [m8flow-nats-consumer/README.md](m8flow-nats-consumer/README.md) for NATS-based event consumption and event-driven workflow execution

---

## Production Deployment

See [docker/DEPLOYMENT.md](docker/DEPLOYMENT.md) for production compose and hardening guidance.

### Production MinIO

A dedicated MinIO compose file with pinned image, restart policy, and resource limits:

```bash
# MinIO only
docker compose -f docker/minio.production.docker-compose.yml up -d

# MinIO with the full stack
docker compose -f docker/m8flow-docker-compose.yml \
               -f docker/minio.production.docker-compose.yml up -d

# With bucket init
docker compose --profile init \
               -f docker/m8flow-docker-compose.yml \
               -f docker/minio.production.docker-compose.yml up -d
```

Set `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` in `.env` (no defaults in the production file).

---

## Contribute

We welcome contributions from the community!

- Submit PRs with passing tests and clear references to issues

---

## License note

m8flow is released under the **Apache License 2.0**. See the [LICENSE](LICENSE) file for the full text.

The upstream [AOT-Technologies/m8flow-core](https://github.com/AOT-Technologies/m8flow-core) code (LGPL-2.1) is **not stored in this repository**. It is fetched on demand via `bin/fetch-upstream.sh` or `bin/fetch-upstream.ps1` and gitignored so that it never enters the m8flow commit history. This keeps the licence boundaries cleanly separated while still allowing the app to run against the upstream SpiffWorkflow engine.
