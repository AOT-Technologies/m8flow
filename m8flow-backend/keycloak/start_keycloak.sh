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
keycloak_super_admin_user="${KEYCLOAK_SUPER_ADMIN_USER:-super-admin}"
keycloak_super_admin_password="${KEYCLOAK_SUPER_ADMIN_PASSWORD:-super-admin}"
keycloak_master_client_id="${M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID:-m8flow-backend}"
keycloak_master_client_secret="${M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET:-${M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET:-JXeQExm0JhQPLumgHtIIqf52bDalHz0q}}"
backend_public_url="${SPIFFWORKFLOW_BACKEND_URL:-${M8FLOW_BACKEND_URL:-http://localhost:8000}}"
frontend_public_url="${SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND:-${M8FLOW_BACKEND_URL_FOR_FRONTEND:-http://localhost:8001}}"
backend_redirect_uri="${backend_public_url%/}/*"
frontend_logout_redirect_uri="${frontend_public_url%/}/*"
placeholder_client_id="__M8FLOW_SPOKE_CLIENT_ID__"
JQ_FIRST_ID_EXPR='.[0].id // empty'

# Get script directory
script_dir="$(
  cd -- "$(dirname "$0")" >/dev/null 2>&1
  pwd -P
)"

# Realm export file paths
m8flow_tenant_template_file="${script_dir}/realm_exports/m8flow-tenant-template.json"

# Realm Info Mapper JAR (from repo root: keycloak-extensions/realm-info-mapper)
repo_root="$(cd "${script_dir}/../../.." && pwd -P)"
realm_info_mapper_jar="${repo_root}/keycloak-extensions/realm-info-mapper/target/realm-info-mapper.jar"

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
if [[ ! -f "$m8flow_tenant_template_file" ]]; then
  echo >&2 "ERROR: m8flow tenant template file not found: $m8flow_tenant_template_file"
  exit 1
fi

if [[ ! -f "$realm_info_mapper_jar" ]]; then
  echo >&2 "ERROR: Realm Info Mapper JAR not found: $realm_info_mapper_jar"
  echo >&2 "Build it with: (cd ${repo_root}/keycloak-extensions/realm-info-mapper && ./build.sh)"
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

function escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[&|]/\\&/g'
}

function prepare_realm_file_for_import() {
  local source_file="$1"
  local output_file="$2"
  local escaped_client_id
  local escaped_backend_redirect
  local escaped_frontend_redirect

  escaped_client_id="$(escape_sed_replacement "${keycloak_master_client_id}")"
  escaped_backend_redirect="$(escape_sed_replacement "${backend_redirect_uri}")"
  escaped_frontend_redirect="$(escape_sed_replacement "${frontend_logout_redirect_uri}")"

  sed \
    -e "s|__M8FLOW_SPOKE_CLIENT_ID__|${escaped_client_id}|g" \
    -e "s|https://replace-me-with-m8flow-backend-host-and-path/\\*|${escaped_backend_redirect}|g" \
    -e "s|https://replace-me-with-m8flow-frontend-host-and-path/\\*|${escaped_frontend_redirect}|g" \
    "${source_file}" > "${output_file}"
}

function resolve_client_internal_id() {
  local realm_name="$1"
  local client_name="$2"
  docker exec keycloak /opt/keycloak/bin/kcadm.sh get clients -r "${realm_name}" -q clientId="${client_name}" --fields id,clientId 2>/dev/null \
    | jq -r "${JQ_FIRST_ID_EXPR}"
}

function ensure_groups_mapper() {
  local realm_name="$1"
  local client_internal_id="$2"
  if ! docker exec keycloak /opt/keycloak/bin/kcadm.sh get "clients/${client_internal_id}/protocol-mappers/models" -r "${realm_name}" 2>/dev/null | jq -e '.[] | select(.name == "groups")' >/dev/null; then
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create "clients/${client_internal_id}/protocol-mappers/models" -r "${realm_name}" \
      -s name=groups \
      -s protocol=openid-connect \
      -s protocolMapper=oidc-usermodel-realm-role-mapper \
      -s consentRequired=false \
      -s 'config."introspection.token.claim"=true' \
      -s 'config.multivalued=true' \
      -s 'config."userinfo.token.claim"=true' \
      -s 'config."id.token.claim"=true' \
      -s 'config."access.token.claim"=true' \
      -s 'config."claim.name"=groups' \
      -s 'config."jsonType.label"=String' >/dev/null
  fi
}

