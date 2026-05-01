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

keycloak_version=26.6.1
keycloak_base_url="http://localhost:7002"
keycloak_admin_user="admin"
keycloak_admin_password="admin"
keycloak_super_admin_user="${KEYCLOAK_SUPER_ADMIN_USER:-super-admin}"
keycloak_super_admin_password="${KEYCLOAK_SUPER_ADMIN_PASSWORD:-super-admin}"
keycloak_master_realm_name="${M8FLOW_KEYCLOAK_MASTER_REALM:-master}"
keycloak_shared_realm_name="${M8FLOW_KEYCLOAK_SHARED_REALM:-m8flow}"
keycloak_default_organization_alias="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS:-${keycloak_shared_realm_name}}"
keycloak_default_organization_name="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_NAME:-${keycloak_default_organization_alias}}"
keycloak_default_organization_seed_users="admin editor integrator reviewer viewer"
keycloak_master_client_id="${M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID:-m8flow-backend}"
keycloak_master_client_secret="${M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET:-${M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET:-JXeQExm0JhQPLumgHtIIqf52bDalHz0q}}"
backend_public_url="${M8FLOW_BACKEND_URL:-http://localhost:8000}"
frontend_public_url="${M8FLOW_BACKEND_URL_FOR_FRONTEND:-http://localhost:8001}"
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

function prepare_realm_file_for_import() {
  local source_file="$1"
  local output_file="$2"
  local source_realm_name="$3"
  local target_realm_name="$4"
  local default_role_name_old="default-roles-${source_realm_name}"
  local default_role_name_new="default-roles-${target_realm_name}"

  jq \
    --arg source_realm_name "${source_realm_name}" \
    --arg target_realm_name "${target_realm_name}" \
    --arg default_role_name_old "${default_role_name_old}" \
    --arg default_role_name_new "${default_role_name_new}" \
    --arg client_id "${keycloak_master_client_id}" \
    --arg backend_redirect_uri "${backend_redirect_uri}" \
    --arg frontend_logout_redirect_uri "${frontend_logout_redirect_uri}" \
    '
      .realm = $target_realm_name
      | .id = $target_realm_name
      | .roles.realm |= map(
          if (.containerId? == $source_realm_name) then .containerId = $target_realm_name else . end
          | if (.name? == $default_role_name_old) then .name = $default_role_name_new else . end
        )
      | if (.defaultRole | type) == "object" then
          .defaultRole |= (
            if (.containerId? == $source_realm_name) then .containerId = $target_realm_name else . end
            | if (.name? == $default_role_name_old) then .name = $default_role_name_new else . end
          )
        else .
        end
      | .users |= map(
          if (.realmRoles | type) == "array" then
            .realmRoles |= map(if . == $default_role_name_old then $default_role_name_new else . end)
          else .
          end
        )
      | .clients |= map(
          (if (.baseUrl | type) == "string" then
             .baseUrl |= gsub("/realms/" + $source_realm_name + "/"; "/realms/" + $target_realm_name + "/")
               | gsub("/admin/" + $source_realm_name + "/"; "/admin/" + $target_realm_name + "/")
           else .
           end)
          | (if (.adminUrl | type) == "string" then
               .adminUrl |= gsub("/realms/" + $source_realm_name + "/"; "/realms/" + $target_realm_name + "/")
                 | gsub("/admin/" + $source_realm_name + "/"; "/admin/" + $target_realm_name + "/")
             else .
             end)
          | (if (.rootUrl | type) == "string" then
               .rootUrl |= gsub("/realms/" + $source_realm_name + "/"; "/realms/" + $target_realm_name + "/")
                 | gsub("/admin/" + $source_realm_name + "/"; "/admin/" + $target_realm_name + "/")
             else .
             end)
          | (if (.redirectUris | type) == "array" then
               .redirectUris |= map(
                 if type == "string" then
                   gsub("/realms/" + $source_realm_name + "/"; "/realms/" + $target_realm_name + "/")
                   | gsub("/admin/" + $source_realm_name + "/"; "/admin/" + $target_realm_name + "/")
                   | gsub("https://replace-me-with-m8flow-backend-host-and-path/\\*"; $backend_redirect_uri)
                   | gsub("https://replace-me-with-m8flow-frontend-host-and-path/\\*"; $frontend_logout_redirect_uri)
                 else .
                 end
               )
             else .
             end)
          | (if (.webOrigins | type) == "array" then
               .webOrigins |= map(
                 if type == "string" then
                   gsub("/realms/" + $source_realm_name + "/"; "/realms/" + $target_realm_name + "/")
                   | gsub("/admin/" + $source_realm_name + "/"; "/admin/" + $target_realm_name + "/")
                 else .
                 end
               )
             else .
             end)
          | (if (.attributes | type) == "object" then
               .attributes |= with_entries(
                 if (.value | type) == "string" then
                   .value |= gsub("/realms/" + $source_realm_name + "/"; "/realms/" + $target_realm_name + "/")
                     | gsub("/admin/" + $source_realm_name + "/"; "/admin/" + $target_realm_name + "/")
                     | gsub("https://replace-me-with-m8flow-backend-host-and-path/\\*"; $backend_redirect_uri)
                     | gsub("https://replace-me-with-m8flow-frontend-host-and-path/\\*"; $frontend_logout_redirect_uri)
                 else .
                 end
               )
             else .
             end)
        )
      | .users |= map(
          if (.serviceAccountClientId? | type) == "string" then
            .serviceAccountClientId |= gsub("__M8FLOW_SPOKE_CLIENT_ID__"; $client_id)
          else .
          end
          | if (.username? | type) == "string" then
              .username |= gsub("__M8FLOW_SPOKE_CLIENT_ID__"; $client_id)
            else .
            end
          | if (.clientRoles | type) == "object" then
              .clientRoles |= with_entries(.key |= gsub("__M8FLOW_SPOKE_CLIENT_ID__"; $client_id))
            else .
            end
        )
      | .clients |= map(
          if (.clientId? | type) == "string" then
            .clientId |= gsub("__M8FLOW_SPOKE_CLIENT_ID__"; $client_id)
          else .
          end
        )
    ' "${source_file}" > "${output_file}"
}

