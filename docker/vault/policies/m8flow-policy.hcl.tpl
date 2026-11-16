# Rendered by docker/vault/scripts/configure-m8flow-vault.* for the active
# AppRole auth mount plus the configured tenant policy/role prefixes.
# This is a privileged control-plane broker policy, not a tenant data policy.
# Any holder can create or rewrite every matching tenant AppRole and policy.
# It cannot mint tenant SecretIDs or read tenant KV data. Attach it only to the
# isolated tenant identity provisioner; never to API/worker processes.

path "sys/policies/acl/__TENANT_POLICY_PREFIX__-*" {
  capabilities = ["create", "read", "update"]
}

path "sys/policy/__TENANT_POLICY_PREFIX__-*" {
  capabilities = ["create", "read", "update"]
}

path "auth/__APPROLE_MOUNT_POINT__/role/__TENANT_ROLE_PREFIX__-*" {
  capabilities = ["create", "read", "update"]
}

path "auth/__APPROLE_MOUNT_POINT__/role/__TENANT_ROLE_PREFIX__-*/role-id" {
  capabilities = ["read"]
}
