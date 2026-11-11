# Vault tenant cleanup

Deleting a tenant removes its Keycloak organization and PostgreSQL tenant row
first. If the database delete fails, the backend preserves Vault data and
returns an error so the data can be repaired and deletion retried.

After a successful database delete, the backend attempts to erase all KV v2
documents under that tenant's secret root using a token issued by that tenant's
AppRole. It does not use the shared broker to delete tenant identities: the
broker intentionally has no cross-tenant delete permission. The API returns
`202` and `vault_cleanup_pending: true` to make the remaining AppRole and policy
cleanup visible.

An operator must then run the controlled cleanup script with the deleted
tenant's stable ID. The operator token is supplied through the environment and
is never written by the script:

```powershell
$env:M8FLOW_VAULT_ADDR = "https://vault.example"
$env:M8FLOW_VAULT_OPERATOR_TOKEN = "<operator-token>"
python docker/vault/scripts/delete_tenant_vault.py <tenant-id>
```

The script deletes data, the tenant AppRole, and its policy only for the
specified tenant ID. Use an operator token whose Vault ACL is scoped to the
configured tenant role/policy prefixes and KV path where possible. The local
Docker Vault root token is for development only.

## Production broker trust boundary

The policy rendered from `policies/m8flow-policy.hcl.tpl` is a **privileged
control-plane broker policy**. It lets the M8Flow service create and update
policies and AppRoles matching the configured tenant prefixes, read those
roles' IDs, and mint their SecretIDs. M8Flow uses these permissions to create
tenant identities dynamically and to obtain short-lived tenant-scoped tokens.

This broker credential is not tenant-scoped. A compromise of any process that
can read it can alter the identity or policy for any tenant and mint credentials
that reach tenant secrets. Tenant AppRole policies limit the resulting data
tokens, but they do not limit the broker itself. Treat `M8FLOW_VAULT_TOKEN` and
the broker AppRole's RoleID/SecretID as production control-plane credentials;
neither is a normal application token. Never use the Vault root token as the
broker credential.

For production deployments:

- Keep the broker credential in the platform secret manager and mount it only
  into trusted M8Flow processes that need Vault access. Do not put it in the
  repository, image, ordinary `.env` files, logs, or support bundles.
- The backend API, Celery worker, notification worker, and NATS consumer need
  the broker to resolve or manage tenant secrets. Keep it away from the
  designer/frontend and monitoring-only services. Compose no longer mounts
  `vault-runtime` into Celery Flower and explicitly clears Vault credential
  variables inherited from the shared `.env` there.
- Use a dedicated AppRole mount, KV mount, and tenant role/policy prefixes for
  M8Flow. Restrict the broker ACL to those prefixes; avoid wildcard grants over
  unrelated Vault roles, policies, or mounts.
- Require TLS verification, restrict network access to Vault, enable Vault
  audit logging, and rotate the broker AppRole SecretID after suspected
  exposure or staff/deployment changes.
- Monitor writes to `sys/policy` and the configured tenant AppRole prefix.
  These are high-impact control-plane actions.

The current design still gives the runtime broker control-plane access because
tenant identities are provisioned dynamically by M8Flow. Removing those
permissions from the runtime would require moving tenant identity creation and
repair into a separately authenticated provisioning service or operator flow;
that architectural change is not part of this repository change.

The `configure-m8flow-vault.*` scripts show a local Compose setup that places a
broker token in `.env`. Treat that as development-only. In production, inject
the broker token with the deployment platform's secret manager (for example,
through `M8FLOW_VAULT_TOKEN_FILE`) and grant access only to the service
containers that need it.
