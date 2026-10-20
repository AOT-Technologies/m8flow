# M8Flow Vault Deployment and Configuration Guide

This guide is for DevOps/SRE teams deploying an externally managed HashiCorp
Vault instance for M8Flow. It describes the integration contract, not an AWS
infrastructure implementation.

The local Docker Vault configuration is development-only. Do not reuse
`docker/vault/config/vault.hcl`, its HTTP listener, its Docker volumes, or the
`vault-demo` bootstrap as a QA or production deployment.

## 1. Security Model

M8Flow separates configuration metadata from sensitive values:

| Data | System of record |
| --- | --- |
| Non-sensitive connector fields and configuration metadata | M8Flow PostgreSQL |
| Sensitive connector fields | Vault KV v2 |
| Manual sensitive Configuration Variable values | Vault KV v2 |
| Manual Configuration Variable metadata | `m8flow_named_value` in PostgreSQL |
| Application audit events | `m8flow_audit_log` in PostgreSQL |

When `M8FLOW_VAULT_ENABLED=true`, M8Flow does not fall back to the legacy
database secret store, an environment variable, or a stale cache for sensitive
values. If Vault is unreachable, sealed, uninitialized, unauthenticated,
unauthorized, or missing the configured KV v2 mount, startup or the relevant
secret operation fails closed.

M8Flow uses two Vault identity layers:

- A broker/control-plane identity is used to reconcile tenant policies and
  AppRoles and to mint tenant-scoped credentials.
- A tenant-scoped AppRole identity performs tenant secret CRUD and list
  operations.

The broker identity must not be granted direct read access to tenant KV data.
Tenant isolation is enforced by the generated tenant policy as well as by
M8Flow request and database scoping.

Responsibilities:

- DevOps/SRE owns Vault availability, TLS, storage, sealing, audit devices,
  backups, monitoring, access to recovery material, and credential delivery.
- The M8Flow application team owns the integration contract, tenant policy
  shape, AppRole lifecycle calls, application audit events, and application
  behavior when Vault is unavailable.

## 2. Supported Deployment Model

M8Flow production deployment expects Vault to be managed outside the M8Flow
application Compose stack. The `vault` and `vault-demo` Compose profiles are
for local development and verification only.

### QA reference model

A single-node Vault deployment is acceptable for the current AWS QA target if
the following contract is met:

- Vault is reachable only through a private network endpoint.
- Vault uses durable encrypted storage.
- Vault serves HTTPS with a certificate trusted by the M8Flow containers.
- KV v2 is mounted at `kv` and AppRole auth is mounted at `approle`, unless
  the corresponding M8Flow settings are changed consistently.
- The broker identity and tenant identities are provisioned with least
  privilege.
- Vault audit logging and retention are enabled.
- Recovery material and encrypted backups have an owner and a restore test.

A single node has no high availability. A Vault outage prevents M8Flow from
starting in Vault mode or retrieving sensitive configuration. This QA model is
not a production HA architecture.

### Production direction

Production should use a multi-node HA Vault cluster across failure domains,
tested disaster recovery, durable encrypted storage, an approved auto-unseal
strategy, and a formal credential rotation process. Those infrastructure
choices are outside this repository and must be supplied by DevOps/SRE.

### Version and download guidance

The repository's local Docker Compose setup currently pins
`hashicorp/vault:1.18.5`. This is the development/verification version used by
the M8Flow local stack; it is not a production recommendation.

For QA and production:

- Select a currently supported stable Vault release through the organization's
  security and platform approval process.
- Pin the exact Vault version, and preferably the image digest when deploying
  a container. Do not use `latest`.
- Validate the selected version against the M8Flow integration contract before
  rollout, including KV v2, AppRole, policy/AppRole lifecycle operations, TLS,
  audit logging, seal/unseal, and the `/v1.0/vault-status` behavior.
- Keep the same approved version across the Vault cluster nodes. Upgrade one
  version at a time using HashiCorp's upgrade guidance and a tested rollback
  procedure.

Use HashiCorp's official sources only:

