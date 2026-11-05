# Local single-node Vault server for docker/m8flow-docker-compose.yml.
# This is a development-only configuration: HTTP listener, single Raft node,
# and manual unseal after each restart.

ui = true

storage "raft" {
  path    = "/vault/data"
  node_id = "m8flow-vault-1"
}

listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"

  # Local Docker development only. Production must enable TLS.
  tls_disable = true
}

api_addr     = "http://vault:8200"
cluster_addr = "http://vault:8201"

disable_mlock = false
