#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../../.." && pwd)
compose_file="$repo_root/docker/m8flow-docker-compose.yml"
policy_template="$repo_root/docker/vault/policies/m8flow-policy.hcl.tpl"

vault_service="${M8FLOW_VAULT_SERVICE_NAME:-vault}"
vault_addr="${M8FLOW_VAULT_INTERNAL_ADDR:-http://127.0.0.1:8200}"
mount_point="${M8FLOW_VAULT_MOUNT_POINT:-kv}"
path_prefix="${M8FLOW_VAULT_SECRET_PATH_PREFIX:-m8flow}"
policy_name="${M8FLOW_VAULT_POLICY_NAME:-m8flow}"
operator_token="${M8FLOW_VAULT_OPERATOR_TOKEN:-${VAULT_TOKEN:-}}"

fail() {
  echo >&2 "configure-m8flow-vault: $*"
  exit 1
}

compose() {
  docker compose -f "$compose_file" "$@"
}

escape_sed_replacement() {
  printf '%s' "$1" | sed 's/[&|]/\\&/g'
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' is not available."
}

require_command docker
require_command sed
require_command grep
require_command mktemp

[ -f "$compose_file" ] || fail "Compose file not found at $compose_file."
[ -f "$policy_template" ] || fail "Policy template not found at $policy_template."
[ -n "$operator_token" ] || fail "Set M8FLOW_VAULT_OPERATOR_TOKEN (or VAULT_TOKEN) to an authorized operator token."

set +e
status_json="$(compose exec -T "$vault_service" sh -lc "VAULT_ADDR='$vault_addr' vault status -format=json" 2>&1)"
status_code=$?
set -e

if [ "$status_code" -ne 0 ]; then
  echo "$status_json" | grep -q '"initialized"[[:space:]]*:[[:space:]]*false' \
    && fail "Vault is not initialized. Run 'docker compose -f docker/m8flow-docker-compose.yml exec vault vault operator init' first."
  echo "$status_json" | grep -q '"sealed"[[:space:]]*:[[:space:]]*true' \
    && fail "Vault is sealed. Unseal it before running this script."
  fail "Could not query Vault status from service '$vault_service'. Output: $status_json"
fi

echo "$status_json" | grep -q '"initialized"[[:space:]]*:[[:space:]]*false' \
  && fail "Vault is not initialized. Run 'docker compose -f docker/m8flow-docker-compose.yml exec vault vault operator init' first."
echo "$status_json" | grep -q '"sealed"[[:space:]]*:[[:space:]]*true' \
  && fail "Vault is sealed. Unseal it before running this script."

export VAULT_ADDR="$vault_addr"
export VAULT_TOKEN="$operator_token"
export MOUNT_POINT="$mount_point"
export POLICY_NAME="$policy_name"

compose exec -T -e VAULT_ADDR -e VAULT_TOKEN "$vault_service" sh -lc 'vault token lookup >/dev/null' \
  || fail "The supplied operator token is missing or not authorized for Vault administration."

if compose exec -T -e VAULT_ADDR -e VAULT_TOKEN -e MOUNT_POINT "$vault_service" \
  sh -lc 'vault secrets list -format=json | grep -q "\"${MOUNT_POINT%/}/\""'; then
  echo "configure-m8flow-vault: KV mount '$mount_point' already exists."
else
  compose exec -T -e VAULT_ADDR -e VAULT_TOKEN -e MOUNT_POINT "$vault_service" \
    sh -lc 'vault secrets enable -path="$MOUNT_POINT" -version=2 kv' >/dev/null
  echo "configure-m8flow-vault: enabled KV v2 mount '$mount_point'."
fi

tmp_policy="$(mktemp)"
trap 'rm -f "$tmp_policy"' EXIT HUP INT TERM

rendered_mount_point="$(escape_sed_replacement "$(printf '%s' "$mount_point" | sed 's#/*$##')")"
rendered_path_prefix="$(escape_sed_replacement "$(printf '%s' "$path_prefix" | sed 's#^/*##; s#/*$##')")"

sed \
  -e "s|__MOUNT_POINT__|$rendered_mount_point|g" \
  -e "s|__PATH_PREFIX__|$rendered_path_prefix|g" \
  "$policy_template" > "$tmp_policy"

compose exec -T -e VAULT_ADDR -e VAULT_TOKEN -e POLICY_NAME "$vault_service" \
  sh -lc 'vault policy write "$POLICY_NAME" -' < "$tmp_policy" >/dev/null

cat <<EOF
configure-m8flow-vault: wrote policy '$policy_name' for mount '$mount_point' and prefix '$path_prefix'.

Next steps:
1. For the development-only AppRole + demo-seeding flow, run:
   docker compose -f docker/m8flow-docker-compose.yml --profile vault --profile vault-demo up -d --build
2. Or create a non-root application token with that policy manually, for example:
   docker compose -f docker/m8flow-docker-compose.yml exec vault \\
     sh -lc 'VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=\$M8FLOW_VAULT_OPERATOR_TOKEN vault token create -policy=$policy_name -display-name=m8flow-local -ttl=24h -renewable=true'
3. Save the returned token outside source control and add these lines to your local .env:
   M8FLOW_VAULT_ENABLED=true
   M8FLOW_VAULT_ADDR=http://vault:8200
   M8FLOW_VAULT_TOKEN=<application token>
   M8FLOW_VAULT_MOUNT_POINT=$mount_point
   M8FLOW_VAULT_SECRET_PATH_PREFIX=$path_prefix
4. Restart the backend and Celery services after Vault is unsealed and the app token is configured.
EOF
