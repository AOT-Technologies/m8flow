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

# Get admin token
function get_admin_token() {
  local token_url="${keycloak_base_url}/realms/master/protocol/openid-connect/token"
  local token_response
  
  # #region agent log
  echo "{\"sessionId\":\"debug-session\",\"runId\":\"run1\",\"hypothesisId\":\"A\",\"location\":\"start_keycloak.sh:get_admin_token:entry\",\"message\":\"Token request starting\",\"data\":{\"token_url\":\"$token_url\",\"username\":\"$keycloak_admin_user\"},\"timestamp\":$(date +%s%3N)}" >> /Users/aot/Development/AOT/m8Flow/vinaayakh-m8flow/.cursor/debug.log
  # #endregion
  
  echo ":: Obtaining admin access token..." >&2
  token_response=$(curl --fail -s -X POST "$token_url" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "grant_type=password&client_id=admin-cli&username=${keycloak_admin_user}&password=${keycloak_admin_password}" 2>&1)
  local curl_exit_code=$?
  
  # #region agent log
  local response_preview=$(echo "$token_response" | head -c 200)
  echo "{\"sessionId\":\"debug-session\",\"runId\":\"run1\",\"hypothesisId\":\"A\",\"location\":\"start_keycloak.sh:get_admin_token:after_curl\",\"message\":\"Token response received\",\"data\":{\"curl_exit_code\":$curl_exit_code,\"response_preview\":\"$response_preview\"},\"timestamp\":$(date +%s%3N)}" >> /Users/aot/Development/AOT/m8Flow/vinaayakh-m8flow/.cursor/debug.log
  # #endregion
  
  if [[ $curl_exit_code -ne 0 ]]; then
    echo >&2 "ERROR: Failed to obtain admin token. Response: $token_response"
    return 1
  fi
  
  local token=$(echo "$token_response" | jq -r '.access_token // empty' 2>/dev/null)
  local token_preview="${token:0:20}..."
  
  # #region agent log
  echo "{\"sessionId\":\"debug-session\",\"runId\":\"run1\",\"hypothesisId\":\"A\",\"location\":\"start_keycloak.sh:get_admin_token:token_extracted\",\"message\":\"Token extraction result\",\"data\":{\"token_length\":${#token},\"token_preview\":\"$token_preview\",\"is_empty\":$([ -z "$token" ] && echo true || echo false)},\"timestamp\":$(date +%s%3N)}" >> /Users/aot/Development/AOT/m8Flow/vinaayakh-m8flow/.cursor/debug.log
  # #endregion
  
  if [[ -z "$token" || "$token" == "null" ]]; then
    echo >&2 "ERROR: Failed to extract access token from response: $token_response"
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
  
  # #region agent log
  local token_preview="${admin_token:0:20}..."
  echo "{\"sessionId\":\"debug-session\",\"runId\":\"run1\",\"hypothesisId\":\"B\",\"location\":\"start_keycloak.sh:realm_exists:entry\",\"message\":\"Checking realm existence\",\"data\":{\"realm_name\":\"$realm_name\",\"check_url\":\"$check_url\",\"token_preview\":\"$token_preview\"},\"timestamp\":$(date +%s%3N)}" >> /Users/aot/Development/AOT/m8Flow/vinaayakh-m8flow/.cursor/debug.log
  # #endregion
  
  response_body=$(curl -s -w "\n%{http_code}" -X GET "$check_url" \
    -H "Authorization: Bearer $admin_token" 2>&1)
  http_code=$(echo "$response_body" | tail -n1)
  response_body=$(echo "$response_body" | sed '$d')
  
  # #region agent log
  local body_preview=$(echo "$response_body" | head -c 200)
  echo "{\"sessionId\":\"debug-session\",\"runId\":\"run1\",\"hypothesisId\":\"B\",\"location\":\"start_keycloak.sh:realm_exists:after_curl\",\"message\":\"Realm check response\",\"data\":{\"http_code\":\"$http_code\",\"response_body_preview\":\"$body_preview\"},\"timestamp\":$(date +%s%3N)}" >> /Users/aot/Development/AOT/m8Flow/vinaayakh-m8flow/.cursor/debug.log
  # #endregion
  
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
    echo ":: Realm '$realm_name' already exists. Skipping import."
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
  
  # #region agent log
  local token_preview="${admin_token:0:20}..."
  local file_size=$(stat -f%z "$realm_file" 2>/dev/null || stat -c%s "$realm_file" 2>/dev/null || echo "unknown")
  echo "{\"sessionId\":\"debug-session\",\"runId\":\"run1\",\"hypothesisId\":\"C\",\"location\":\"start_keycloak.sh:import_realm:before_curl\",\"message\":\"About to import realm\",\"data\":{\"realm_name\":\"$realm_name\",\"import_url\":\"$import_url\",\"file_size\":\"$file_size\",\"token_preview\":\"$token_preview\"},\"timestamp\":$(date +%s%3N)}" >> /Users/aot/Development/AOT/m8Flow/vinaayakh-m8flow/.cursor/debug.log
  # #endregion
  
  response=$(curl -s -w "\n%{http_code}" -X POST "$import_url" \
    -H "Authorization: Bearer $admin_token" \
    -H 'Content-Type: application/json' \
    --data "@$realm_file" 2>&1)
  
  http_code=$(echo "$response" | tail -n1)
  response_body=$(echo "$response" | sed '$d')
  
  # #region agent log
  local body_preview=$(echo "$response_body" | head -c 500)
  echo "{\"sessionId\":\"debug-session\",\"runId\":\"run1\",\"hypothesisId\":\"C\",\"location\":\"start_keycloak.sh:import_realm:after_curl\",\"message\":\"Import response received\",\"data\":{\"http_code\":\"$http_code\",\"response_body_preview\":\"$body_preview\"},\"timestamp\":$(date +%s%3N)}" >> /Users/aot/Development/AOT/m8Flow/vinaayakh-m8flow/.cursor/debug.log
  # #endregion
  
  if [[ "$http_code" == "201" ]]; then
    echo ":: Successfully imported realm '$realm_name'"
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

echo ":: Realm import process completed successfully"
echo ":: Keycloak is running with realms: $identity_realm_name, $tenant_realm_name"