function resolve_client_internal_id() {
  local realm_name="$1"
  local client_name="$2"
  docker exec keycloak /opt/keycloak/bin/kcadm.sh get clients -r "${realm_name}" -q clientId="${client_name}" --fields id,clientId 2>/dev/null \
    | jq -r "${JQ_FIRST_ID_EXPR}"
}

function resolve_client_scope_internal_id() {
  local realm_name="$1"
  local scope_name="$2"
  docker exec keycloak /opt/keycloak/bin/kcadm.sh get client-scopes -r "${realm_name}" --fields id,name 2>/dev/null \
    | grep -B1 "\"name\" : \"${scope_name}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

function ensure_shared_realm_organization_scope() {
  local realm_name="$1"
  local scope_id

  scope_id="$(resolve_client_scope_internal_id "${realm_name}" "organization")"
  if [[ -z "${scope_id}" ]]; then
    echo ":: Creating built-in organization client scope in realm ${realm_name}."
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create client-scopes -r "${realm_name}" \
      -s name=organization \
      -s protocol=openid-connect \
      -s 'attributes."include.in.token.scope"=true' \
      -s 'attributes."display.on.consent.screen"=false' >/dev/null
    scope_id="$(resolve_client_scope_internal_id "${realm_name}" "organization")"
  fi

  if [[ -z "${scope_id}" ]]; then
    echo >&2 "ERROR: Failed to resolve organization client scope id in realm ${realm_name}"
    return 1
  fi

  if ! docker exec keycloak /opt/keycloak/bin/kcadm.sh get "client-scopes/${scope_id}/protocol-mappers/models" -r "${realm_name}" 2>/dev/null | jq -e '.[] | select(.protocolMapper == "oidc-organization-membership-mapper")' >/dev/null; then
    echo ":: Adding Organization Membership mapper to client scope organization in realm ${realm_name}."
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create "client-scopes/${scope_id}/protocol-mappers/models" -r "${realm_name}" \
      -s name=organization \
      -s protocol=openid-connect \
      -s protocolMapper=oidc-organization-membership-mapper \
      -s consentRequired=false \
      -s 'config."claim.name"=organization' \
      -s 'config."id.token.claim"=true' \
      -s 'config."access.token.claim"=true' \
      -s 'config."userinfo.token.claim"=true' \
      -s 'config."introspection.token.claim"=true' \
      -s 'config.multivalued=true' \
      -s 'config."jsonType.label"=String' >/dev/null
  fi

  echo ":: Realm ${realm_name} organization client scope ensured."
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
  local organization_scope_id
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
      -s 'optionalClientScopes=["organization","address","phone","offline_access","microprofile-jwt"]' \
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
    -s 'optionalClientScopes=["organization","address","phone","offline_access","microprofile-jwt"]' \
    -s "redirectUris=[\"${backend_redirect_uri}\"]" \
    -s "webOrigins=[\"${frontend_public_url%/}\"]" \
    -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" >/dev/null

  organization_scope_id="$(resolve_client_scope_internal_id "${realm_name}" "organization")"
  if [[ -z "${organization_scope_id}" ]]; then
    echo >&2 "ERROR: Failed to resolve organization client scope in realm ${realm_name}"
    return 1
  fi

  docker exec keycloak /opt/keycloak/bin/kcadm.sh update "clients/${current_client_internal_id}/optional-client-scopes/${organization_scope_id}" -r "${realm_name}" -n >/dev/null

  ensure_groups_mapper "${realm_name}" "${current_client_internal_id}"
  echo ":: Realm ${realm_name} client ${keycloak_master_client_id} ensured."
}

function ensure_shared_realm_user_policy() {
  local realm_name="$1"

  echo ":: Enforcing shared-realm organizations and username-only login policy in realm ${realm_name}..."
  docker exec keycloak /opt/keycloak/bin/kcadm.sh update "realms/${realm_name}" \
    -s sslRequired=NONE \
    -s organizationsEnabled=true \
    -s registrationEmailAsUsername=false \
    -s loginWithEmailAllowed=false \
    -s duplicateEmailsAllowed=true >/dev/null
}

function organization_alias_exists() {
  local realm_name="$1"
  local organization_alias="$2"

  [[ -n "${organization_alias}" ]] || return 1

  docker exec keycloak /opt/keycloak/bin/kcadm.sh get organizations -r "${realm_name}" -q search="${organization_alias}" 2>/dev/null \
    | jq -e --arg alias "${organization_alias}" '.[] | select(.alias == $alias)' >/dev/null
}

function resolve_organization_id_by_alias() {
  local realm_name="$1"
  local organization_alias="$2"

  [[ -n "${organization_alias}" ]] || return 1

  docker exec keycloak /opt/keycloak/bin/kcadm.sh get organizations -r "${realm_name}" -q search="${organization_alias}" -q exact=true 2>/dev/null \
    | jq -r --arg alias "${organization_alias}" '.[] | select(.alias == $alias) | .id' \
    | head -n 1
}

function resolve_user_id_by_username() {
  local realm_name="$1"
  local username="$2"

  [[ -n "${username}" ]] || return 1

  docker exec keycloak /opt/keycloak/bin/kcadm.sh get users -r "${realm_name}" -q username="${username}" -q exact=true --fields id,username 2>/dev/null \
    | jq -r --arg username "${username}" '.[] | select(.username == $username) | .id' \
    | head -n 1
}

function organization_has_member() {
  local realm_name="$1"
  local organization_id="$2"
  local username="$3"

  [[ -n "${organization_id}" ]] || return 1
  [[ -n "${username}" ]] || return 1

  docker exec keycloak /opt/keycloak/bin/kcadm.sh get "organizations/${organization_id}/members" -r "${realm_name}" -q search="${username}" -q exact=true -q max=100 2>/dev/null \
    | jq -e --arg username "${username}" '.[] | select(.username == $username)' >/dev/null
}

function add_user_to_organization() {
  local realm_name="$1"
  local organization_id="$2"
  local user_id="$3"
  local payload_file

  payload_file="$(mktemp)"
  printf '"%s"\n' "${user_id}" > "${payload_file}"

  if docker cp "${payload_file}" keycloak:/tmp/m8flow-org-member.json >/dev/null 2>&1 \
    && docker exec keycloak /opt/keycloak/bin/kcadm.sh create "organizations/${organization_id}/members" -r "${realm_name}" -f /tmp/m8flow-org-member.json >/dev/null 2>&1; then
    rm -f "${payload_file}"
    docker exec keycloak rm -f /tmp/m8flow-org-member.json >/dev/null 2>&1 || true
    return 0
  fi

  rm -f "${payload_file}"
  docker exec keycloak rm -f /tmp/m8flow-org-member.json >/dev/null 2>&1 || true
  return 1
}

function ensure_default_organization() {
  local realm_name="$1"

  if [[ -z "${keycloak_default_organization_alias}" ]]; then
    return 0
  fi

  if organization_alias_exists "${realm_name}" "${keycloak_default_organization_alias}"; then
    echo ":: Realm ${realm_name}: default organization ${keycloak_default_organization_alias} already exists."
    return 0
  fi

  docker exec keycloak /opt/keycloak/bin/kcadm.sh create organizations -r "${realm_name}" \
    -s name="${keycloak_default_organization_name}" \
    -s alias="${keycloak_default_organization_alias}" >/dev/null
  echo ":: Realm ${realm_name}: created default organization ${keycloak_default_organization_alias}."
}

function ensure_default_organization_seed_members() {
  local realm_name="$1"
  local organization_id
  local username
  local user_id

  organization_id="$(resolve_organization_id_by_alias "${realm_name}" "${keycloak_default_organization_alias}")"
  if [[ -z "${organization_id}" ]]; then
    echo >&2 "ERROR: Realm ${realm_name}: could not resolve default organization id for ${keycloak_default_organization_alias}"
    return 1
  fi

  for username in ${keycloak_default_organization_seed_users}; do
    user_id="$(resolve_user_id_by_username "${realm_name}" "${username}")"
    if [[ -z "${user_id}" ]]; then
      echo ":: Realm ${realm_name}: seed user ${username} not found; skipping default organization membership."
      continue
    fi

    if organization_has_member "${realm_name}" "${organization_id}" "${username}"; then
      echo ":: Realm ${realm_name}: user ${username} already belongs to organization ${keycloak_default_organization_alias}."
      continue
    fi

    if add_user_to_organization "${realm_name}" "${organization_id}" "${user_id}"; then
      echo ":: Realm ${realm_name}: added user ${username} to organization ${keycloak_default_organization_alias}."
    else
      echo >&2 "ERROR: Realm ${realm_name}: failed to add user ${username} to organization ${keycloak_default_organization_alias}"
      return 1
    fi
  done
}

function resolve_browser_execution_id_by_name() {
  local realm_name="$1"
  local display_name="$2"

  curl -s -X GET "${keycloak_base_url}/admin/realms/${realm_name}/authentication/flows/browser/executions" \
    -H "Authorization: Bearer ${admin_token}" \
    | jq -r --arg display_name "${display_name}" '.[] | select(.displayName == $display_name) | .id' \
    | head -n 1
}

function update_browser_execution_requirement() {
  local realm_name="$1"
  local execution_id="$2"
  local requirement="$3"
  local response
  local http_code
  local response_body

  response=$(curl -s -w "\n%{http_code}" -X PUT "${keycloak_base_url}/admin/realms/${realm_name}/authentication/flows/browser/executions" \
    -H "Authorization: Bearer ${admin_token}" \
    -H 'Content-Type: application/json' \
    -d "{\"id\":\"${execution_id}\",\"requirement\":\"${requirement}\"}" 2>&1)
  http_code=$(echo "$response" | tail -n1)
  response_body=$(echo "$response" | sed '$d')

  if [[ "$http_code" -ge 200 && "$http_code" -lt 300 ]]; then
    return 0
  fi

  echo >&2 "ERROR: Failed to update browser execution ${execution_id} in realm ${realm_name}. HTTP ${http_code}: ${response_body}"
  return 1
}

function disable_shared_realm_identity_first_login() {
  local realm_name="$1"
  local display_name
  local execution_id

  for display_name in "Organization" "Organization Identity-First Login"; do
    execution_id="$(resolve_browser_execution_id_by_name "${realm_name}" "${display_name}")"
    if [[ -z "${execution_id}" ]]; then
      echo ":: Realm ${realm_name}: browser execution '${display_name}' not found; nothing to disable."
      continue
    fi

    if update_browser_execution_requirement "${realm_name}" "${execution_id}" "DISABLED"; then
      echo ":: Realm ${realm_name}: browser execution '${display_name}' disabled."
    else
      return 1
    fi
  done
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
  -e KC_FEATURES="organization,token-exchange,admin-fine-grained-authz" \
  quay.io/keycloak/keycloak:${keycloak_version} start-dev \
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

function ensure_admin_realm_exists() {
  local realm_name="$1"
  if [[ "$realm_name" == "master" ]]; then
    return 0
  fi

  if docker exec keycloak /opt/keycloak/bin/kcadm.sh get "realms/${realm_name}" >/dev/null 2>&1; then
    docker exec keycloak /opt/keycloak/bin/kcadm.sh update "realms/${realm_name}" -s sslRequired=NONE >/dev/null 2>&1 || true
    return 0
  fi

  echo ":: Creating admin realm ${realm_name}..."
  docker exec keycloak /opt/keycloak/bin/kcadm.sh create realms \
    -s realm="${realm_name}" \
    -s enabled=true \
    -s sslRequired=NONE >/dev/null
}

function ensure_master_super_admin() {
  local admin_realm_name="${keycloak_master_realm_name}"
  echo ":: Ensuring admin realm ${admin_realm_name} browser client, super-admin role, and user..."

  ensure_admin_realm_exists "${admin_realm_name}"

  local client_id
  client_id=$(docker exec keycloak /opt/keycloak/bin/kcadm.sh get clients -r "${admin_realm_name}" -q clientId="${keycloak_master_client_id}" --fields id,clientId 2>/dev/null | jq -r "${JQ_FIRST_ID_EXPR}")

  if [[ -z "$client_id" ]]; then
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create clients -r "${admin_realm_name}" \
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
    client_id=$(docker exec keycloak /opt/keycloak/bin/kcadm.sh get clients -r "${admin_realm_name}" -q clientId="${keycloak_master_client_id}" --fields id,clientId 2>/dev/null | jq -r "${JQ_FIRST_ID_EXPR}")
  fi

  if [[ -z "$client_id" ]]; then
    echo >&2 "ERROR: Failed to resolve admin realm ${admin_realm_name} client id for ${keycloak_master_client_id}"
    return 1
  fi

  docker exec keycloak /opt/keycloak/bin/kcadm.sh update "clients/${client_id}" -r "${admin_realm_name}" \
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

  if ! docker exec keycloak /opt/keycloak/bin/kcadm.sh get "clients/${client_id}/protocol-mappers/models" -r "${admin_realm_name}" 2>/dev/null | jq -e '.[] | select(.name == "groups")' >/dev/null; then
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create "clients/${client_id}/protocol-mappers/models" -r "${admin_realm_name}" \
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

  docker exec keycloak /opt/keycloak/bin/kcadm.sh get roles/super-admin -r "${admin_realm_name}" >/dev/null 2>&1 \
    || docker exec keycloak /opt/keycloak/bin/kcadm.sh create roles -r "${admin_realm_name}" -s name=super-admin >/dev/null

  local user_id
  user_id=$(docker exec keycloak /opt/keycloak/bin/kcadm.sh get users -r "${admin_realm_name}" -q username="${keycloak_super_admin_user}" --fields id,username 2>/dev/null | jq -r "${JQ_FIRST_ID_EXPR}")

  if [[ -z "$user_id" ]]; then
    docker exec keycloak /opt/keycloak/bin/kcadm.sh create users -r "${admin_realm_name}" \
      -s username="${keycloak_super_admin_user}" \
      -s enabled=true \
      -s firstName="Super" \
      -s lastName="Admin" >/dev/null
    user_id=$(docker exec keycloak /opt/keycloak/bin/kcadm.sh get users -r "${admin_realm_name}" -q username="${keycloak_super_admin_user}" --fields id,username 2>/dev/null | jq -r "${JQ_FIRST_ID_EXPR}")
  fi

  if [[ -z "$user_id" ]]; then
    echo >&2 "ERROR: Failed to resolve admin realm ${admin_realm_name} super-admin user id"
    return 1
  fi

  docker exec keycloak /opt/keycloak/bin/kcadm.sh set-password -r "${admin_realm_name}" --username "${keycloak_super_admin_user}" --new-password "${keycloak_super_admin_password}" >/dev/null
  docker exec keycloak /opt/keycloak/bin/kcadm.sh add-roles -r "${admin_realm_name}" --uusername "${keycloak_super_admin_user}" --rolename super-admin >/dev/null 2>&1 || true
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
m8flow_template_realm_name=$(jq -r '.realm // empty' "$m8flow_tenant_template_file" 2>/dev/null)

if [[ -z "$m8flow_template_realm_name" ]]; then
  echo >&2 "ERROR: Could not extract realm name from m8flow realm file"
  exit 1
fi

# Import shared realm first
echo ":: Importing shared realm ${keycloak_shared_realm_name}..."
processed_m8flow_realm_file="$(mktemp)"
prepare_realm_file_for_import "$m8flow_tenant_template_file" "$processed_m8flow_realm_file" "$m8flow_template_realm_name" "$keycloak_shared_realm_name"
if ! import_realm "$processed_m8flow_realm_file" "$keycloak_shared_realm_name" "$admin_token"; then
  rm -f "$processed_m8flow_realm_file"
  echo >&2 "ERROR: Failed to import shared realm ${keycloak_shared_realm_name}"
  exit 1
fi
rm -f "$processed_m8flow_realm_file"

if ! ensure_shared_realm_organization_scope "$keycloak_shared_realm_name"; then
  echo >&2 "ERROR: Failed to ensure organization client scope in realm ${keycloak_shared_realm_name}"
  exit 1
fi

if ! ensure_spoke_client_in_realm "$keycloak_shared_realm_name"; then
  echo >&2 "ERROR: Failed to ensure client ${keycloak_master_client_id} in realm ${keycloak_shared_realm_name}"
  exit 1
fi

if ! ensure_shared_realm_user_policy "$keycloak_shared_realm_name"; then
  echo >&2 "ERROR: Failed to enforce user policy in realm ${keycloak_shared_realm_name}"
  exit 1
fi

if ! ensure_default_organization "$keycloak_shared_realm_name"; then
  echo >&2 "ERROR: Failed to ensure default organization in realm ${keycloak_shared_realm_name}"
  exit 1
fi

if ! ensure_default_organization_seed_members "$keycloak_shared_realm_name"; then
  echo >&2 "ERROR: Failed to ensure default organization members in realm ${keycloak_shared_realm_name}"
  exit 1
fi

if ! disable_shared_realm_identity_first_login "$keycloak_shared_realm_name"; then
  echo >&2 "ERROR: Failed to disable identity-first browser login in realm ${keycloak_shared_realm_name}"
  exit 1
fi

echo ":: Realm import process completed successfully"
echo ":: Keycloak is running with shared realm: ${keycloak_shared_realm_name} and admin realm: ${keycloak_master_realm_name}"
