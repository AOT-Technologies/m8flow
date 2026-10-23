# Run the backend and designer from source

Run `m8flow-backend` and `m8flow-designer` on your machine with hot reload,
while Docker runs the infrastructure they depend on. Use this setup when you
change backend or designer code.

## Prerequisites

You need the following tools:

| Tool | Version | Check with |
|---|---|---|
| Git | Any recent version | `git --version` |
| Docker with Compose v2 | Compose v2 | `docker compose version` |
| Python | 3.12 | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | Latest | `uv --version` |
| Node.js and npm | 20.19 or later | `node --version` |

You also need a `.env` file at the repository root. If you don't have one, copy
it from the sample:

```bash
cp sample.env .env
```

If the full Docker stack is running, stop its `m8flow-backend` and
`m8flow-designer` containers first. Otherwise they hold ports 6840 and 6853.

## Start the infrastructure

To start the database, Keycloak, Redis, MinIO, the connector proxy, and the
one-time `init` jobs, run the following command:

```bash
docker compose --env-file .env --profile init \
    -f docker/m8flow-docker-compose.yml up -d --build \
    m8flow-db keycloak-db keycloak keycloak-proxy redis minio \
    minio-mc-init keycloak-master-admin-init m8flow-node-wire-proxy
```

On Windows PowerShell, put the command on one line, because `\` isn't a line
continuation there.

The `keycloak-master-admin-init` job creates the `super-admin` user and the
backend client in the master realm. Without it, the platform admin sign-in
fails with "Client not found".

## Start the backend

To start the backend on port 6840 with reload, run the following command from
the repository root:

```bash
./m8flow-backend/bin/run_m8flow_backend.sh 6840 --reload
```

On Windows, run `.\m8flow-backend\bin\run_m8flow_backend.ps1 6840` instead.

The launcher syncs dependencies with `uv`, runs the database migrations, and
starts the ASGI server. To skip the dependency sync, set
`M8FLOW_BACKEND_SYNC_DEPS=false`. To use the current Python environment
instead of `uv`, set `M8FLOW_BACKEND_USE_UV=false`.

To check that the backend is up, run the following command:

```bash
curl http://localhost:6840/v1.0/status
```

The output is similar to the following:

```json
{ "healthy": true, "ok": true, "status": "ok" }
```

## Start the designer

To start the designer's dev server, run the following commands:

```bash
cd m8flow-designer
npm install
npm run dev
```

The designer runs at `http://localhost:6853/`. Its dev server forwards `/v1.0`
calls to the backend on the same origin, so the browser needs no CORS setup.
Sign-in and sign-out go to the backend URL directly, so the Keycloak redirect
stays on port 6840.

To point the designer at a different backend, set `VITE_BACKEND_BASE_URL`
before you run `npm run dev`.

## Start a Celery worker

Timers and other background jobs need a Celery worker. To start one, run the
following command from the repository root:

```bash
./m8flow-backend/bin/run_m8flow_celery_worker.sh
```

On Windows, run `.\m8flow-backend\bin\run_m8flow_celery_worker.ps1` instead.

To run the worker in Docker instead, start the `m8flow-celery-worker` service.
The local backend and the containerized worker read the same process models,
because Compose bind-mounts `data/process_models` from the repository.

## Troubleshoot

### The backend fails with "Failed building wheel"

A clean Ubuntu or WSL machine lacks the build tools for native Python
packages. To install them, run the following command:

```bash
sudo apt-get install -y build-essential python3-dev python3-venv
```

If the error continues, delete `m8flow-backend/.venv` and start the backend
again, so `uv` rebuilds the environment.

### The designer fails with a missing Rollup package

npm sometimes skips the platform-specific Rollup binary, such as
`@rollup/rollup-win32-x64-msvc`. To fix it, delete
`m8flow-designer/node_modules` and `m8flow-designer/package-lock.json`, then
run `npm install` again.

### The backend logs "Connection refused" on port 6844

`m8flow-node-wire-proxy` isn't running. The backend only needs it for service
tasks, so startup still succeeds. To start it, run the following command:

```bash
docker compose --env-file .env \
    -f docker/m8flow-docker-compose.yml up -d m8flow-node-wire-proxy
```

### A port is already in use

Another container or program holds one of the m8flow ports. Change the port in
`.env`, as described in [Services and ports](../reference/services-and-ports.md).

## Next steps

- [Run the tests and linters](develop-and-test.md).
- [See where the code lives](../reference/repository-layout.md).
