# Runtime M8Flow policy. This identity can request a tenant-scoped token but
# cannot create or modify tenant AppRoles or policies.

path "auth/__APPROLE_MOUNT_POINT__/role/__TENANT_ROLE_PREFIX__-*/role-id" {
  capabilities = ["read"]
}

path "auth/__APPROLE_MOUNT_POINT__/role/__TENANT_ROLE_PREFIX__-*/secret-id" {
  capabilities = ["create", "update"]
}

path "auth/__APPROLE_MOUNT_POINT__/role/__TENANT_ROLE_PREFIX__-*/secret-id/destroy" {
  capabilities = ["update"]
}

path "auth/__APPROLE_MOUNT_POINT__/role/__TENANT_ROLE_PREFIX__-*/secret-id-accessor/destroy" {
  capabilities = ["update"]
}
