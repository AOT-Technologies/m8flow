# Vault tenant cleanup and identity separation

## Tenant deletion

Deleting a tenant removes its Keycloak organization and PostgreSQL tenant row
first. If the database delete fails, the backend preserves Vault data and
returns an error so the deletion can be repaired and retried.

After the database deletion commits, the backend uses a tenant-scoped token to
delete KV v2 documents under that tenant's secret root. It does not delete the
AppRole or policy. The API reports `vault_cleanup_pending: true`; an operator
must then run `docker/vault/scripts/delete_tenant_vault.py <tenant-id>` with an
operator credential restricted to the tenant role/policy prefixes and KV path.
The local Docker Vault root token is for development only.

## Workload identities

M8Flow uses separate Vault identities for the runtime and the tenant identity
provisioner:

- **Runtime AppRole** is used by the backend, Celery worker, notification
  worker, and NATS consumer. Its policy can read tenant RoleIDs and create,
  use, and destroy one-use SecretIDs. It cannot create or modify policies or
  AppRoles. Tenant-scoped tokens it obtains can access only that tenant's KV
  subtree.
- **Provisioner AppRole** is mounted only into the isolated
  `vault-provisioner` service. Its policy can create/update policies and
  AppRoles under the configured M8Flow tenant prefixes and read their RoleIDs.
  It cannot read KV secret values or mint tenant SecretIDs.
- **Provisioner API token** authenticates backend requests to the provisioner.
  The endpoint accepts only a tenant ID and applies the fixed policy and role
  settings in M8Flow code; callers cannot supply policy text or role settings.

This removes Vault policy/role write credentials from application and worker
processes. The runtime remains a trusted cross-tenant service: because it
serves requests for multiple tenants, it can ask Vault for tenant-scoped
credentials for any tenant ID. The internal API token also authorizes requests
for any tenant ID, so protect it like a high-impact service credential. A
future deployment can narrow this further by authenticating the caller's
active tenant and enforcing that binding at the provisioner boundary.

## Production deployment requirements

The local Compose stack runs `vault-provisioner` only with the `vault-demo`
profile. Production deployments must provide an equivalent isolated service;
operations needing tenant identity reconciliation fail closed if the
provisioner URL or API token is absent.

- Give the provisioner its own AppRole RoleID/SecretID and mount them only in
  that service. Do not mount its credentials into backend, workers, designer,
  or monitoring services.
- Give runtime processes a separate runtime AppRole. Its policy must not grant
  policy or role management capabilities.
- Configure backend/worker processes with `M8FLOW_VAULT_PROVISIONER_URL` and
  `M8FLOW_VAULT_PROVISIONER_API_TOKEN_FILE` (or the direct token setting from a
  platform secret manager). The provisioner reads the same API token from its
  own secret file. Rotate the shared API token on suspected exposure.
- Keep the provisioner on a private network and require TLS with certificate
  verification for traffic that leaves a trusted pod/container network. Set
  `M8FLOW_VAULT_CACERT` when a private CA is used. Do not expose its port to
  browsers or the public internet.
- Use a dedicated AppRole mount, KV mount, and tenant role/policy prefixes.
  Enable Vault audit logging and alert on policy/AppRole writes.
- Never use the Vault root token as either workload credential.

The `configure-m8flow-vault.*` scripts write the provisioner and runtime
policies, but do not create production workloads or distribute their
credentials. The operator must create separate AppRoles with the appropriate
policies and deliver each credential through the deployment platform's secret
manager. The scripts' local `.env` and named-volume setup is development-only.

## Local Compose flow

`docker/m8flow-docker-compose.vault.yml` selects Vault for local runtime
services. The `vault-demo` bootstrap creates the KV/AppRole mounts, both
policies, and two workload identities. It stores runtime credentials in
`vault-runtime` and provisioner credentials in `vault-provisioner`. Only the
backend/worker containers mount `vault-runtime`; only `vault-provisioner`
mounts the provisioner identity. The backend receives only the internal API
token, while the provisioner receives its own Vault credential and the same
API token. The service has no published host port.

Start the demo with:

```powershell
docker compose --env-file .env --profile vault --profile vault-demo `
  -f docker/m8flow-docker-compose.yml `
  -f docker/m8flow-docker-compose.vault.yml up -d --build
```

The Compose setup uses HTTP only on its local Docker network and is not a
production template. See [Local Vault development](../../docs/vault-local-development.md)
for startup, seeding, and reset steps.
