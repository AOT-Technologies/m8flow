# HTTP API

The backend serves its API under two prefixes on port 6840. This page covers
the prefixes, authentication, tenant selection, errors, and the endpoints you
use most.

## Prefixes and the OpenAPI spec

| Prefix | Defined in | Contents |
|---|---|---|
| `/v1.0/m8flow/` | `m8flow-backend/src/m8flow_backend/api.yml` (OpenAPI 3) | Catalog, process instances, Task Review, templates, tenants, invitations, connectors, API keys, NATS, and MCP tools |
| `/v1.0/` | `m8flow-backend/src/m8flow_backend/routes/v1.py` | Sign-in, health, permission checks, tasks, and secrets |

Connexion validates requests against `api.yml`. The interactive API reference
is at `http://localhost:6840/v1.0/m8flow/ui`, and the raw spec is at
`http://localhost:6840/v1.0/m8flow/openapi.json`.

## Authentication

Send the access token in one of two ways:

- As an `Authorization: Bearer <token>` header. Use this from scripts and
  other services.
- As the `access_token` cookie. The browser sends it after sign-in.

Replace `<token>` with an access token issued by the shared or master realm.

The trigger endpoint, `POST /v1.0/m8flow/events/m8flow-trigger`, is the
exception. It takes a tenant API key in the `X-M8FLOW-NATS-API-Key` header
instead of a token.

## Tenant selection

Each request works in one tenant. The backend takes the tenant from the
`m8flow_selected_tenant` cookie when it matches the token. Without the cookie,
it uses the token's tenant claim, then the `x-m8flow-tenant-id` header if the
user belongs to that tenant. When none applies, the request fails.

## Errors

Error responses have a JSON body with an error code and a message:

```json
{ "error_code": "permission_denied", "message": "..." }
```

Any response with status 400 or higher rolls back the request's database
changes.

## Sign-in endpoints

The browser uses these endpoints during sign-in. Scripts don't call them.

| Method and path | Purpose |
|---|---|
| `GET /v1.0/login` | Redirects to the Keycloak sign-in page. With `tenant=<alias>&tenant_finalization=1`, finalizes the active tenant. |
| `GET /v1.0/login_return` | Keycloak's redirect target. Exchanges the code for tokens and sets the cookies. |
| `POST /v1.0/refresh` | Refreshes the access token with the `refresh_token` cookie |
| `GET /v1.0/logout` | Clears the m8flow cookies and ends the Keycloak session |
| `GET /v1.0/m8flow/session` | The current session: user, active tenant, and session type |
| `GET /v1.0/m8flow/organization-memberships` | The tenants the user can switch to |

## Health endpoints

These endpoints need no token:

| Method and path | Returns |
|---|---|
| `GET /v1.0/healthy`, `GET /v1.0/ping` | Liveness |
| `GET /v1.0/readyz` | Readiness, for load balancers and deployment checks |
| `GET /v1.0/status` | `{"healthy": true, "ok": true, "status": "ok"}` when the backend is up |

## Permission checks

`POST /v1.0/permissions-check` answers whether the current user may call one
or more endpoints. The designer uses it to decide which actions to show.

The following request asks about two endpoints:

```json
{
  "requests_to_check": {
    "/v1.0/process-instances": ["GET", "POST"],
    "/v1.0/secrets": ["POST"]
  }
}
```

The response is similar to the following:

```json
{
  "results": {
    "/v1.0/process-instances": { "GET": true, "POST": true },
    "/v1.0/secrets": { "POST": false }
  }
}
```

## Common endpoints

The following endpoints cover the main workflow. All of them work in the
active tenant.

| Method and path | Purpose |
|---|---|
| `GET /v1.0/m8flow/process-groups` | List process groups |
| `GET /v1.0/m8flow/process-models` | List process models |
| `POST /v1.0/m8flow/process-models/<model-id>/start` | Start a process instance |
| `GET /v1.0/m8flow/process-instances` | List process instances |
| `GET /v1.0/m8flow/process-instances/<instance-id>` | One process instance |
| `POST /v1.0/m8flow/process-instances/<instance-id>/suspend` | Suspend an instance. `resume` and `terminate` work the same way. |
| `GET /v1.0/m8flow/process-instances/<instance-id>/events` | The instance's events |
| `GET /v1.0/tasks` | Tasks the current user can work |
| `PUT /v1.0/tasks/<task-id>/claim` | Claim a task |
| `POST /v1.0/tasks/<task-id>/complete` | Complete a task with form data |
| `GET /v1.0/secrets` | List secret keys. Values are never returned. |
| `POST /v1.0/m8flow/events/m8flow-trigger` | Start a process from an external system |

Replace the following:

- `<model-id>`: the process model identifier with each `/` replaced by `:`,
  for example `billing:invoice-paid`.
- `<instance-id>`: the numeric process instance ID.
- `<task-id>`: the numeric task ID from `GET /v1.0/tasks`.

For every other endpoint and its request and response schemas, see the
interactive API reference.

## Related pages

- [Trigger processes from external systems](../how-to/trigger-processes-with-api-keys.md)
- [About multi-tenancy and access control](../explanation/multi-tenancy-and-access.md)
