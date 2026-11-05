# Rendered by docker/vault/scripts/configure-m8flow-vault.* for the active
# AppRole auth mount plus the configured tenant policy/role prefixes.

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

path "auth/__APPROLE_MOUNT_POINT__/role/__TENANT_ROLE_PREFIX__-*/secret-id" {
  capabilities = ["create", "update"]
}
