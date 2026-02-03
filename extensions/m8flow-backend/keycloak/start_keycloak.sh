#!/usr/bin/env bash

function setup_traps() {
  trap 'error_handler ${LINENO} $?' ERR
}
function remove_traps() {
  trap - ERR
}

function error_handler() {
  echo >&2 "Exited with BAD EXIT CODE '${2}' in ${0} script at line: ${1}."
  exit "$2"
}
setup_traps

set -o errtrace -o errexit -o nounset -o pipefail

keycloak_version=26.0.7
keycloak_base_url="http://localhost:7002"
keycloak_admin_user="admin"
keycloak_admin_password="admin"

# Get script directory
script_dir="$(
  cd -- "$(dirname "$0")" >/dev/null 2>&1
  pwd -P
)"

# Realm export file paths
identity_realm_file="${script_dir}/realm_exports/identity-realm-export.json"
tenant_realm_file="${script_dir}/realm_exports/tenant-realm-export.json"
# Backend default auth uses spiffworkflow-local; must exist and have sslRequired=NONE for HTTP
spiffworkflow_local_realm_file="${script_dir}/realm_exports/spiffworkflow-local-realm.json"

# Validate required tools
if ! command -v docker &> /dev/null; then
  echo >&2 "ERROR: docker command not found. Please install Docker."
  exit 1
fi

if ! command -v curl &> /dev/null; then
  echo >&2 "ERROR: curl command not found. Please install curl."
  exit 1
fi

if ! command -v jq &> /dev/null; then
  echo >&2 "ERROR: jq command not found. Please install jq."
  exit 1
fi

# Validate realm export files exist
if [[ ! -f "$identity_realm_file" ]]; then
  echo >&2 "ERROR: Identity realm export file not found: $identity_realm_file"
  exit 1
fi

if [[ ! -f "$tenant_realm_file" ]]; then
  echo >&2 "ERROR: Tenant realm export file not found: $tenant_realm_file"
  exit 1
fi

if [[ ! -f "$spiffworkflow_local_realm_file" ]]; then
  echo >&2 "ERROR: Spiffworkflow-local realm export file not found: $spiffworkflow_local_realm_file"
  exit 1
fi

# Docker network setup
echo ":: Checking Docker network..."
if ! docker network inspect m8flow >/dev/null 2>&1; then
  echo ":: Creating Docker network: m8flow"
  if ! docker network create m8flow; then
    echo >&2 "ERROR: Failed to create Docker network 'm8flow'"
    exit 1
  fi
fi

# Container management
container_name="keycloak"
container_regex="^keycloak$"
if [[ -n "$(docker ps -qa -f name=$container_regex 2>/dev/null)" ]]; then
  echo ":: Found existing container - $container_name"
  if [[ -n "$(docker ps -q -f name=$container_regex 2>/dev/null)" ]]; then
    echo ":: Stopping running container - $container_name"
    if ! docker stop $container_name; then
      echo >&2 "ERROR: Failed to stop container $container_name"
      exit 1
    fi
  fi
  echo ":: Removing stopped container - $container_name"
  if ! docker rm $container_name; then
    echo >&2 "ERROR: Failed to remove container $container_name"
    exit 1
  fi
fi

# Wait for Keycloak to be ready
function wait_for_keycloak_to_be_up() {
  local max_attempts=600
  echo ":: Waiting for Keycloak to be ready..."
  local attempts=0
  local url="http://localhost:7009/health/ready"
  while [[ "$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo "000")" != "200" ]]; do
    if [[ "$attempts" -gt "$max_attempts" ]]; then
      echo >&2 "ERROR: Keycloak health check failed after $max_attempts attempts. URL: $url"
      return 1
    fi
    attempts=$((attempts + 1))
    sleep 1
  done
  echo ":: Keycloak is ready"
}

