# Vault Local Development

This repository supports two local Vault workflows:

- `vault` profile: a manual single-node development Vault.
- `vault-demo` profile: a development-only bootstrap layer on top of `vault` that initializes, unseals, configures, seeds, and verifies Vault automatically.

Both workflows are local-only. They use a single-node HTTP Vault with no TLS, no HA, no audit device, and no production-grade unseal strategy.

## Architecture

- Base Vault service: `vault`
- Demo bootstrap service: `vault-demo`
- Demo metadata seeder service: `vault-demo-seed`
- Vault image: `hashicorp/vault:1.18.5`
- Vault server config: [docker/vault/config/vault.hcl](../docker/vault/config/vault.hcl)
- Policy template: [docker/vault/policies/m8flow-policy.hcl.tpl](../docker/vault/policies/m8flow-policy.hcl.tpl)
- Demo bootstrap script: [docker/vault/demo/bootstrap_vault_demo.py](../docker/vault/demo/bootstrap_vault_demo.py)
- Demo metadata seeder script: [docker/vault/demo/seed_vault_demo_metadata.py](../docker/vault/demo/seed_vault_demo_metadata.py)
- Demo seed file: [docker/vault/demo/secrets.yml](../docker/vault/demo/secrets.yml)
- Runtime verification script: [docker/vault/demo/verify_backend_vault_demo.py](../docker/vault/demo/verify_backend_vault_demo.py)
- Persistent Vault data volume: `m8flow_vault-data`
- Persistent demo state volume: `m8flow_vault-demo-state`
- Host UI/API URL: `http://127.0.0.1:${M8FLOW_VAULT_PORT:-8200}`
- In-container Vault URL: `http://vault:8200`
- KV v2 mount used by M8Flow: `kv`
- Logical secret path convention: `kv/m8flow/tenants/{tenant_id}/secrets/{secret_name}`

The `vault-demo` profile stores generated local-only files inside the named demo state volume at `/vault/demo`:

- `init.json`
- `m8flow-role-id`
- `m8flow-secret-id`
- `m8flow-approle.env`
- `runtime.env`
- `verification.json`

Because those files live in a Docker volume instead of the repository, they are not committed and do not need `.gitignore` entries.

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

Use this when you want an end-to-end local Vault demo with AppRole credentials and seeded secrets:

```bash
docker compose -f docker/m8flow-docker-compose.yml --profile vault --profile vault-demo up -d --build
```

What the `vault-demo` profile does on each run:

- waits for the base `vault` service;
- initializes Vault if needed and persists the init payload in the demo state volume;
- auto-unseals Vault using the persisted development unseal key;
- enables KV v2 at `kv` if it is missing;
- enables AppRole auth if it is missing;
- creates or updates the `m8flow` policy;
- creates or updates the `m8flow` AppRole;
- reuses the persisted AppRole `secret_id` when it is still valid, otherwise generates a new one;
- writes `runtime.env` plus file-backed AppRole credentials into `/vault/demo`;
- seeds [docker/vault/demo/secrets.yml](../docker/vault/demo/secrets.yml) under the shared-realm `m8flow` tenant alias;
- skips existing seeded secrets by default;
- overwrites seeded secrets only when `M8FLOW_VAULT_DEMO_OVERWRITE=true`;
- starts `vault-demo-seed` after the backend is up so the seeded `m8flow` tenant resolves to its canonical local tenant UUID;
- ensures the local shared-realm `admin` user and principal exist;
- upserts `vault_metadata` rows as if `admin` created the seeded secrets for that tenant.
- verifies AppRole access with both raw Vault login and the repo's backend `VaultClient`.

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

The `vault-demo` bootstrap persists the local development init payload in `/vault/demo/init.json`. To inspect it without depending on a running backend container:

```bash
docker compose -f docker/m8flow-docker-compose.yml --profile vault --profile vault-demo \
  run --rm --no-deps m8flow-backend sh -lc "cat /vault/demo/init.json"
```

Use the `root_token` value from that JSON to sign in to the Vault UI with the `Token` auth method.

That token stays the same across normal container restarts, rebuilds, and `docker compose up/down` runs as long as the named volumes are preserved. It changes only when Vault is re-initialized, which for this local setup normally means removing both `m8flow_vault-data` and `m8flow_vault-demo-state`.

## Verification

Check the bootstrap logs:

```bash
docker compose -f docker/m8flow-docker-compose.yml logs vault-demo
```

Check the metadata-seeding logs:

```bash
docker compose -f docker/m8flow-docker-compose.yml logs vault-demo-seed
```

Verify seeded-secret retrieval plus `vault_metadata` ownership from the backend container:

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
docker compose -f docker/m8flow-docker-compose.yml up -d vault-demo vault-demo-seed
```

If you want the seed file to overwrite existing secrets on the next run:

```bash
export M8FLOW_VAULT_DEMO_OVERWRITE=true
docker compose -f docker/m8flow-docker-compose.yml up -d vault-demo vault-demo-seed
```

## Restart Behavior And Persistence

The local Vault data and generated demo credentials survive container restarts because both are stored in named Docker volumes.

Examples:

```bash
docker compose -f docker/m8flow-docker-compose.yml stop vault
docker compose -f docker/m8flow-docker-compose.yml start vault
docker compose -f docker/m8flow-docker-compose.yml up -d vault-demo vault-demo-seed
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
- `vault-demo-seed` fails after Vault bootstraps successfully: inspect `docker compose logs vault-demo-seed` and confirm the backend finished migrations plus the shared-realm `m8flow` organization still exists.
- Backend or Celery logs mention `http://localhost:8200`: the container-side Vault address is wrong. Containerized services must use `http://vault:8200`.
- Seeded secrets did not change after you edited `secrets.yml`: this is expected unless `M8FLOW_VAULT_DEMO_OVERWRITE=true`.
- `verify_backend_vault_demo.py` fails inside a container: inspect `docker compose logs vault-demo` and `docker compose logs vault-demo-seed` first, then check `/vault/demo/runtime.env` and `/vault/demo/verification.json`.
- You want a manual Vault without auto-seeding: run only the `vault` profile and skip `vault-demo`.
