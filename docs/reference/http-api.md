# HTTP API

The backend serves versioned APIs on port 6840. This page covers the prefixes,
authentication, tenant selection, errors, and the endpoints you use most.

## Prefixes and the OpenAPI spec

| Prefix | Defined in | Contents |
|---|---|---|
| `/v1.0/m8flow/` | `m8flow-backend/src/m8flow_backend/api-v1.yml` (OpenAPI 3) | V1 contract for catalog, process instances, Task Review, templates, tenants, invitations, connectors, API keys, NATS, and MCP tools |
| `/v2.0/m8flow/` | `m8flow-backend/src/m8flow_backend/api-v2.yml` (OpenAPI 3) | V2 contract for the same API areas, independently versioned from V1 |
| `/v{version}/` | `m8flow-backend/src/m8flow_backend/routes/v1.py` | Sign-in, health, permission checks, tasks, instance starts, and secrets |

Currently, `{version}` is `1.0` or `2.0`. V1 remains the default for existing
clients. V2 currently uses the same handlers and request/response contract as
V1; endpoint-specific behavior or schemas will diverge only when that
endpoint's contract changes. See the [versioning policy](versioning.md) for
the compatibility guarantee.

Connexion validates requests against the OpenAPI spec for the requested version. The interactive API reference
is at `http://localhost:6840/v1.0/m8flow/ui` for V1 or
`http://localhost:6840/v2.0/m8flow/ui` for V2. The raw OpenAPI document is
available at the matching `/openapi.json` path.

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
| `GET /v1.0/status` | `{"healthy": true, "ok": true, "status": "ok", "API version": "1.0"}` when the backend is up; `/v2.0/status` returns the same health fields with `"API version": "2.0"` |

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
| `POST /v1.0/process-instances` | Start a process instance by model identifier in the request body |
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

## Start a process instance

Send a JSON object with `process_model_identifier`, such as
`billing/invoice-paid`, to `POST /v1.0/process-instances`. The Designer start
endpoint takes the model identifier from its path.

For a collaboration, send `bpmn_process_id` to select an executable participant
with a none start event. A BPMN participant's `processRef` must reference a
process in the same document. Use an unprefixed process ID or a prefix bound to
the document's `targetNamespace`. A black-box pool can omit the reference.

The optional `collaboration_correlation_key` is case-sensitive and preserves
leading and trailing whitespace. The core generates a key when omitted.
Single-process starts take only the model identifier.

The thin endpoint returns HTTP 201 with `id` and `status`. Collaboration
instances also include `collaboration_correlation_key` in the response.

| HTTP status | Error code | Cause |
|---|---|---|
| 400 | `validation_error` | The request body is invalid JSON, is not an object, or lacks a nonblank string `process_model_identifier` |
| 400 | `validation_error` | Invalid option value or collaboration options supplied for a single-process model |
| 400 | `collaboration_participant_required` | No participant was selected |
| 404 | `collaboration_participant_not_found` | The selected process is outside the executable participants |
| 409 | `collaboration_participant_not_startable` | The participant starts through a modeled event |
| 409 | `collaboration_core_upgrade_required` | The installed core version lacks collaboration support |

## Related pages

- [Trigger processes from external systems](../how-to/trigger-processes-with-api-keys.md)
- [About multi-tenancy and access control](../explanation/multi-tenancy-and-access.md)


## External BPMN message delivery

Call POST /v1.0/m8flow/messages/correlate with an m8flow bearer token and a
concrete active tenant. The caller needs the tenant's message.correlate
permission. The tenant-admin role grants it.

```json
{
  "messageName": "Payment received",
  "deliveryId": "payment-17-west",
  "payload": {"payment": {"caseNumber": 17, "region": "west"}}
}
```

Message names match the BPMN message declaration exactly. The model's
retrieval paths determine which payload fields participate in correlation.
Optional processDefinitionId and processInstanceId fields narrow the wait to
a stored definition or instance within the active tenant.

A 200 response includes deliveryId, processInstanceId, taskGuid, deliveredAt,
and outcome. An outcome of workflow_error means the message was committed
and a later workflow step failed. Use the process instance's retry operation
to recover from that failure.

Missing or invalid request fields return 400. A 404 means no eligible catch
matches, and the sender can retry with the same delivery ID. Multiple matches
or changing the inputs of a committed delivery ID return 409. Identical
retries return the original receipt.
