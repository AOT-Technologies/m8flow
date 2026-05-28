# m8flow Documentation

This folder contains project documentation for setup, architecture, and development workflows.

## Index

- [Repository structure](#repository-structure)
- [Running locally (without Docker for backend/frontend)](#running-locally-without-docker-for-backendfrontend)
- [Access the application with multitenant mode off](#access-the-application-with-multitenant-mode-off)
- [Shared-realm organization group role mapping](shared-realm-organization-group-role-mapping.md)
- [Sample Templates](#sample-templates)
- [Integration Services](#integration-services)

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

## Running Locally (without Docker for backend/frontend)

Use this mode for active development of m8flow extensions.

### 1. Start infrastructure services

Start only the infrastructure (database, Keycloak, MinIO, Redis) as containers:

```bash
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build m8flow-db keycloak-db keycloak keycloak-proxy redis minio minio-mc-init
```

### 2. Start the backend

```bash
bin/fetch-upstream.sh
./m8flow-backend/bin/run_m8flow_backend.sh 6840 --reload
```

```powershell
bin/fetch-upstream.ps1
.\m8flow-backend\bin\run_m8flow_backend.ps1 6840
```

Verify the backend:

```bash
curl http://localhost:6840/v1.0/status
```

Expected response:

```json
{ "ok": true, "can_access_frontend": true }
```

When `uv` is available locally, the backend launcher syncs backend dependencies automatically before starting and runs the backend through `uv`. Set `M8FLOW_BACKEND_SYNC_DEPS=false` to skip sync, or `M8FLOW_BACKEND_USE_UV=false` to use the current Python environment directly.

### 3. Start the frontend

Install frontend dependencies first if you have not already done so for this checkout and then start the frontend:

```bash
cd m8flow-frontend
npm install
npm start
```

This flow expects the Docker dependencies to be running, but not the Docker `m8flow-backend` or `m8flow-frontend` services on the same ports. If those containers are still up, stop them before launching the local dev servers.

Docker bind-mounts the repo `process_models/` directory into the backend and Celery containers, so a locally started backend and a containerized worker read the same process-model files by default.

If the frontend fails with a missing Rollup native package such as `@rollup/rollup-win32-x64-msvc`, reinstall `m8flow-frontend` dependencies on that machine with `npm install`.

### 4. Running a Celery worker

```bash
./m8flow-backend/bin/run_m8flow_celery_worker.sh
```

If you are on Windows and do not have access to a shell (`sh`), you can start the Celery worker with Docker instead. Since the Celery worker relies on `m8flow-backend`, make sure to stop the `m8flow-backend` container if you plan to run the backend locally as described above, after building the `m8flow-celery-worker` container.

```bash
docker compose -f docker/m8flow-docker-compose.yml up -d --build m8flow-backend m8flow-celery-worker
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
