# Repository layout

This page maps the top-level folders of the m8flow repository to the
components they build.

## Top-level folders

The repository contains the following folders:

| Folder | Contents |
|---|---|
| `m8flow-backend/` | The HTTP host: API routes, host modules, migrations, Keycloak assets, and tests |
| `m8flow-designer/` | The web UI: Vite, React, and TypeScript |
| `m8flow-bpmn/` | The BPMN and DMN modeler package that the designer embeds. Based on bpmn-js and dmn-js. |
| `m8flow-node-wire-proxy/` | The default connector proxy for service tasks |
| `m8flow-connector-proxy/` | An alternative connector proxy, behind the `legacy-connector-proxy` Compose profile |
| `m8flow-nats-consumer/` | The NATS trigger consumer and the notification worker |
| `m8flow-mcp/` | The Model Context Protocol server for AI assistants |
| `m8flow-telemetry/` | Shared OpenTelemetry metrics helpers |
| `keycloak-extensions/` | The Keycloak realm-info-mapper that adds tenant claims to tokens |
| `docker/` | Compose files, Dockerfiles, Keycloak bootstrap scripts, and the observability stack |
| `bin/` | Developer helper scripts |
| `.github/` | CI workflows and pull request templates |

The repository root also holds `sample.env`, the glossary in `CONTEXT.md`, the
contributor rules in `AGENTS.md`, `CHANGELOG.md`, and `LICENSE`.

## Backend

The backend source is in `m8flow-backend/src/m8flow_backend/`:

| Path | Contents |
|---|---|
| `app.py` | Builds the ASGI app: middleware, error handlers, routes, and the OpenAPI mount |
| `api.yml` | OpenAPI spec for every `/v1.0/m8flow/` endpoint |
| `workflow/`, `catalog/`, `human_task/`, `scheduler/`, `identity/`, `auth/`, `authorization/`, `secrets/` | The eight host modules |
| `routes/` | Route handlers. `v1.py` registers the `/v1.0/` routes. |
| `integrations/auth/` | The auth provider seam and the Keycloak provider |
| `connectors/` | Connector catalog, profiles, and run-time parameter filling |
| `services/` | Supporting services: templates, invitations, NATS, email, and tenants |
| `models/` | SQLAlchemy models for host-owned tables |
| `config/permissions/m8flow.yml` | The permission policy |
| `observability/` | Health checks, JSON logging, request IDs, and SQL timing |
| `startup/` | Environment mapping, logging, error handlers, and bootstrap |

Other backend folders:

| Path | Contents |
|---|---|
| `m8flow-backend/bin/` | Scripts to run the backend, the Celery worker, and Alembic |
| `m8flow-backend/migrations/` | Alembic migrations for host-owned tables |
| `m8flow-backend/keycloak/` | Realm template and the sign-in page theme |
| `m8flow-backend/sample_templates/` | Templates loaded at startup |
| `m8flow-backend/vendor/` | The pinned `m8flow-bpmn-core` engine wheel |
| `m8flow-backend/tests/` | Unit tests, plus integration tests in `tests/integration/` |

## Designer

The designer source is in `m8flow-designer/src/`:

| Path | Contents |
|---|---|
| `app/` | The router and the route list |
| `pages/` | One folder per page, for example `processes/` and `task-review/` |
| `components/` | Shared components. `components/library/` is the component library shown in Storybook. |
| `lib/` | API clients and helpers, one module per backend area |
| `locales/` | Translations, one folder per language |

Playwright browser tests are in `m8flow-designer/e2e/`.

## Data folders

m8flow writes runtime files to the following folders at the repository root.
They aren't part of the source:

| Path | Contents |
|---|---|
| `data/process_models/` | The process-model catalog, one subfolder per tenant. Compose bind-mounts it into the backend and workers. |
| `data/templates/` | Template storage when you run the backend from source. Compose uses a named volume instead. |

## Related pages

- [About the m8flow architecture](../explanation/architecture.md)
- [Develop and test m8flow](../how-to/develop-and-test.md)
