# Inspecting Tenant Connector Secrets Locally

This guide explains how to inspect a connector secret document in the
development-only Vault setup. It is intended for local troubleshooting, not
production operations.

## Prerequisites

Start Vault and the demo bootstrap:

```powershell
docker compose `
  -f docker/m8flow-docker-compose.yml `
  --profile vault `
  --profile vault-demo `
  up -d --build
```

Confirm that the one-shot bootstrap completed:

```powershell
docker compose -f docker/m8flow-docker-compose.yml logs vault-demo
```

The logs should contain `vault-demo: Bootstrap complete`.

## Resolve the Operator Token

The helper scripts need an operator token to query the database and Vault
administration APIs. In local demo mode, the command below reads the
encrypted `root_token` from `/vault/demo/init.json` inside the container and
stores it only in the current PowerShell process:

```powershell
$env:M8FLOW_VAULT_OPERATOR_TOKEN = docker compose `
  -f docker/m8flow-docker-compose.yml `
  --profile vault `
  --profile vault-demo `
  run --rm --no-deps `
  --entrypoint python `
  m8flow-backend `
  -c "import sys; sys.path.insert(0, '/app/docker/vault/demo'); import bootstrap_vault_demo as b; print(b.root_token_from_init(b.load_init_payload()))"
```

The decryption key is supplied to the container through `.env` as
`M8FLOW_VAULT_DEMO_STATE_KEY`, or through the legacy fallback
`M8FLOW_BACKEND_ENCRYPTION_KEY`. The command does not create a new key.

Do not commit, paste, or save the operator token in shell history or CI logs.

## Get Tenant AppRole Credentials

Use the tenant UUID, name, or slug. `-ShowSecretId` is intentionally required
to print the sensitive AppRole secret ID:

```powershell
.\docker\vault\scripts\print-tenant-vault-approle.ps1 `
  -Tenant "<tenant-id>" `
  -ShowSecretId
```

Record the returned `role_id` and `secret_id` only for the immediate local
test. The script creates a fresh tenant AppRole secret ID.

## Exchange AppRole Credentials for a Tenant Token

The role ID and secret ID are not the token used for KV reads. Exchange them
with the AppRole login endpoint:

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8200/v1/auth/approle/login" `
  -ContentType "application/json" `
  -Body (@{
    role_id = "<role-id>"
    secret_id = "<secret-id>"
  } | ConvertTo-Json)

$tenantToken = $login.auth.client_token
```

The returned token is short-lived and is restricted to the selected tenant's
Vault policy. The local Vault instance uses HTTP, so do not use `https` for
this development endpoint.

## Read a Connector Document

Connector sensitive fields are stored together in one KV v2 document. The
path is:

```text
kv/m8flow/tenants/<tenant-id>/secrets/connector-configuration/<connector-configuration-id>
```

For example:

```powershell
curl.exe `
  -H "X-Vault-Token: $tenantToken" `
  "http://127.0.0.1:8200/v1/kv/data/m8flow/tenants/<tenant-id>/secrets/connector-configuration/<connector-configuration-id>"
```

The response is a KV v2 envelope. Sensitive values are under `data.data`,
while version and creation metadata are under `data.metadata`:

```json
{
  "data": {
    "data": {
      "SMTP_PASSWORD": "<secret>",
      "SMTP_USER": "<secret>"
    },
    "metadata": {
      "version": 1,
      "destroyed": false
    }
  }
}
```

The connector configuration's immutable ID, not its editable display metadata,
is used as the Vault document name. Connector identifiers are independently
validated for service-task selection.

## Manual Configuration Variables

Sensitive manual Configuration Variables use a different, value-only document:

```text
kv/m8flow/tenants/<tenant-id>/secrets/configuration-variable/<named-value-id>
```

`<named-value-id>` is the immutable UUID from `m8flow_named_value`. The Vault
document contains only `{"value": "<secret>"}`; names, descriptions, tenant
ownership, and configured state remain in the database catalog. Do not use the
old unscoped UUID path when creating new variables.

## What Happens

1. `vault-demo` initializes or unseals the local Vault and persists its
   development bootstrap state in the `vault-demo-state` volume.
2. M8Flow provisions a separate policy and AppRole for each tenant.
3. The helper obtains an operator credential, resolves the tenant UUID, and
   creates a fresh tenant AppRole secret ID.
4. AppRole login exchanges the role ID and secret ID for a short-lived,
   tenant-scoped client token.
5. Vault authorizes the token only under that tenant's `secrets/` subtree.
6. A connector profile stores all sensitive fields in one document, while
   non-sensitive configuration remains in the database.

The backend uses its broker/control-plane identity to provision tenant
identities. It should not use that identity to read tenant secret values.

## Troubleshooting

- `Could not resolve an operator token`: set
  `M8FLOW_VAULT_OPERATOR_TOKEN`, or rerun the token-recovery command after
  confirming `vault-demo` completed.
- `permission denied` on the KV write: ensure the document path includes the
  tenant UUID and that the backend has been rebuilt after connector storage
  changes.
- `permission denied` on the KV read: exchange the tenant AppRole credentials
  for a tenant token; the broker token is not a tenant secret-read token.
- Missing or unreadable `init.json`: the Vault data and demo-state volumes
  may be out of sync. Follow the reset procedure in
  [Vault local development](./vault-local-development.md).
