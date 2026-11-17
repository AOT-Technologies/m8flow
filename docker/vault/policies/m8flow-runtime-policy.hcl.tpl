# Runtime M8Flow identity has no AppRole control-plane access. The backend asks
# the isolated provisioner to log in to a tenant role and receives only the
# resulting tenant-scoped token.
path "sys/health" {
  capabilities = ["read"]
}
