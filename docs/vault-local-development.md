# Vault Local Development

This repository supports two local Vault workflows:

- `vault` profile: a manual single-node development Vault.
- `vault-demo` profile: a development-only bootstrap layer on top of `vault` that initializes, unseals, configures, seeds, and verifies Vault automatically.

Both workflows are local-only. They use a single-node HTTP Vault with no TLS, no HA, no audit device, and no production-grade unseal strategy.

The local dev setup now has two distinct Vault identity layers:

- a shared broker/control-plane AppRole created by `vault-demo` so backend and Celery containers can start in Vault mode and mint tenant-scoped Vault clients in local Docker;
- per-tenant Vault policies and AppRoles created by M8Flow itself when tenants are provisioned, so Vault becomes the tenant-isolation backstop.

## Architecture

- Base Vault service: `vault`
- Demo bootstrap service: `vault-demo`
- Vault image: `hashicorp/vault:1.18.5`
- Vault server config: [docker/vault/config/vault.hcl](../docker/vault/config/vault.hcl)
- Policy template: [docker/vault/policies/m8flow-policy.hcl.tpl](../docker/vault/policies/m8flow-policy.hcl.tpl)
- Tenant AppRole helper scripts:
  [docker/vault/scripts/print-tenant-vault-approle.sh](../docker/vault/scripts/print-tenant-vault-approle.sh)
  and
  [docker/vault/scripts/print-tenant-vault-approle.ps1](../docker/vault/scripts/print-tenant-vault-approle.ps1)
- Demo bootstrap script: [docker/vault/demo/bootstrap_vault_demo.py](../docker/vault/demo/bootstrap_vault_demo.py)
- Demo seed template: [docker/vault/demo/secrets.yml.sample](../docker/vault/demo/secrets.yml.sample)
- Runtime verification script: [docker/vault/demo/verify_backend_vault_demo.py](../docker/vault/demo/verify_backend_vault_demo.py)
- Persistent Vault data volume: `m8flow_vault-data`
- Persistent demo state volume: `m8flow_vault-demo-state`
- Host UI/API URL: `http://127.0.0.1:${M8FLOW_VAULT_PORT:-8200}`
- In-container Vault URL: `http://vault:8200`
- KV v2 mount used by M8Flow: `kv`
- Logical secret path convention: `kv/m8flow/tenants/{tenant_id}/secrets/{secret_name}`

The `vault-demo` profile stores generated local-only files inside the named demo state volume at `/vault/demo`:

- `init.json` (encrypted at rest)
- `m8flow-role-id` (encrypted at rest)
- `m8flow-secret-id` (encrypted at rest)
- `runtime.env`
- `verification.json`

Because those files live in a Docker volume instead of the repository, they are not committed and do not need `.gitignore` entries.

## Per-Tenant Vault Identities

When `M8FLOW_VAULT_ENABLED=true`, M8Flow now provisions Vault-side tenant identities automatically:

- the create-tenant API creates a tenant-scoped ACL policy and AppRole after the Keycloak organization and local tenant row are created;
- the shared-realm bootstrap provisions the default `m8flow` tenant's Vault identity after reconciling the canonical tenant UUID;
- the generated tenant policy is limited to that tenant's secret subtree, following the logical path convention `kv/m8flow/tenants/{tenant_id}/secrets/{secret_name}`;
- repeated startup/bootstrap passes reconcile the role and policy without rotating the existing tenant AppRole `secret_id`.

The configured runtime token or AppRole is now a broker/control-plane identity. M8Flow uses it to create, reconcile, and resolve tenant-specific AppRoles, then performs tenant secret CRUD through tenant-scoped Vault clients derived from those AppRoles. If that broker identity can still read tenant KV data directly, the local setup is misconfigured.

## Resolve One Tenant-Scoped AppRole

Use these helpers when you want to sign in to the local Vault UI with one tenant's AppRole only.

Both scripts:

- accept a tenant `id`, `slug`, or `name`;
- resolve the canonical tenant UUID from `m8flow_tenant`;
- compute the tenant AppRole name using the repo's own provisioning logic;
- mint a fresh tenant AppRole `secret_id`;
- print the `role_id`, a masked `secret_id` by default, the AppRole auth URL, and the tenant secrets URL.
- only print the real `secret_id` when you pass an explicit reveal flag.

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File docker/vault/scripts/print-tenant-vault-approle.ps1 -Tenant Test
```

POSIX shell:

```bash
sh docker/vault/scripts/print-tenant-vault-approle.sh Test
```

If you need the actual `secret_id` for a one-time local AppRole sign-in, opt in explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File docker/vault/scripts/print-tenant-vault-approle.ps1 -Tenant Test -ShowSecretId
```

```bash
sh docker/vault/scripts/print-tenant-vault-approle.sh --show-secret-id Test
```

Use the printed `role_id` and, when explicitly revealed, the `secret_id` to sign in at the printed `approle_auth_url`.

Notes:

- Each run mints a new tenant AppRole `secret_id`. Treat it like a credential.
- The real `secret_id` is hidden by default so it does not land in routine shell output or copied logs by accident.
- When you reveal it with `-ShowSecretId` or `--show-secret-id`, the scripts print a warning to `stderr` before writing the secret to `stdout`.
- If `M8FLOW_VAULT_OPERATOR_TOKEN` or `VAULT_TOKEN` is set in your host shell, the helpers use that operator token.
- Otherwise, in the local `vault-demo` workflow they fall back to the encrypted persisted `root_token` from `/vault/demo/init.json` by using the repo-owned bootstrap decryption helper.
- These helpers are local-development tooling. They are not intended for production Vault access flows.

## Start Only The Base Vault Service

Use this when you want a manual Vault and do not want auto-seeding:

```bash
docker compose --profile vault -f docker/m8flow-docker-compose.yml up -d vault
docker compose -f docker/m8flow-docker-compose.yml exec vault vault status
```

Expected first-run status:

- `Initialized false`
- `Sealed true`
- UI/API still reachable

If you stay on the manual path, initialize and unseal Vault yourself:

```bash
docker compose -f docker/m8flow-docker-compose.yml exec vault vault operator init
docker compose -f docker/m8flow-docker-compose.yml exec vault vault operator unseal
```

Then use one of the repo-owned policy bootstrap helpers:

```bash
export M8FLOW_VAULT_OPERATOR_TOKEN=<authorized-operator-token>
bash docker/vault/scripts/configure-m8flow-vault.sh
```

```powershell
$env:M8FLOW_VAULT_OPERATOR_TOKEN = "<authorized-operator-token>"
powershell -ExecutionPolicy Bypass -File docker/vault/scripts/configure-m8flow-vault.ps1
```

Those helpers keep the base `vault` profile manual. They enable the KV v2 mount and write the policy, but they do not auto-seed demo data.

## Start The Demo Bootstrap Workflow

Use this when you want an end-to-end local Vault demo with broker AppRole credentials and seeded secrets:

```bash
docker compose -f docker/m8flow-docker-compose.yml --profile vault --profile vault-demo up -d --build
```

If you want real demo secrets seeded, create your local seed file first:

```bash
cp docker/vault/demo/secrets.yml.sample docker/vault/demo/secrets.yml
```

```powershell
Copy-Item docker/vault/demo/secrets.yml.sample docker/vault/demo/secrets.yml
```

Then edit `docker/vault/demo/secrets.yml` and define the secrets you want seeded for the shared-realm `m8flow` tenant:

```yaml
tenants:
  m8flow:
    secrets:
      API_TOKEN: your-local-demo-token
      SMTP_PASSWORD: your-local-demo-password
```

What the `vault-demo` profile does on each run:

- waits for the base `vault` service;
- initializes Vault if needed and persists the encrypted init payload in the demo state volume;
- auto-unseals Vault using the persisted development unseal key;
- enables KV v2 at `kv` if it is missing;
- enables AppRole auth if it is missing;
- creates or updates the shared broker `m8flow` policy;
- creates or updates the shared broker `m8flow` AppRole;
- reuses the persisted broker AppRole `secret_id` when it is still valid, otherwise generates a new one;
- writes `runtime.env` plus encrypted file-backed broker AppRole credentials into `/vault/demo`;
- if `docker/vault/demo/secrets.yml` exists, seeds it under the canonical tenant UUID that corresponds to the shared-realm `m8flow` organization alias;
- if `docker/vault/demo/secrets.yml` is absent, skips tenant secret seeding entirely while still bootstrapping Vault and the canonical `m8flow` tenant identity;
- skips existing seeded secrets by default;
- overwrites seeded secrets only when `M8FLOW_VAULT_DEMO_OVERWRITE=true`;
- provisions the seeded tenant's Vault policy and AppRole through the broker identity;
- verifies the broker identity cannot read the tenant secret directly;
- verifies the repo's backend `VaultClient` can read the seeded secret only after switching into a tenant-scoped Vault client.

When no real secret has been seeded yet, the tenant `secrets/` path will not appear in the Vault UI. That is normal for KV v2: empty folders are not persisted separately from secret documents.

That `m8flow` AppRole is the shared local broker identity. It is separate from the per-tenant AppRoles that M8Flow provisions when tenant creation/bootstrap runs.

The backend, Celery worker, Celery Flower, and the optional NATS workers mount `/vault/demo` read-only. Their startup commands load `runtime.env` automatically when it exists so the demo profile can supply the Vault address plus file-backed AppRole credentials. `M8FLOW_VAULT_ENABLED` is still controlled by your local `.env`.

## Recreate The Full Stack With Vault Demo

If you want to fully rebuild the local stack and include both `vault` and `vault-demo`, first enable Vault-backed runtime behavior in your local `.env`:

```dotenv
M8FLOW_VAULT_ENABLED=true
```

Then recreate the stack with the required profiles:

```bash
docker compose -f docker/m8flow-docker-compose.yml down --volumes
docker compose --profile init --profile vault --profile vault-demo -f docker/m8flow-docker-compose.yml build
docker compose --profile init --profile vault --profile vault-demo -f docker/m8flow-docker-compose.yml up -d
```

That sequence:

- removes the existing containers and named volumes;
- rebuilds the application images plus the profile-gated helpers;
- starts the base stack, `vault`, `vault-demo`, and the one-off `init` jobs in one pass.

## Vault UI Login

Open the local Vault UI at `http://127.0.0.1:${M8FLOW_VAULT_PORT:-8200}/ui/`.

The `vault-demo` bootstrap persists the local development init payload in encrypted form at `/vault/demo/init.json`. To print the usable `root_token` without depending on a running backend container:

```bash
docker compose -f docker/m8flow-docker-compose.yml --profile vault --profile vault-demo \
  run --rm --no-deps --entrypoint python m8flow-backend \
  -c "import sys; sys.path.insert(0, '/app/docker/vault/demo'); import bootstrap_vault_demo as b; print(b.root_token_from_init(b.load_init_payload()))"
```

```powershell
docker compose -f docker/m8flow-docker-compose.yml --profile vault --profile vault-demo `
  run --rm --no-deps --entrypoint python m8flow-backend `
  -c "import sys; sys.path.insert(0, '/app/docker/vault/demo'); import bootstrap_vault_demo as b; print(b.root_token_from_init(b.load_init_payload()))"
```

Use the printed `root_token` value to sign in to the Vault UI with the `Token` auth method.

That token stays the same across normal container restarts, rebuilds, and `docker compose up/down` runs as long as the named volumes are preserved. It changes only when Vault is re-initialized, which for this local setup normally means removing both `m8flow_vault-data` and `m8flow_vault-demo-state`.

## Verification

Check the bootstrap logs:

```bash
docker compose -f docker/m8flow-docker-compose.yml logs vault-demo
```

Verify seeded-secret retrieval from the backend container:

```bash
docker compose -f docker/m8flow-docker-compose.yml exec m8flow-backend \
  python /app/docker/vault/demo/verify_backend_vault_demo.py
```

Verify the same path from the Celery worker container:

```bash
docker compose -f docker/m8flow-docker-compose.yml exec m8flow-celery-worker \
  python /app/docker/vault/demo/verify_backend_vault_demo.py
```

Inspect the latest verification report:

```bash
docker compose -f docker/m8flow-docker-compose.yml exec m8flow-backend \
  cat /vault/demo/verification.json
```

Re-run only the demo bootstrap services to confirm idempotency:

```bash
docker compose -f docker/m8flow-docker-compose.yml up -d vault-demo
```

Create another tenant after the stack is running to exercise the new per-tenant provisioning path. With Vault mode enabled, the tenant-create API now returns an error and rolls the tenant back if Vault policy/AppRole provisioning fails.

If you want the seed file to overwrite existing secrets on the next run:

```bash
export M8FLOW_VAULT_DEMO_OVERWRITE=true
docker compose -f docker/m8flow-docker-compose.yml up -d vault-demo
```

## Restart Behavior And Persistence

The local Vault data and generated demo credentials survive container restarts because both are stored in named Docker volumes.

Examples:

```bash
docker compose -f docker/m8flow-docker-compose.yml stop vault
docker compose -f docker/m8flow-docker-compose.yml start vault
docker compose -f docker/m8flow-docker-compose.yml up -d vault-demo
```

After a plain Vault restart:

- the Vault data still exists;
- Vault returns to the sealed state;
- `vault-demo` can unseal it again using the persisted development key.

## Reset The Local Vault Demo

Warning: this permanently deletes the local Vault data and the persisted development bootstrap state.

```bash
docker compose -f docker/m8flow-docker-compose.yml down
docker volume rm m8flow_vault-data m8flow_vault-demo-state
```

After removing those volumes, the next `vault-demo` run starts from a brand-new uninitialized Vault.

## Troubleshooting

- `vault-demo` fails saying the init file is missing while Vault is already initialized: the Vault data volume and the demo state volume are out of sync. Remove both and start again.
- Backend or Celery logs mention `http://localhost:8200`: the container-side Vault address is wrong. Containerized services must use `http://vault:8200`.
- `vault-demo` says the secrets file is missing: copy `docker/vault/demo/secrets.yml.sample` to `docker/vault/demo/secrets.yml` and edit the values locally.
- Seeded secrets did not change after you edited `secrets.yml`: this is expected unless `M8FLOW_VAULT_DEMO_OVERWRITE=true`.
- `verify_backend_vault_demo.py` fails inside a container: inspect `docker compose logs vault-demo` first, then check `/vault/demo/runtime.env` and `/vault/demo/verification.json`. A healthy report should show `broker_direct_read_blocked: true`.
- You want a manual Vault without auto-seeding: run only the `vault` profile and skip `vault-demo`.