# Start Keycloak container
echo ":: Starting Keycloak container..."
if ! docker run \
  -p 7002:8080 \
  -p 7009:9000 \
  -d \
  --network=m8flow \
  --name keycloak \
  -e KEYCLOAK_LOGLEVEL=ALL \
  -e ROOT_LOGLEVEL=ALL \
  -e KEYCLOAK_ADMIN="$keycloak_admin_user" \
  -e KEYCLOAK_ADMIN_PASSWORD="$keycloak_admin_password" \
  -e KC_HEALTH_ENABLED="true" \
  quay.io/keycloak/keycloak:${keycloak_version} start-dev \
  -Dkeycloak.profile.feature.token_exchange=enabled \
  -Dkeycloak.profile.feature.admin_fine_grained_authz=enabled \
  -D--spi-theme-static-max-age=-1 \
  -D--spi-theme-cache-themes=false \
  -D--spi-theme-cache-templates=false; then
  echo >&2 "ERROR: Failed to start Keycloak container"
  exit 1
fi

# Wait for Keycloak to be ready
if ! wait_for_keycloak_to_be_up; then
  echo >&2 "ERROR: Keycloak failed to become ready"
  exit 1
fi

# Additional wait for admin API to be ready
echo ":: Waiting for admin API to be ready..."
sleep 3

# Turn off SSL for master realm so token and admin API work over HTTP (localhost)
echo ":: Configuring master realm for HTTP access..."
docker exec keycloak /opt/keycloak/bin/kcadm.sh config credentials --server http://localhost:8080 --realm master --user admin --password admin 2>/dev/null || true
docker exec keycloak /opt/keycloak/bin/kcadm.sh update realms/master -s sslRequired=NONE 2>/dev/null || true

# Get admin token
function get_admin_token() {
  local token_url="${keycloak_base_url}/realms/master/protocol/openid-connect/token"
  local token_out
  local token_code
  local token_body

  echo ":: Obtaining admin access token..." >&2
  token_out=$(mktemp)
  token_code=$(curl -s -w '%{http_code}' -o "$token_out" -X POST "$token_url" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "grant_type=password&client_id=admin-cli&username=${keycloak_admin_user}&password=${keycloak_admin_password}")
  token_body=$(cat "$token_out")
  rm -f "$token_out"

  if [[ "$token_code" -lt 200 || "$token_code" -ge 300 ]]; then
    echo >&2 "ERROR: Token request failed (HTTP $token_code): $token_body"
    return 1
  fi

  local token
  token=$(echo "$token_body" | jq -r '.access_token // empty' 2>/dev/null)

  if [[ -z "$token" || "$token" == "null" ]]; then
    echo >&2 "ERROR: No access_token in response (HTTP $token_code): $token_body"
    return 1
  fi

  echo "$token"
}

# Check if realm exists
function realm_exists() {
  local realm_name="$1"
  local admin_token="$2"
  local check_url="${keycloak_base_url}/admin/realms/${realm_name}"
  local http_code
  local response_body

  response_body=$(curl -s -w "\n%{http_code}" -X GET "$check_url" \
    -H "Authorization: Bearer $admin_token" 2>&1)
  http_code=$(echo "$response_body" | tail -n1)
  response_body=$(echo "$response_body" | sed '$d')

  if [[ "$http_code" == "200" ]]; then
    return 0  # Realm exists
  elif [[ "$http_code" == "404" ]]; then
    return 1  # Realm does not exist
  else
    echo >&2 "ERROR: Unexpected HTTP code $http_code when checking realm '$realm_name'"
    echo >&2 "Response body: $response_body"
    return 2  # Error
  fi
}

