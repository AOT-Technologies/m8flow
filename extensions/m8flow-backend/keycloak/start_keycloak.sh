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
# Backend default auth uses spiffworkflow-local; must exist and have sslRequired=NONE for HTTP
spiffworkflow_local_realm_file="${script_dir}/realm_exports/spiffworkflow-local-realm.json"

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
if [[ ! -f "$identity_realm_file" ]]; then
  echo >&2 "ERROR: Identity realm export file not found: $identity_realm_file"
  exit 1
fi

if [[ ! -f "$spiffworkflow_local_realm_file" ]]; then
  echo >&2 "ERROR: Spiffworkflow-local realm export file not found: $spiffworkflow_local_realm_file"
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

# Create realm from template (mimicking keycloak_service.py)
function create_realm_from_template() {
  local template_file="$1"
  local realm_id="$2"
  local display_name="$3"
  local admin_token="$4"
  local template_name
  
  template_name=$(jq -r '.realm // empty' "$template_file" 2>/dev/null)
  
  echo ":: Creating realm '$realm_id' from template '$template_name'..."

  # Step 0: Fill template using jq (Mimicking keycloak_service.py _fill_realm_template)
  local full_payload
  full_payload=$(jq --arg realm_id "$realm_id" \
     --arg display_name "$display_name" \
     --arg template_name "$template_name" \
     '
    .realm = $realm_id |
    .id = $realm_id |
    .displayName = $display_name |
    # Update realm roles containerId and names
    (if .roles.realm then .roles.realm[] |= (if .containerId == $template_name then .containerId = $realm_id else . end | if .name | startswith("default-roles-") then .name = ("default-roles-" + $realm_id) else . end) else . end) |
    # Update defaultRole
    (if .defaultRole then
      (if .defaultRole.containerId == $template_name then .defaultRole.containerId = $realm_id else . end) |
      (if .defaultRole.name | startswith("default-roles-") then .defaultRole.name = ("default-roles-" + $realm_id) else . end)
    else . end) |
    # Update clients URLs and attributes
    (if .clients then .clients[] |= (
      (if .baseUrl then .baseUrl |= sub("/realms/" + $template_name + "/"; "/realms/" + $realm_id + "/") else . end) |
      (if .rootUrl then .rootUrl |= sub("/realms/" + $template_name + "/"; "/realms/" + $realm_id + "/") else . end) |
      (if .adminUrl then .adminUrl |= sub("/realms/" + $template_name + "/"; "/realms/" + $realm_id + "/") else . end) |
      (if .redirectUris then .redirectUris[] |= sub("/realms/" + $template_name + "/"; "/realms/" + $realm_id + "/") else . end) |
      (if .attributes."post.logout.redirect.uris" then .attributes."post.logout.redirect.uris" |= sub("/realms/" + $template_name + "/"; "/realms/" + $realm_id + "/") else . end)
    ) else . end) |
    # Update users realm roles
    (if .users then .users[] |= (if .realmRoles then .realmRoles[] |= sub("^default-roles-" + $template_name + "$"; "default-roles-" + $realm_id) else . end) else . end)
  ' "$template_file")

  # Step 1: Create minimal realm
  local minimal_payload
  minimal_payload=$(echo "$full_payload" | jq '{realm: .realm, displayName: .displayName, enabled: (.enabled // true), sslRequired: (.sslRequired // "none")}')
  
  local create_url="${keycloak_base_url}/admin/realms"
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$create_url" \
    -H "Authorization: Bearer $admin_token" \
    -H 'Content-Type: application/json' \
    -d "$minimal_payload")
    
  if [[ "$http_code" == "201" || "$http_code" == "409" ]]; then
    echo ":: Minimal realm '$realm_id' created or already exists ($http_code)"
  else
    echo >&2 "ERROR: Failed to create minimal realm '$realm_id' (HTTP $http_code)"
    return 1
  fi

  # Step 2: Partial Import (mimicking keycloak_service.py sanitization)
  local partial_import_payload
  partial_import_payload=$(echo "$full_payload" | jq '
    # Sanitization
    (if .roles.realm then .roles.realm[] |= del(.id) else . end) |
    (if .roles.client then .roles.client |= map_values(.[] |= del(.id)) else . end) |
    (if .groups then .groups[] |= (del(.id) | (if .subGroups then .subGroups[] |= del(.id) else . end)) else . end) |
    (if .users then .users[] |= (del(.id, .createdTimestamp) | (if .credentials then .credentials[] |= del(.id, .createdDate) else . end)) else . end) |
    (if .clientScopes then .clientScopes[] |= del(.id) else . end) |
    (if .identityProviders then .identityProviders[] |= del(.internalId) else . end) |
    (if .clients then .clients[] |= (del(.id) | (if .protocolMappers then .protocolMappers[] |= del(.id) else . end)) else . end) |
    
    {
      ifResourceExists: "SKIP",
      clients: .clients,
      clientScopes: .clientScopes,
      defaultDefaultClientScopes: .defaultDefaultClientScopes,
      defaultOptionalClientScopes: .defaultOptionalClientScopes,
      identityProviders: .identityProviders,
      roles: .roles,
      groups: .groups,
      users: .users,
      realmRoles: .realmRoles,
      clientRoles: .clientRoles,
      themes: .themes,
      emailThemes: .emailThemes,
      smtpServer: .smtpServer,
      bruteForceConfig: .bruteForceConfig,
      tokenPolicies: .tokenPolicies,
      oauth2DeviceConfig: .oauth2DeviceConfig,
      otpPolicy: .otpPolicy,
      webAuthnPolicy: .webAuthnPolicy,
      passwordPolicy: .passwordPolicy,
      internationalization: .internationalization,
      accountTheme: .accountTheme,
      accountThemeText: .accountThemeText,
      loginTheme: .loginTheme,
      loginThemeText: .loginThemeText,
      adminTheme: .adminTheme,
      adminThemeText: .adminThemeText,
      emailTheme: .emailTheme,
      emailThemeText: .emailThemeText,
      masterRealmAdminTheme: .masterRealmAdminTheme,
      masterRealmAdminThemeText: .masterRealmAdminThemeText,
      masterRealmLoginTheme: .masterRealmLoginTheme,
      masterRealmLoginThemeText: .masterRealmLoginThemeText,
      masterRealmEmailTheme: .masterRealmEmailTheme,
      masterRealmEmailThemeText: .masterRealmEmailThemeText
    } | with_entries(select(.value != null))
  ')
  
  local import_url="${keycloak_base_url}/admin/realms/${realm_id}/partialImport"
  http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$import_url" \
    -H "Authorization: Bearer $admin_token" \
    -H 'Content-Type: application/json' \
    -d "$partial_import_payload")
    
  if [[ "$http_code" == "200" || "$http_code" == "201" || "$http_code" == "204" ]]; then
    echo ":: Partial import for realm '$realm_id' successful ($http_code)"
  else
    echo >&2 "ERROR: Partial import for realm '$realm_id' failed (HTTP $http_code)"
  fi

  # Final cleanup: ensure sslRequired=NONE
  curl -s -X PUT "${keycloak_base_url}/admin/realms/${realm_id}" \
    -H "Authorization: Bearer $admin_token" \
    -H 'Content-Type: application/json' \
    -d '{"sslRequired": "NONE"}' >/dev/null || true
    
  return 0
}

# Main import logic
echo ":: Starting realm import process..."

# Get admin token
admin_token=$(get_admin_token)
if [[ -z "$admin_token" ]]; then
  echo >&2 "ERROR: Failed to obtain admin token"
  exit 1
fi

# Extract realm names from JSON files (tenant-a is created from template, not from a file)
identity_realm_name=$(jq -r '.realm // empty' "$identity_realm_file" 2>/dev/null)
tenant_realm_name="tenant-a"

if [[ -z "$identity_realm_name" ]]; then
  echo >&2 "ERROR: Could not extract realm name from identity realm file"
  exit 1
fi

# Import identity realm first
echo ":: Importing identity realm..."
if ! import_realm "$identity_realm_file" "$identity_realm_name" "$admin_token"; then
  echo >&2 "ERROR: Failed to import identity realm"
  exit 1
fi

# Create tenant-a from spiffworkflow-local template (following API format)
echo ":: Creating tenant-a from template..."
if ! create_realm_from_template "$spiffworkflow_local_realm_file" "tenant-a" "Tenant A" "$admin_token"; then
  echo >&2 "ERROR: Failed to create tenant-a from template"
  exit 1
fi

echo ":: Realm import process completed successfully"
echo ":: Keycloak is running with realms: $identity_realm_name, $tenant_realm_name"
