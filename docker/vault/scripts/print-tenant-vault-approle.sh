#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../../.." && pwd)
compose_file="$repo_root/docker/m8flow-docker-compose.yml"

vault_service="${M8FLOW_VAULT_SERVICE_NAME:-vault}"
db_service="${M8FLOW_DB_SERVICE_NAME:-m8flow-db}"
backend_service="${M8FLOW_BACKEND_SERVICE_NAME:-m8flow-backend}"
vault_ui_base_url="${M8FLOW_VAULT_UI_BASE_URL:-}"
operator_token="${M8FLOW_VAULT_OPERATOR_TOKEN:-${VAULT_TOKEN:-}}"
tenant_identifier="${1:-}"
postgres_user="${POSTGRES_USER:-postgres}"
postgres_db="${POSTGRES_DB:-postgres}"
path_prefix="${M8FLOW_VAULT_SECRET_PATH_PREFIX:-m8flow}"
tenant_role_prefix="${M8FLOW_VAULT_TENANT_ROLE_PREFIX:-m8flow-tenant-role}"

fail() {
  echo >&2 "print-tenant-vault-approle: $*"
  exit 1
}

compose() {
  docker compose -f "$compose_file" "$@"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' is not available."
}

join_vault_path() {
  result=""
  for part in "$@"; do
    normalized_part=$(printf '%s' "$part" | sed 's#^/*##; s#/*$##')
    [ -n "$normalized_part" ] || continue
    if [ -n "$result" ]; then
      result="$result/$normalized_part"
    else
      result=$normalized_part
    fi
  done
  printf '%s\n' "$result"
}

sanitize_name_component() {
  normalized_value=$1
  [ -n "$normalized_value" ] || fail "Vault name component must not be empty."
  sanitized_value=$(printf '%s' "$normalized_value" | sed -E 's/[^A-Za-z0-9._-]+/-/g; s/^[.-]+//; s/[.-]+$//')
  [ -n "$sanitized_value" ] || fail "Vault name component '$normalized_value' does not contain any Vault-safe characters."
  printf '%s\n' "$sanitized_value"
}

normalize_host_ui_base_url() {
  raw_value=$1
  [ -n "$raw_value" ] || return 1

  normalized_value=$raw_value
  case "$normalized_value" in
    http://*|https://*) ;;
    *) normalized_value="http://$normalized_value" ;;
  esac

  normalized_value=$(printf '%s' "$normalized_value" | sed 's#://0\.0\.0\.0:#://127.0.0.1:#')
  printf '%s\n' "$normalized_value"
}

resolve_vault_ui_base_url() {
  if [ -n "$vault_ui_base_url" ]; then
    normalize_host_ui_base_url "$vault_ui_base_url"
    return
  fi

  set +e
  host_port="$(compose port "$vault_service" 8200 2>/dev/null | tail -n 1)"
  port_status=$?
  set -e

  if [ "$port_status" -eq 0 ] && [ -n "$host_port" ]; then
    normalize_host_ui_base_url "$host_port"
    return
  fi

  normalize_host_ui_base_url "127.0.0.1:${M8FLOW_VAULT_PORT:-8200}"
}

resolve_operator_token() {
  if [ -n "$operator_token" ]; then
    printf '%s\n' "$operator_token"
    return
  fi

  set +e
  resolved_token=$(compose exec -T "$backend_service" sh -c \
    'python -c "import sys; sys.path.insert(0, \"/app/docker/vault/demo\"); import bootstrap_vault_demo as b; print(b.root_token_from_init(b.load_init_payload()))"' \
    2>/dev/null)
  status_code=$?
  set -e
  if [ "$status_code" -eq 0 ] && [ -n "$resolved_token" ]; then
    printf '%s\n' "$resolved_token"
    return
  fi

  compose run --rm --no-deps "$backend_service" sh -c \
    'python -c "import sys; sys.path.insert(0, \"/app/docker/vault/demo\"); import bootstrap_vault_demo as b; print(b.root_token_from_init(b.load_init_payload()))"' \
    2>/dev/null || fail \
    "Could not resolve an operator token. Set M8FLOW_VAULT_OPERATOR_TOKEN (or VAULT_TOKEN), or run the local vault-demo bootstrap first."
}