# Import realm
function import_realm() {
  local realm_file="$1"
  local realm_name="$2"
  local admin_token="$3"
  local import_url="${keycloak_base_url}/admin/realms"
  
  # Check if realm already exists
  echo ":: Checking if realm '$realm_name' already exists..."
  if realm_exists "$realm_name" "$admin_token"; then
    echo ":: Realm '$realm_name' already exists. Updating sslRequired=NONE just in case..."
    # Update existing realm to disable SSL requirement for local dev
    curl -s -X PUT "${keycloak_base_url}/admin/realms/${realm_name}" \
      -H "Authorization: Bearer $admin_token" \
      -H 'Content-Type: application/json' \
      -d '{"sslRequired": "NONE"}' >/dev/null || true
    return 0
  fi
  
  # Validate JSON file
  if ! jq empty "$realm_file" >/dev/null 2>&1; then
    echo >&2 "ERROR: Invalid JSON file: $realm_file"
    return 1
  fi
  
  # Import realm
  echo ":: Importing realm '$realm_name' from $realm_file..."
  local http_code
  local response

  response=$(curl -s -w "\n%{http_code}" -X POST "$import_url" \
    -H "Authorization: Bearer $admin_token" \
    -H 'Content-Type: application/json' \
    --data "@$realm_file" 2>&1)
  
  http_code=$(echo "$response" | tail -n1)
  response_body=$(echo "$response" | sed '$d')

  if [[ "$http_code" == "201" ]]; then
    echo ":: Successfully imported realm '$realm_name'"
    # Disable SSL requirement for the newly imported realm
    echo ":: Disabling SSL requirement for realm '$realm_name'..."
    curl -s -X PUT "${keycloak_base_url}/admin/realms/${realm_name}" \
      -H "Authorization: Bearer $admin_token" \
      -H 'Content-Type: application/json' \
      -d '{"sslRequired": "NONE"}' >/dev/null || true
    return 0
  elif [[ "$http_code" == "409" ]]; then
    echo ":: Realm '$realm_name' already exists (409 Conflict). Skipping import."
    return 0
  else
    echo >&2 "ERROR: Failed to import realm '$realm_name'. HTTP code: $http_code"
    echo >&2 "Response: $response_body"
    return 1
  fi
}

# Main import logic
echo ":: Starting realm import process..."

# Get admin token
admin_token=$(get_admin_token)
if [[ -z "$admin_token" ]]; then
  echo >&2 "ERROR: Failed to obtain admin token"
  exit 1
fi

# Extract realm names from JSON files
identity_realm_name=$(jq -r '.realm // empty' "$identity_realm_file" 2>/dev/null)
tenant_realm_name=$(jq -r '.realm // empty' "$tenant_realm_file" 2>/dev/null)

if [[ -z "$identity_realm_name" ]]; then
  echo >&2 "ERROR: Could not extract realm name from identity realm file"
  exit 1
fi

if [[ -z "$tenant_realm_name" ]]; then
  echo >&2 "ERROR: Could not extract realm name from tenant realm file"
  exit 1
fi

# Import identity realm first
echo ":: Importing identity realm..."
if ! import_realm "$identity_realm_file" "$identity_realm_name" "$admin_token"; then
  echo >&2 "ERROR: Failed to import identity realm"
  exit 1
fi

# Import tenant realm second
echo ":: Importing tenant realm..."
if ! import_realm "$tenant_realm_file" "$tenant_realm_name" "$admin_token"; then
  echo >&2 "ERROR: Failed to import tenant realm"
  exit 1
fi

# Import spiffworkflow-local (used by backend default SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS for OpenID discovery)
spiffworkflow_local_realm_name=$(jq -r '.realm // empty' "$spiffworkflow_local_realm_file" 2>/dev/null)
if [[ -n "$spiffworkflow_local_realm_name" ]]; then
  echo ":: Importing spiffworkflow-local realm (backend auth)..."
  if ! import_realm "$spiffworkflow_local_realm_file" "$spiffworkflow_local_realm_name" "$admin_token"; then
    echo >&2 "ERROR: Failed to import spiffworkflow-local realm"
    exit 1
  fi
fi

echo ":: Realm import process completed successfully"
echo ":: Keycloak is running with realms: $identity_realm_name, $tenant_realm_name${spiffworkflow_local_realm_name:+, $spiffworkflow_local_realm_name}"