function ensure_spoke_client_in_realm() {
  local realm_name="$1"

  if ! docker exec keycloak /opt/keycloak/bin/kcadm.sh get "realms/${realm_name}" >/dev/null 2>&1; then
    echo ":: Realm ${realm_name} not present; skipping spoke client reconciliation."
    return 0
  fi

  local current_client_internal_id
  local placeholder_client_internal_id
  current_client_internal_id="$(resolve_client_internal_id "${realm_name}" "${keycloak_master_client_id}")"
  placeholder_client_internal_id="$(resolve_client_internal_id "${realm_name}" "${placeholder_client_id}")"

  if [[ -z "${current_client_internal_id}" && -n "${placeholder_client_internal_id}" ]]; then
    current_client_internal_id="${placeholder_client_internal_id}"
    echo ":: Renaming placeholder client ${placeholder_client_id} to ${keycloak_master_client_id} in realm ${realm_name}."
  elif [[ -z "${current_client_internal_id}" ]]; then
    echo ":: Creating spoke client ${keycloak_master_client_id} in realm ${realm_name}."
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create clients -r "${realm_name}" \
      -s clientId="${keycloak_master_client_id}" \
      -s enabled=true \
      -s publicClient=false \
      -s bearerOnly=false \
      -s secret="${keycloak_master_client_secret}" \
      -s standardFlowEnabled=true \
      -s directAccessGrantsEnabled=true \
      -s serviceAccountsEnabled=true \
      -s authorizationServicesEnabled=true \
      -s fullScopeAllowed=true \
      -s 'defaultClientScopes=["web-origins","acr","profile","roles","email"]' \
      -s 'optionalClientScopes=["address","phone","offline_access","microprofile-jwt"]' \
      -s "redirectUris=[\"${backend_redirect_uri}\"]" \
      -s "webOrigins=[\"${frontend_public_url%/}\"]" \
      -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" >/dev/null
    current_client_internal_id="$(resolve_client_internal_id "${realm_name}" "${keycloak_master_client_id}")"
  fi

  if [[ -z "${current_client_internal_id}" ]]; then
    echo >&2 "ERROR: Failed to resolve realm ${realm_name} client id for ${keycloak_master_client_id}"
    return 1
  fi

  docker exec keycloak /opt/keycloak/bin/kcadm.sh update "clients/${current_client_internal_id}" -r "${realm_name}" \
    -s clientId="${keycloak_master_client_id}" \
    -s enabled=true \
    -s publicClient=false \
    -s bearerOnly=false \
    -s secret="${keycloak_master_client_secret}" \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=true \
    -s serviceAccountsEnabled=true \
    -s authorizationServicesEnabled=true \
    -s fullScopeAllowed=true \
    -s "redirectUris=[\"${backend_redirect_uri}\"]" \
    -s "webOrigins=[\"${frontend_public_url%/}\"]" \
    -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" >/dev/null

  ensure_groups_mapper "${realm_name}" "${current_client_internal_id}"
  echo ":: Realm ${realm_name} client ${keycloak_master_client_id} ensured."
}

# Start Keycloak container
echo ":: Starting Keycloak container..."
if ! docker run \
  -p 7002:8080 \
  -p 7009:9000 \
  -d \
  --network=m8flow \
  --name keycloak \
  -v "${realm_info_mapper_jar}:/opt/keycloak/providers/realm-info-mapper.jar:ro" \
  -e KEYCLOAK_LOGLEVEL=ALL \
  -e ROOT_LOGLEVEL=ALL \
  -e KEYCLOAK_ADMIN="$keycloak_admin_user" \
  -e KEYCLOAK_ADMIN_PASSWORD="$keycloak_admin_password" \
  -e KC_HEALTH_ENABLED="true" \
  quay.io/keycloak/keycloak:${keycloak_version} start-dev \
  -Dkeycloak.profile.feature.token_exchange=enabled \
  -Dkeycloak.profile.feature.admin_fine_grained_authz=enabled \
  --spi-theme-static-max-age=-1 \
  --spi-theme-cache-themes=false \
  --spi-theme-cache-templates=false; then
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

