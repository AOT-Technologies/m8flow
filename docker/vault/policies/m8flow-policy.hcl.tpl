# Rendered by docker/vault/scripts/configure-m8flow-vault.* for the active
# KV v2 mount and the configured M8Flow path prefix.

path "__MOUNT_POINT__/data/__PATH_PREFIX__/tenants/+/secrets/+" {
  capabilities = ["create", "read", "update", "delete"]
}

path "__MOUNT_POINT__/metadata/__PATH_PREFIX__/tenants/+/secrets/+" {
  capabilities = ["delete"]
}
