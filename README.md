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

## Prerequisites (Docker setup)

Install the following tools:

- **Git** — [Downloads](https://git-scm.com/downloads)
- **Docker Desktop** (includes Docker Compose v2) — [Product page](https://www.docker.com/products/docker-desktop/) — install guides: [Windows](https://docs.docker.com/desktop/install/windows-install/), [macOS](https://docs.docker.com/desktop/install/mac-install/)

### Default host ports

By default, the stack publishes **6840–6852** on your machine (configured in [sample.env](sample.env)).

| Port(s) | Service |
|---------|---------|
| 6840 | `m8flow-backend` (API) |
| 6841 | `m8flow-frontend` (UI) |
| 6842 | `keycloak-proxy` (Keycloak URL for browsers) |
| 6843 | `m8flow-db` (PostgreSQL) |
| 6844 | `m8flow-connector-proxy` |
| 6846 / 6847 | `minio` (API / console) |
| 6848 | `redis` |
| 6849 | `keycloak` management/health port on host |
| 6850 | `m8flow-celery-flower` |
| 6845 / 6851 / 6852 | NATS client / monitoring / UI (optional; see [docker/m8flow-nats-docker-compose.yml](docker/m8flow-nats-docker-compose.yml)) |

Environment variable reference: [docs/env-reference.md](docs/env-reference.md).

---

## Quick start (Docker)

### 1. Clone the repository

```bash
git clone https://github.com/AOT-Technologies/m8flow.git
cd m8flow
```

### 2. Create your `.env`

Copy [sample.env](sample.env) to `.env` (repo root). Use the command for your OS/shell:

**Windows (Command Prompt)**

```bat
copy sample.env .env
```

**Windows (PowerShell)**

```powershell
Copy-Item sample.env .env
```

**macOS / Linux**

```bash
cp sample.env .env
```

### 3. Port conflicts (read this first)

- **Detect a busy port** (example: backend **6840**):
  - macOS/Linux: `lsof -i :6840` (or `sudo lsof -nP -iTCP:6840 -sTCP:LISTEN`)
  - Windows PowerShell: `Get-NetTCPConnection -LocalPort 6840`
  - Windows CMD: `netstat -ano | findstr :6840`
- **Change a port**: edit `.env` (for example `M8FLOW_BACKEND_PORT=16840`) and re-run docker compose.
- **See what docker published** (after `up`):
  - `docker compose -f docker/m8flow-docker-compose.yml port m8flow-backend 6840`

### 4. Start m8flow

First-time start (includes one-time init jobs):

```bash
docker compose --profile init -f docker/m8flow-docker-compose.yml up -d --build
```

> **Note:** Run the above command only the first time to perform initialization. For future starts, skip the init profile:

```bash
docker compose -f docker/m8flow-docker-compose.yml up -d --build
```

### Once started, open [http://localhost:6841/](http://localhost:6841/) in your browser to access m8flow.
---

## Signing In — Application Usage

1. **Tenant Selection:**  
   When you visit the application, you'll be prompted to select or enter your tenant slug. By default, the tenant `m8flow` will be available for you to use.

   <div align="center">
       <img src="./docs/images/access-m8flow-tenant-selection.png" />
   </div>

2. **Log In:**  
   After choosing your tenant, you'll be redirected to the login page.

   <div align="center">
       <img src="./docs/images/access-m8flow-1.png" />
   </div>


<a id="try-the-default-test-users"></a>
3. **Try the Default Test Users:**  
   Each tenant (including tenants you add later) is provisioned with these default test users.

   | Username     | Role                                  |
   |--------------|---------------------------------------|
   | `admin`      | Tenant administrator                  |
   | `editor`     | Create and edit process models        |
   | `viewer`     | Read-only access                      |
   | `integrator` | Service task / connector access       |
   | `reviewer`   | Review and approve tasks              |
   | `submitter`  | Submit work                           |

   **Password:** the initial password for each user is the **same as the username** (for example `admin` / `admin`). Passwords are imported as **temporary** in Keycloak, so users are prompted for a **password change on first login**.


You’re all set! Continue with [How to use m8flow](#how-to-use-m8flow) to create your first process group, or go to [Tenant creation](#tenant-creation) to add your own tenants.

---

## How to use m8flow

After signing in, follow the [How to use m8flow](docs/how-to-use.md) guide to create your first process group and start organizing process models.

---

## Tenant creation

1. **Open the Application:**  
   Go to [http://localhost:6841/](http://localhost:6841/) in your web browser.

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

### Once your tenant is created, it will automatically include the set of default test users described above in [Try the Default Test Users](#try-the-default-test-users).
---

## Docker Compose services

The Keycloak image is built with the **m8flow realm-info-mapper** provider, so tokens include `m8flow_tenant_id` and `m8flow_tenant_name`. No separate build of the keycloak-extensions JAR is required.

| Service | Description | Host port (default) |
|---------|-------------|----------------------|
| `m8flow-db` | PostgreSQL — m8flow application database | 6843 |
| `keycloak-db` | PostgreSQL — Keycloak database | — |
| `keycloak` | Keycloak identity provider (with m8flow realm mapper) | 6849 (mgmt/health) |
| `keycloak-proxy` | Nginx proxy in front of Keycloak | 6842 |
| `redis` | Redis — Celery broker and cache | 6848 |
| `minio` | MinIO object storage (process models, templates) | 6846, 6847 |
| `m8flow-backend` | SpiffWorkflow backend + m8flow extensions | 6840 |
| `m8flow-frontend` | SpiffWorkflow frontend + m8flow extensions | 6841 |
| `m8flow-connector-proxy` | m8flow connector proxy (SMTP, Slack, HTTP, etc.) | 6844 |
| `m8flow-celery-worker` | Celery background task worker | — |
| `m8flow-celery-flower` | Celery monitoring UI | 6850 |
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
## Additional Documentation & Developer Resources

For details on active development of backend/frontend workflows without docker,  and other development topics, refer to [docs/README.md](docs/README.md). More guides and references are available in the `docs/` folder as the documentation expands.

---

## Contribute

We welcome contributions from the community!

- Submit PRs with passing tests and clear references to issues

---

## License note

m8flow is released under the **Apache License 2.0**. See the [LICENSE](LICENSE) file for the full text.

The upstream [AOT-Technologies/m8flow-core](https://github.com/AOT-Technologies/m8flow-core) code (LGPL-2.1) is **not stored in this repository**. It is fetched on demand via `bin/fetch-upstream.sh` or `bin/fetch-upstream.ps1` and gitignored so that it never enters the m8flow commit history. This keeps the licence boundaries cleanly separated while still allowing the app to run against the upstream SpiffWorkflow engine.