function ensure_master_super_admin() {
  echo ":: Ensuring master realm browser client, super-admin role, and user..."

  local client_id
  client_id=$(docker exec keycloak /opt/keycloak/bin/kcadm.sh get clients -r master -q clientId="${keycloak_master_client_id}" --fields id,clientId 2>/dev/null | jq -r "${JQ_FIRST_ID_EXPR}")

  if [[ -z "$client_id" ]]; then
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create clients -r master \
      -s clientId="${keycloak_master_client_id}" \
      -s enabled=true \
      -s publicClient=false \
      -s bearerOnly=false \
      -s secret="${keycloak_master_client_secret}" \
      -s standardFlowEnabled=true \
      -s directAccessGrantsEnabled=true \
      -s serviceAccountsEnabled=true \
      -s fullScopeAllowed=true \
      -s 'defaultClientScopes=["web-origins","acr","profile","roles","email"]' \
      -s 'optionalClientScopes=["address","phone","offline_access","microprofile-jwt"]' \
      -s "redirectUris=[\"${backend_redirect_uri}\"]" \
      -s "webOrigins=[\"${frontend_public_url%/}\"]" \
      -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" >/dev/null
    client_id=$(docker exec keycloak /opt/keycloak/bin/kcadm.sh get clients -r master -q clientId="${keycloak_master_client_id}" --fields id,clientId 2>/dev/null | jq -r "${JQ_FIRST_ID_EXPR}")
  fi

  if [[ -z "$client_id" ]]; then
    echo >&2 "ERROR: Failed to resolve master realm client id for ${keycloak_master_client_id}"
    return 1
  fi

  docker exec keycloak /opt/keycloak/bin/kcadm.sh update "clients/${client_id}" -r master \
    -s enabled=true \
    -s publicClient=false \
    -s bearerOnly=false \
    -s secret="${keycloak_master_client_secret}" \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=true \
    -s serviceAccountsEnabled=true \
    -s fullScopeAllowed=true \
    -s "redirectUris=[\"${backend_redirect_uri}\"]" \
    -s "webOrigins=[\"${frontend_public_url%/}\"]" \
    -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" >/dev/null

  if ! docker exec keycloak /opt/keycloak/bin/kcadm.sh get "clients/${client_id}/protocol-mappers/models" -r master 2>/dev/null | jq -e '.[] | select(.name == "groups")' >/dev/null; then
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create "clients/${client_id}/protocol-mappers/models" -r master \
      -s name=groups \
      -s protocol=openid-connect \
      -s protocolMapper=oidc-usermodel-realm-role-mapper \
      -s consentRequired=false \
      -s 'config."introspection.token.claim"=true' \
      -s 'config.multivalued=true' \
      -s 'config."userinfo.token.claim"=true' \
      -s 'config."id.token.claim"=true' \
      -s 'config."access.token.claim"=true' \
      -s 'config."claim.name"=groups' \
      -s 'config."jsonType.label"=String' >/dev/null
  fi

  docker exec keycloak /opt/keycloak/bin/kcadm.sh get roles/super-admin -r master >/dev/null 2>&1 \
    || docker exec keycloak /opt/keycloak/bin/kcadm.sh create roles -r master -s name=super-admin >/dev/null

  local user_id
  user_id=$(docker exec keycloak /opt/keycloak/bin/kcadm.sh get users -r master -q username="${keycloak_super_admin_user}" --fields id,username 2>/dev/null | jq -r "${JQ_FIRST_ID_EXPR}")

  if [[ -z "$user_id" ]]; then
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create users -r master \
      -s username="${keycloak_super_admin_user}" \
      -s enabled=true \
      -s firstName="Super" \
      -s lastName="Admin" >/dev/null
    user_id=$(docker exec keycloak /opt/keycloak/bin/kcadm.sh get users -r master -q username="${keycloak_super_admin_user}" --fields id,username 2>/dev/null | jq -r "${JQ_FIRST_ID_EXPR}")
  fi

  if [[ -z "$user_id" ]]; then
    echo >&2 "ERROR: Failed to resolve master realm super-admin user id"
    return 1
  fi

  docker exec keycloak /opt/keycloak/bin/kcadm.sh set-password -r master --username "${keycloak_super_admin_user}" --new-password "${keycloak_super_admin_password}" >/dev/null
  docker exec keycloak /opt/keycloak/bin/kcadm.sh add-roles -r master --uusername "${keycloak_super_admin_user}" --rolename super-admin >/dev/null 2>&1 || true
}

ensure_master_super_admin

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

# Extract realm name from JSON file
m8flow_realm_name=$(jq -r '.realm // empty' "$m8flow_tenant_template_file" 2>/dev/null)

if [[ -z "$m8flow_realm_name" ]]; then
  echo >&2 "ERROR: Could not extract realm name from m8flow realm file"
  exit 1
fi

# Import m8flow realm first
echo ":: Importing m8flow realm..."
processed_m8flow_realm_file="$(mktemp)"
prepare_realm_file_for_import "$m8flow_tenant_template_file" "$processed_m8flow_realm_file"
if ! import_realm "$processed_m8flow_realm_file" "$m8flow_realm_name" "$admin_token"; then
  rm -f "$processed_m8flow_realm_file"
  echo >&2 "ERROR: Failed to import m8flow realm"
  exit 1
fi
rm -f "$processed_m8flow_realm_file"

if ! ensure_spoke_client_in_realm "$m8flow_realm_name"; then
  echo >&2 "ERROR: Failed to ensure client ${keycloak_master_client_id} in realm ${m8flow_realm_name}"
  exit 1
fi

echo ":: Realm import process completed successfully"
echo ":: Keycloak is running with realm: $m8flow_realm_name"