resolve_tenant_row() {
  lookup_value=$1
  tenant_rows=$(compose exec -T "$db_service" \
    psql -U "$postgres_user" -d "$postgres_db" -At -F '|' -c 'select id, name, slug from m8flow_tenant order by created_at_in_seconds desc;') \
    || fail "Could not query tenants from service '$db_service'."

  matched_id=""
  matched_name=""
  matched_slug=""
  lower_lookup=$(printf '%s' "$lookup_value" | tr '[:upper:]' '[:lower:]')

  old_ifs=$IFS
  IFS='
'
  for tenant_row in $tenant_rows; do
    [ -n "$tenant_row" ] || continue
    row_id=$(printf '%s' "$tenant_row" | cut -d '|' -f 1)
    row_name=$(printf '%s' "$tenant_row" | cut -d '|' -f 2)
    row_slug=$(printf '%s' "$tenant_row" | cut -d '|' -f 3)

    lower_id=$(printf '%s' "$row_id" | tr '[:upper:]' '[:lower:]')
    lower_slug=$(printf '%s' "$row_slug" | tr '[:upper:]' '[:lower:]')
    lower_name=$(printf '%s' "$row_name" | tr '[:upper:]' '[:lower:]')

    if [ "$lower_lookup" = "$lower_id" ] || [ "$lower_lookup" = "$lower_slug" ] || [ "$lower_lookup" = "$lower_name" ]; then
      matched_id=$row_id
      matched_name=$row_name
      matched_slug=$row_slug
      break
    fi
  done
  IFS=$old_ifs

  [ -n "$matched_id" ] || fail "Tenant '$lookup_value' was not found in m8flow_tenant."
  printf '%s|%s|%s\n' "$matched_id" "$matched_name" "$matched_slug"
}

resolve_role_and_paths() {
  tenant_id=$1
  role_name="$(sanitize_name_component "$tenant_role_prefix")-$(sanitize_name_component "$tenant_id")"
  bootstrap_path=$(join_vault_path "$path_prefix" tenants "$tenant_id" bootstrap)
  secrets_path=$(join_vault_path "$path_prefix" tenants "$tenant_id" secrets)
  printf '%s\n%s\n%s\n' "$role_name" "$bootstrap_path" "$secrets_path"
}

require_command docker
require_command cut
require_command sed
require_command tail
require_command tr

[ -f "$compose_file" ] || fail "Compose file not found at $compose_file."
[ -n "$tenant_identifier" ] || fail "Usage: sh docker/vault/scripts/print-tenant-vault-approle.sh <tenant-id-or-slug-or-name>"

tenant_row=$(resolve_tenant_row "$tenant_identifier")
tenant_id=$(printf '%s' "$tenant_row" | cut -d '|' -f 1)
tenant_name=$(printf '%s' "$tenant_row" | cut -d '|' -f 2)
tenant_slug=$(printf '%s' "$tenant_row" | cut -d '|' -f 3)

role_and_paths=$(resolve_role_and_paths "$tenant_id") || fail "Could not resolve tenant Vault role metadata."
role_name=$(printf '%s\n' "$role_and_paths" | sed -n '1p')
bootstrap_path=$(printf '%s\n' "$role_and_paths" | sed -n '2p')
secrets_path=$(printf '%s\n' "$role_and_paths" | sed -n '3p')

[ -n "$role_name" ] || fail "Resolved tenant role name was empty."
[ -n "$bootstrap_path" ] || fail "Resolved tenant bootstrap path was empty."
[ -n "$secrets_path" ] || fail "Resolved tenant secrets path was empty."

resolved_operator_token=$(resolve_operator_token)
resolved_vault_ui_base_url=$(resolve_vault_ui_base_url)

role_id=$(compose exec -T \
  -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN="$resolved_operator_token" \
  -e VAULT_ROLE_NAME="$role_name" \
  "$vault_service" sh -c 'vault read -field=role_id "auth/approle/role/$VAULT_ROLE_NAME/role-id"') \
  || fail "Could not read role_id for tenant AppRole '$role_name'."

secret_id=$(compose exec -T \
  -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN="$resolved_operator_token" \
  -e VAULT_ROLE_NAME="$role_name" \
  "$vault_service" sh -c 'vault write -f -field=secret_id "auth/approle/role/$VAULT_ROLE_NAME/secret-id"') \
  || fail "Could not generate a secret_id for tenant AppRole '$role_name'."

auth_url="$resolved_vault_ui_base_url/ui/vault/auth?with=approle"
bootstrap_url="$resolved_vault_ui_base_url/ui/vault/secrets/kv/show/$bootstrap_path"
secrets_url="$resolved_vault_ui_base_url/ui/vault/secrets/kv/list/$secrets_path/"

cat <<EOF
tenant_name=$tenant_name
tenant_slug=$tenant_slug
tenant_id=$tenant_id
role_name=$role_name
role_id=$role_id
secret_id=$secret_id
approle_auth_url=$auth_url
bootstrap_url=$bootstrap_url
tenant_secrets_url=$secrets_url

This script minted a fresh tenant AppRole secret_id for local use.
Use the AppRole auth method in the Vault UI and sign in with:
  Role ID:   $role_id
  Secret ID: $secret_id
EOF
