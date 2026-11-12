# Local Vault development

The main Compose stack can run a local, single-node HashiCorp Vault for development and demos. It is disabled unless the `vault` and `vault-demo` profiles are selected. This setup uses HTTP, a persisted local root token and unseal key, and a development-only broker AppRole. Do not use these settings or volumes in production. Production Vault address, TLS, authentication, policies, and secret delivery must be configured by the deployment environment.

## Start the local Vault demo

Set `M8FLOW_VAULT_ENABLED=true` (or `M8FLOW_SECRET_BACKEND_KIND=vault`) in the ignored root `.env` file. The Vault broker credentials are generated in a local named volume and loaded by backend and worker containers. Database secrets remain the default when Vault mode is not enabled.

Optionally create a local seed file. It is ignored by Git:

```powershell
Copy-Item docker/vault/demo/secrets.yml.sample docker/vault/demo/secrets.yml
```

Edit `docker/vault/demo/secrets.yml` to add development configuration variables. Each entry has a value and an explicit sensitivity flag. Ordinary values are stored in `m8flow_named_value.value`; only sensitive values are written to Vault at the UUID-based `configuration-variable/<id>` path. Then start the stack:

```powershell
docker compose --env-file .env --profile vault --profile vault-demo -f docker/m8flow-docker-compose.yml up -d --build
```

Compose runs these steps in order:

1. `vault` starts the local Vault server.
2. `vault-demo` initializes/unseals Vault as needed, enables KV v2 and AppRole, creates the broker policy and role, and stores Vault root/unseal state in `vault-admin-state`, which only this bootstrap service mounts. It also creates a non-renewable five-minute seed token scoped to `kv/data/m8flow/tenants/m8flow/secrets/configuration-variable/*`; that token is stored in the separate `vault-seed-state` volume. Broker credentials remain in `vault-runtime`.
3. `m8flow-backend` starts and runs its normal database migrations before serving requests. Backend and worker entrypoints load the local broker credential paths from the state volume.
4. `vault-seed` waits for the backend healthcheck, which can pass only after the migrated backend serves `/v1.0/healthy`. It then writes named configuration variables for the default `m8flow` tenant. Existing values are preserved unless `M8FLOW_VAULT_DEMO_OVERWRITE=true`.

The seed script still accepts the previous `secrets:` format for local files that have not been updated: `SMTP_HOST` and `SMTP_PORT` become ordinary values, while other legacy entries default to sensitive. If an existing variable should adopt the new sensitivity declared in the seed file, set `M8FLOW_VAULT_DEMO_OVERWRITE=true` for that local seed run. If `secrets.yml` is absent, Vault still starts and the seed step exits successfully without writing demo values. Verify service order and result with:

```powershell
docker compose --env-file .env --profile vault --profile vault-demo -f docker/m8flow-docker-compose.yml ps
docker compose --env-file .env --profile vault --profile vault-demo -f docker/m8flow-docker-compose.yml logs vault-demo vault-seed m8flow-backend
```

Open the local Vault UI at `http://127.0.0.1:8200/ui/`. The local root token and unseal key are in the private `vault-admin-state` Docker volume. The seeder cannot mount that volume; it receives only the short-lived seed token from `vault-seed-state`, and that token cannot access connector secrets or other tenants. The bootstrap service migrates and removes `init.json` from the legacy `vault-demo-state` volume when upgrading an existing local setup. Backend and worker containers mount only broker credentials from `vault-runtime`. Treat these volumes as development credentials. They are persistent; removing them resets local bootstrap state. Removing the Vault data volume deletes local Vault data. The seed token is regenerated each time `vault-demo` runs and expires after five minutes.

## Manual Vault configuration

For a manually managed local Vault, start only the base service:

```powershell
docker compose --env-file .env --profile vault -f docker/m8flow-docker-compose.yml up -d vault
```

Use `docker/vault/scripts/configure-m8flow-vault.ps1` or `.sh` to configure an already initialized Vault with the tenant policy and KV v2 mount. The scripts require an operator token and do not alter deployment configuration.

## Files

- `docker/vault/config/vault.hcl`: local-only single-node server configuration.
- `docker/vault/policies/m8flow-policy.hcl.tpl`: broker policy template used by the manual setup script.
- `docker/vault/demo/bootstrap_vault_demo.py`: local Vault initialization and broker AppRole bootstrap.
- `docker/vault/demo/seed_vault_demo.py`: post-migration demo named-value and sensitive Vault seeding.
- `docker/vault/demo/secrets.yml.sample`: example local seed file.