- [Vault installation instructions](https://developer.hashicorp.com/vault/install)
  provide platform-specific installation methods and the currently advertised
  release.
- [HashiCorp Vault releases](https://releases.hashicorp.com/vault/) provide
  versioned binaries and checksum files. Verify checksums and signatures before
  installing a binary.
- [Official Vault Docker image](https://hub.docker.com/_/vault) provides the
  container distribution. Pin a version or digest in deployment manifests.
- [Vault hardening guidance](https://developer.hashicorp.com/vault/docs/concepts/production-hardening)
  and the [integrated storage reference architecture](https://developer.hashicorp.com/vault/docs/deploy/raft)
  should be used when designing non-local deployments.

Do not upgrade the repository's local image solely because a newer release is
available. Change the Compose pin only after compatibility tests pass and the
local demo bootstrap has been verified.

## 3. Deployment Contract

### Network and TLS

Expose Vault only to the M8Flow runtime network and approved operator paths.
Do not expose the Vault API publicly. Use an HTTPS address such as:

```text
https://<VAULT_PRIVATE_DNS_NAME>
```

Mount the issuing CA bundle into each M8Flow backend and worker container and
set `M8FLOW_VAULT_CACERT` to its in-container path. Certificate verification
must remain enabled. `M8FLOW_VAULT_SKIP_VERIFY=true` is for local non-production
diagnostics only and must not be used in QA or production.

Certificate rotation must preserve trust continuity: deploy the new CA chain,
verify M8Flow connectivity, rotate the server certificate, and remove the old
CA only after all clients have been updated.

### Storage and process security

Vault storage must be durable, encrypted, monitored for capacity, and included
in the backup and restore plan. Run Vault under a dedicated unprivileged
service account. Restrict the Vault configuration and credential files to the
Vault service account and the designated operator group.

The deployment should also address swap, core dumps, host patching, process
limits, and certificate/private-key permissions. Do not place static AWS
access keys in Vault configuration. If AWS KMS auto-unseal is selected, use
the platform IAM role/instance or workload identity mechanism approved by
DevOps.

### Seal and unseal

For QA, AWS KMS auto-unseal is recommended, but the KMS key, ownership,
permissions, and recovery procedure are DevOps decisions. Manual unseal is
acceptable only when the operational process and recovery-material custody are
documented and tested.

## 4. Vault Bootstrap

The following commands are structural examples only. Replace placeholders and
run them from an approved operator environment. Never paste real tokens,
Secret IDs, recovery keys, private keys, or secret values into tickets, shell
history, CI logs, or this repository.

### Initialize and verify Vault

Initialization and recovery material must be handled according to the approved
Vault custody process. Do not print the response in a shared terminal:

```bash
export VAULT_ADDR=<VAULT_ADDR>
export VAULT_CACERT=<PATH_TO_M8FLOW_CA_BUNDLE>

# Run through the approved secure operator procedure.
vault operator init <APPROVED_INIT_OPTIONS>
vault status
```

The output of `vault operator init` contains recovery material and must not be
captured in normal logs. With auto-unseal, verify the seal state and KMS access
instead of creating an ad hoc unseal workflow.

### Required mounts

M8Flow defaults are:

```text
KV v2 mount:   kv
AppRole mount: approle
Path prefix:   m8flow
```

Verify the mounts without exposing credentials:

```bash
vault secrets list -format=json
vault auth list -format=json
```

If the deployment uses different mount names, set `M8FLOW_VAULT_MOUNT_POINT`
and `M8FLOW_VAULT_APPROLE_MOUNT_POINT` identically for every M8Flow runtime
that uses the cluster.

### Vault audit device

Enable at least one Vault audit device before application cutover and route its
output to the approved protected destination. The exact device and retention
platform are DevOps decisions. Example structure, with placeholders only:

```bash
vault audit enable file file_path=<PROTECTED_VAULT_AUDIT_LOG_PATH>
vault audit list -format=json
```

The audit destination must have restricted permissions, rotation, retention,
capacity monitoring, and an alert when all audit devices become unavailable.
Vault audit logs may contain sensitive request metadata; protect them as
security logs.

### Broker policy and AppRole

The broker policy must allow only the control-plane operations M8Flow uses to
reconcile tenant policies and AppRoles. It must not grant read, list, or
delete access to tenant KV data. The local policy template is a reference for
the broker control-plane shape:

[docker/vault/policies/m8flow-policy.hcl.tpl](../docker/vault/policies/m8flow-policy.hcl.tpl)

The policy and AppRole names used by the local demo default to `m8flow`, but
QA/production names and credential delivery are DevOps-controlled. Provision
the broker policy and AppRole through the approved Vault administration path;
do not use a root token as the M8Flow runtime credential.

### Tenant policy and AppRole lifecycle

When Vault mode is enabled, M8Flow provisions a policy and AppRole for each
tenant using the canonical tenant UUID. Defaults are:

```text
Policy prefix:                 m8flow-tenant-policy
AppRole prefix:                m8flow-tenant-role
Secret ID uses:                1
Secret ID TTL:                 10m
Tenant token initial TTL:      10m
Tenant token maximum TTL:      30m
```

These values are passed by M8Flow when it creates or updates tenant AppRoles;
they are not a substitute for Vault-side security review. M8Flow currently
does not implement a separate broker-token rotation or a general token-renewal
workflow. DevOps must define rotation and revocation procedures.

## 5. M8Flow Runtime Configuration

The following are the actual M8Flow Vault variables currently implemented.
Values may be supplied directly or, for credentials, through the matching
file-based variable. File-based delivery is preferred.

| Variable | Default / role | Purpose |
| --- | --- | --- |
| `M8FLOW_VAULT_ENABLED` | disabled | Enables the fail-closed Vault backend. |
| `M8FLOW_VAULT_ADDR` or `VAULT_ADDR` | none | Vault API base URL. |
| `M8FLOW_VAULT_CACERT` or `VAULT_CACERT` | system trust | CA bundle path for TLS verification. |
| `M8FLOW_VAULT_SKIP_VERIFY` or `VAULT_SKIP_VERIFY` | false | Disables TLS verification; local diagnostics only. |
| `M8FLOW_VAULT_TOKEN` or `VAULT_TOKEN` | none | Broker/control-plane token auth. |
| `M8FLOW_VAULT_TOKEN_FILE` or `VAULT_TOKEN_FILE` | none | File containing the broker token. |
| `M8FLOW_VAULT_ROLE_ID` or `VAULT_ROLE_ID` | none | Broker AppRole role ID. |
| `M8FLOW_VAULT_ROLE_ID_FILE` or `VAULT_ROLE_ID_FILE` | none | File containing the broker role ID. |
| `M8FLOW_VAULT_SECRET_ID` or `VAULT_SECRET_ID` | none | Broker AppRole Secret ID. |
| `M8FLOW_VAULT_SECRET_ID_FILE` or `VAULT_SECRET_ID_FILE` | none | File containing the broker Secret ID. |
| `M8FLOW_VAULT_NAMESPACE` or `VAULT_NAMESPACE` | none | Optional Vault Enterprise namespace; not required by M8Flow. |
| `M8FLOW_VAULT_MOUNT_POINT` | `kv` | KV v2 mount. |
| `M8FLOW_VAULT_SECRET_PATH_PREFIX` | `m8flow` | Root path prefix inside KV. |
| `M8FLOW_VAULT_APPROLE_MOUNT_POINT` | `approle` | AppRole auth mount. |
| `M8FLOW_VAULT_TENANT_POLICY_PREFIX` | `m8flow-tenant-policy` | Tenant policy name prefix. |
| `M8FLOW_VAULT_TENANT_ROLE_PREFIX` | `m8flow-tenant-role` | Tenant AppRole name prefix. |
| `M8FLOW_VAULT_TENANT_SECRET_ID_NUM_USES` | `1` | Uses allowed for generated tenant Secret IDs. |
| `M8FLOW_VAULT_TENANT_SECRET_ID_TTL` | `10m` | Generated tenant Secret ID TTL. |
| `M8FLOW_VAULT_TENANT_TOKEN_TTL` | `10m` | Initial tenant token TTL. |
| `M8FLOW_VAULT_TENANT_TOKEN_MAX_TTL` | `30m` | Maximum tenant token TTL. |
| `M8FLOW_VAULT_TIMEOUT_SECONDS` | `5` | Vault API request timeout. |

Do not set both token auth and AppRole auth with conflicting values. M8Flow
prefers token auth when a token is configured; otherwise it requires both
broker AppRole role and Secret IDs.

Mount credential files read-only inside the backend, Celery worker, and any
other process that performs Vault operations. For example, the contract is:

```text
/run/m8flow-vault/role-id       mode 0600, runtime account readable
/run/m8flow-vault/secret-id     mode 0600, runtime account readable
/run/m8flow-vault/ca-bundle.pem mode 0644 or tighter, runtime account readable
```

Use the corresponding `*_FILE` variables with these in-container paths. Do
not put broker credentials in the image or source tree.

### Startup validation

With Vault enabled, `configure_vault()` validates configuration and calls the
Vault startup readiness check before the application serves requests. Startup
fails if the address or broker credentials are incomplete, Vault cannot be
authenticated, Vault is unavailable, or the configured mount is not KV v2.
Celery and other workers must receive the same effective Vault configuration.

### Vault status endpoint

M8Flow exposes a separate endpoint:

```text
GET /v1.0/vault-status
```

Example healthy response:

```json
{
  "ok": true,
  "enabled": true,
  "configured": true,
  "healthy": true,
  "mount_point": "kv",
  "auth_method": "approle"
}
```

The endpoint returns `200` when Vault is disabled or when it is enabled,
configured, and healthy. It returns `503` when Vault is enabled but unhealthy,
or when the process is in the defensive enabled/unconfigured state. The public
probe is non-auditing and does not create application audit rows.

Also verify the normal application status endpoint independently. A successful
Vault status response does not replace application, database, or Keycloak
health checks.

## 6. Secret Paths and Access Control

The generic logical root is:

```text
kv/m8flow/tenants/{tenant_id}/secrets/...
```

Tenant IDs are encoded by the application when building paths. The tenant
policy is limited to that tenant's subtree and grants data operations under
the KV v2 `data` path plus the required metadata operations.

### Connector configuration

Sensitive connector fields are stored together:

```text
kv/m8flow/tenants/{tenant_id}/secrets/connector-configuration/{connector_configuration_id}
```

The document contains only sensitive connector fields, for example:

```json
{
  "SMTP_USER": "<SENSITIVE_VALUE>",
  "SMTP_PASSWORD": "<SENSITIVE_VALUE>"
}
```

Non-sensitive connector fields and sensitivity/configured metadata remain in
`m8flow_connector_configuration` and `m8flow_connector_variable`.

### Manual sensitive Configuration Variables

Manual sensitive values use the immutable named-value UUID:

```text
kv/m8flow/tenants/{tenant_id}/secrets/configuration-variable/{named_value_id}
```

The document is exactly:

```json
{
  "value": "<SENSITIVE_VALUE>"
}
```

The database remains authoritative for the variable name, description,
tenant, sensitivity, configured state, user, and timestamps. Normal list and
detail APIs are database-backed and do not read or expose Vault plaintext.

### Lifecycle operations

- Provisioning: tenant creation reconciles the tenant policy and AppRole.
- Rotation: update the Vault payload through the M8Flow API or approved
  operator process; do not write a database copy of the sensitive value.
- Revocation: revoke the tenant AppRole credentials and reconcile the tenant
  identity when compromise is suspected.
- Deletion: delete the M8Flow catalog record and the corresponding Vault
  document through the supported application operation.
- Tenant recovery: restore the tenant database identity and Vault policy/
  AppRole consistently, then verify access with a tenant-scoped credential.

Recommended production controls, not claims about current M8Flow enforcement,
include short Secret ID/token TTLs, one-time Secret IDs, automated credential
rotation, revocation on personnel or tenant offboarding, and alerting on
unexpected policy changes.

## 7. Operations and Runbooks

### Pre-deployment checklist

- [ ] Private Vault DNS/network route exists from every M8Flow runtime.
- [ ] HTTPS certificate and CA bundle are issued and mounted.
- [ ] Durable encrypted storage and capacity alerts are configured.
- [ ] Seal/unseal or auto-unseal ownership is documented.
- [ ] KV v2 exists at the configured mount.
- [ ] AppRole exists at the configured auth mount.
- [ ] Broker policy cannot read tenant KV data.
- [ ] Tenant policy template is approved and limits each tenant UUID subtree.
- [ ] Vault audit device is enabled and its retention destination is healthy.
- [ ] Backup and restore test evidence is available.

### Application cutover checklist

- [ ] Deploy the CA bundle and file-based broker credentials with restricted
      permissions.
- [ ] Set `M8FLOW_VAULT_ENABLED=true` and the exact variables required above.
- [ ] Restart backend and all workers together.
- [ ] Confirm startup readiness succeeded without credential-bearing logs.
- [ ] Confirm `GET /v1.0/vault-status` returns the expected redacted status.
- [ ] Create or reconcile one non-production tenant and verify its policy and
      AppRole.
- [ ] Perform a test sensitive read/write with the tenant-scoped path.
- [ ] Verify no sensitive plaintext is present in PostgreSQL or application
      logs.
- [ ] Verify the corresponding `m8flow_audit_log` events contain metadata only.

### Monitoring and alerting

Monitor and alert on:

- Vault health and seal state.
- Authentication failures and authorization denials.
- Vault audit-device write failures.
- Raft/storage capacity and snapshot failures.
- TLS certificate expiry and CA trust failures.
- `/v1.0/vault-status` returning `503`.
- M8Flow startup failures while Vault mode is enabled.
- Unexpected tenant policy/AppRole changes.

Application audit events are stored in `m8flow_audit_log`; Vault server audit
events remain in the Vault audit device destination. These are separate logs
and should be correlated by the operations platform where possible.

### Vault unavailable or sealed

1. Confirm Vault network, TLS, health, and seal state without printing tokens.
2. Check the Vault audit device and storage health.
3. Do not disable Vault mode to bypass an outage unless the change is an
   explicitly approved rollback; disabling Vault is not a data migration and
   does not copy Vault values into PostgreSQL.
4. Restore Vault availability or credentials, then restart affected M8Flow
   services if startup failed.
5. Verify `/v1.0/vault-status`, one tenant-scoped operation, and audit events.

### Broker credential rotation

Create the replacement broker credential using the approved Vault process,
deliver it as a new restricted file, update the corresponding `*_FILE` setting,
restart backend and workers, verify startup and status, then revoke the old
credential. Never print either credential during the process.

### Tenant identity recovery

For a tenant identity failure, verify the canonical tenant UUID, policy name,
AppRole name, policy contents, and AppRole policy attachment. Reconcile using
the M8Flow tenant-provisioning path or an approved operator procedure. Do not
grant the broker direct tenant-secret read access as a workaround.

### Backup, restore, and upgrade

Back up Vault storage using the approved Vault snapshot procedure and encrypt
the backup externally. A restore is not complete until DevOps records a test
that verifies:

- Vault starts and is unsealed.
- KV v2 and AppRole mounts are present.
- The broker identity authenticates.
- A tenant identity can access only its own subtree.
- M8Flow startup and `/v1.0/vault-status` succeed.
- Sensitive values are retrievable only through the intended tenant identity.

For a QA single node, schedule maintenance, stop or drain M8Flow secret
operations, take a verified backup, upgrade Vault, verify seal/mount/audit
state, then restart or reconcile M8Flow. Production requires the HA upgrade
procedure approved by the Vault operators.

## 8. QA Reference Deployment on AWS

This is a reference contract, not AWS infrastructure code:

- One Vault node in a private subnet with encrypted persistent storage.
- Security groups allow Vault API traffic only from M8Flow runtime networks and
  approved operator paths.
- Private DNS resolves the Vault HTTPS endpoint.
- AWS KMS auto-unseal is recommended, subject to KMS ownership and IAM review.
- The CA bundle is mounted into M8Flow containers.
- Vault audit logs are forwarded to the approved protected log destination.
- Encrypted Vault backups are stored outside the node and restore-tested.
- Cloud and host monitoring cover availability, seal state, storage, TLS,
  audit-device health, and backup success.

This model has no Vault HA and must not be represented as production-ready.

## 9. Security Acceptance Checklist

| Control | Evidence |
| --- | --- |
| Private network exposure | Network/security-group review |
| TLS verification | Redacted M8Flow startup/status evidence and CA deployment record |
| Durable encrypted storage | Storage configuration and backup record |
| Seal/unseal ownership | Approved runbook and recovery-material custody record |
| Required mounts | Redacted `vault secrets list` / `vault auth list` output |
| Broker least privilege | Reviewed broker policy; denied direct tenant-secret read test |
| Tenant isolation | Two-tenant positive/negative access test using tenant identities |
| Fail-closed startup | Test with unavailable, sealed, or unauthorized Vault |
| Application health | Successful `/v1.0/vault-status` and normal application status |
| Application audit | Metadata-only `m8flow_audit_log` verification |
| Vault audit | Audit-device listing, retention, and failure alert evidence |
| Backup and restore | Successful restore-test report |
| Credential rotation | Broker and tenant credential rotation evidence |

## Open Decisions / DevOps Inputs Required

The repository cannot determine:

- QA Vault DNS name and private routing design.
- Certificate issuer, CA distribution, and rotation owner.
- AWS KMS key ownership, IAM role, and auto-unseal approval.
- Vault storage implementation and capacity thresholds.
- Vault audit-device destination, retention, access controls, and SIEM owner.
- Backup location, encryption key, retention, and restore-test schedule.
- Broker credential delivery mechanism and rotation schedule.
- Tenant credential revocation and emergency-access procedure.
- QA maintenance window and single-node outage communication.
- Production HA topology, failure domains, DR objectives, and upgrade owner.

## Repository References

- [Vault local development](./vault-local-development.md)
- [Environment reference](./env-reference.md)
- [Local Vault configuration](../docker/vault/config/vault.hcl)
- [Broker policy template](../docker/vault/policies/m8flow-policy.hcl.tpl)
- [Tenant policy provisioning](../m8flow-backend/src/m8flow_backend/services/tenant_vault_provisioning_service.py)
- [Vault client](../m8flow-backend/src/m8flow_backend/services/vault_client.py)
