#!/usr/bin/env bash
# Create bootstrap admin user before first start (avoids "Local access required" behind proxy).
# Start Keycloak, then set sslRequired=NONE on realms for HTTP access (e.g. behind a reverse proxy without HTTPS termination at Keycloak).
set -e

BOOTSTRAP_USER="${KC_BOOTSTRAP_ADMIN_USERNAME:-admin}"
M8FLOW_REALM_IMPORT_FILE="/opt/keycloak/data/import/m8flow-tenant-template.json"
M8FLOW_TEMPLATE_REALM_NAME="m8flow"
M8FLOW_REALM_NAME="${M8FLOW_KEYCLOAK_SHARED_REALM:-${KEYCLOAK_REALM:-${M8FLOW_TEMPLATE_REALM_NAME}}}"
M8FLOW_DEFAULT_ORGANIZATION_ALIAS="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS:-${M8FLOW_REALM_NAME}}"
M8FLOW_DEFAULT_ORGANIZATION_NAME="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_NAME:-${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}}"
M8FLOW_DEFAULT_ORGANIZATION_SEED_USERS="admin editor integrator reviewer viewer"
M8FLOW_SPOKE_CLIENT_ID="${M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID:-m8flow-backend}"
M8FLOW_SPOKE_CLIENT_SECRET="${M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET:-${M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET:-JXeQExm0JhQPLumgHtIIqf52bDalHz0q}}"
BACKEND_PUBLIC_URL="${M8FLOW_BACKEND_URL:-http://localhost:7000}"
FRONTEND_PUBLIC_URL="${M8FLOW_BACKEND_URL_FOR_FRONTEND:-http://localhost:7001}"
BACKEND_REDIRECT_URI="${BACKEND_PUBLIC_URL%/}/*"
FRONTEND_LOGOUT_REDIRECT_URI="${FRONTEND_PUBLIC_URL%/}/*"

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[&|]/\\&/g'
}

prepare_m8flow_realm_import() {
  if [ ! -f "${M8FLOW_REALM_IMPORT_FILE}" ]; then
    return
  fi

  local escaped_client_id
  local escaped_backend_redirect
  local escaped_frontend_redirect
  local escaped_realm_name

  escaped_client_id="$(escape_sed_replacement "${M8FLOW_SPOKE_CLIENT_ID}")"
  escaped_backend_redirect="$(escape_sed_replacement "${BACKEND_REDIRECT_URI}")"
  escaped_frontend_redirect="$(escape_sed_replacement "${FRONTEND_LOGOUT_REDIRECT_URI}")"
  escaped_realm_name="$(escape_sed_replacement "${M8FLOW_REALM_NAME}")"

  sed -i \
    -e "0,/^  \"id\": \"${M8FLOW_TEMPLATE_REALM_NAME}\",$/s//  \"id\": \"${escaped_realm_name}\",/" \
    -e "s|\"realm\": \"${M8FLOW_TEMPLATE_REALM_NAME}\"|\"realm\": \"${escaped_realm_name}\"|" \
    -e "s|\"containerId\": \"${M8FLOW_TEMPLATE_REALM_NAME}\"|\"containerId\": \"${escaped_realm_name}\"|g" \
    -e "s|default-roles-${M8FLOW_TEMPLATE_REALM_NAME}|default-roles-${escaped_realm_name}|g" \
    -e "s|/realms/${M8FLOW_TEMPLATE_REALM_NAME}/|/realms/${escaped_realm_name}/|g" \
    -e "s|/admin/${M8FLOW_TEMPLATE_REALM_NAME}/|/admin/${escaped_realm_name}/|g" \
    -e "s|__M8FLOW_SPOKE_CLIENT_ID__|${escaped_client_id}|g" \
    -e "s|https://replace-me-with-m8flow-backend-host-and-path/\\*|${escaped_backend_redirect}|g" \
    -e "s|https://replace-me-with-m8flow-frontend-host-and-path/\\*|${escaped_frontend_redirect}|g" \
    "${M8FLOW_REALM_IMPORT_FILE}"

  echo "[keycloak-entrypoint] Prepared ${M8FLOW_REALM_NAME} realm import for client ${M8FLOW_SPOKE_CLIENT_ID}."
}

resolve_client_internal_id() {
  local realm_name="$1"
  local client_name="$2"

  /opt/keycloak/bin/kcadm.sh get clients -r "${realm_name}" -q clientId="${client_name}" --fields id,clientId \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

resolve_client_scope_internal_id() {
  local realm_name="$1"
  local scope_name="$2"

  /opt/keycloak/bin/kcadm.sh get client-scopes -r "${realm_name}" --fields id,name \
    | grep -B1 "\"name\" : \"${scope_name}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

ensure_shared_realm_organization_scope() {
  local scope_id

  scope_id="$(resolve_client_scope_internal_id "${M8FLOW_REALM_NAME}" "organization")"
  if [ -z "${scope_id}" ]; then
    if /opt/keycloak/bin/kcadm.sh create client-scopes -r "${M8FLOW_REALM_NAME}" \
      -s name=organization \
      -s protocol=openid-connect \
      -s 'attributes."include.in.token.scope"=true' \
      -s 'attributes."display.on.consent.screen"=false' >/dev/null 2>&1; then
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: created organization client scope."
      scope_id="$(resolve_client_scope_internal_id "${M8FLOW_REALM_NAME}" "organization")"
    else
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: failed to create organization client scope." >&2
      return 1
    fi
  fi

  if [ -z "${scope_id}" ]; then
    echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: could not resolve organization client scope id." >&2
    return 1
  fi

  if ! /opt/keycloak/bin/kcadm.sh get "client-scopes/${scope_id}/protocol-mappers/models" -r "${M8FLOW_REALM_NAME}" 2>/dev/null | grep -q 'oidc-organization-membership-mapper'; then
    if /opt/keycloak/bin/kcadm.sh create "client-scopes/${scope_id}/protocol-mappers/models" -r "${M8FLOW_REALM_NAME}" \
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
      -s 'config."jsonType.label"=String' >/dev/null 2>&1; then
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: organization membership mapper ensured."
    else
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: failed to create organization membership mapper." >&2
      return 1
    fi
  fi
}

ensure_shared_realm_spoke_client_scope() {
  if ! ensure_shared_realm_organization_scope; then
    return 1
  fi

  local client_internal_id
  local scope_id

  client_internal_id="$(resolve_client_internal_id "${M8FLOW_REALM_NAME}" "${M8FLOW_SPOKE_CLIENT_ID}")"
  if [ -z "${client_internal_id}" ]; then
    echo "[keycloak-entrypoint] Client ${M8FLOW_SPOKE_CLIENT_ID} not found in realm ${M8FLOW_REALM_NAME}; skipping organization scope reconciliation." >&2
    return 0
  fi

  scope_id="$(resolve_client_scope_internal_id "${M8FLOW_REALM_NAME}" "organization")"
  if [ -z "${scope_id}" ]; then
    echo "[keycloak-entrypoint] Client ${M8FLOW_SPOKE_CLIENT_ID}: organization client scope id could not be resolved." >&2
    return 1
  fi

  if /opt/keycloak/bin/kcadm.sh update "clients/${client_internal_id}/optional-client-scopes/${scope_id}" -r "${M8FLOW_REALM_NAME}" -n >/dev/null 2>&1; then
    echo "[keycloak-entrypoint] Client ${M8FLOW_SPOKE_CLIENT_ID}: organization optional scope ensured."
  else
    echo "[keycloak-entrypoint] Client ${M8FLOW_SPOKE_CLIENT_ID}: failed to ensure organization optional scope." >&2
    return 1
  fi
}

organization_alias_exists() {
  local realm_name="$1"
  local organization_alias="$2"

  [ -n "${organization_alias}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get organizations -r "${realm_name}" -q search="${organization_alias}" 2>/dev/null \
    | grep -q "\"alias\" : \"${organization_alias}\""
}

resolve_organization_id_by_alias() {
  local realm_name="$1"
  local organization_alias="$2"

  [ -n "${organization_alias}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get organizations -r "${realm_name}" -q search="${organization_alias}" -q exact=true 2>/dev/null \
    | grep -B3 "\"alias\" : \"${organization_alias}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

resolve_user_id_by_username() {
  local realm_name="$1"
  local username="$2"

  [ -n "${username}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get users -r "${realm_name}" -q username="${username}" -q exact=true --fields id,username 2>/dev/null \
    | grep -B2 "\"username\" : \"${username}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

organization_has_member() {
  local realm_name="$1"
  local organization_id="$2"
  local username="$3"

  [ -n "${organization_id}" ] || return 1
  [ -n "${username}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get "organizations/${organization_id}/members" -r "${realm_name}" -q search="${username}" -q exact=true -q max=100 2>/dev/null \
    | grep -q "\"username\" : \"${username}\""
}

add_user_to_organization() {
  local realm_name="$1"
  local organization_id="$2"
  local user_id="$3"
  local payload_file

  payload_file="$(mktemp)"
  printf '"%s"\n' "${user_id}" > "${payload_file}"

  if /opt/keycloak/bin/kcadm.sh create "organizations/${organization_id}/members" -r "${realm_name}" -f "${payload_file}" >/dev/null 2>&1; then
    rm -f "${payload_file}"
    return 0
  fi

  rm -f "${payload_file}"
  return 1
}

ensure_default_organization() {
  if [ -z "${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}" ]; then
    return 0
  fi

  if organization_alias_exists "${M8FLOW_REALM_NAME}" "${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}"; then
    echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: default organization ${M8FLOW_DEFAULT_ORGANIZATION_ALIAS} already exists."
    return 0
  fi

  if /opt/keycloak/bin/kcadm.sh create organizations -r "${M8FLOW_REALM_NAME}" \
    -s name="${M8FLOW_DEFAULT_ORGANIZATION_NAME}" \
    -s alias="${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}" >/dev/null 2>&1; then
    echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: created default organization ${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}."
    return 0
  fi

  echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: failed to create default organization ${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}." >&2
  return 1
}

ensure_default_organization_seed_members() {
  local organization_id
  local username
  local user_id

  organization_id="$(resolve_organization_id_by_alias "${M8FLOW_REALM_NAME}" "${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}")"
  if [ -z "${organization_id}" ]; then
    echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: could not resolve default organization id for ${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}." >&2
    return 1
  fi

  for username in ${M8FLOW_DEFAULT_ORGANIZATION_SEED_USERS}; do
    user_id="$(resolve_user_id_by_username "${M8FLOW_REALM_NAME}" "${username}")"
    if [ -z "${user_id}" ]; then
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: seed user ${username} not found; skipping default organization membership."
      continue
    fi

    if organization_has_member "${M8FLOW_REALM_NAME}" "${organization_id}" "${username}"; then
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: user ${username} already belongs to organization ${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}."
      continue
    fi

    if add_user_to_organization "${M8FLOW_REALM_NAME}" "${organization_id}" "${user_id}"; then
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: added user ${username} to organization ${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}."
    else
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: failed to add user ${username} to organization ${M8FLOW_DEFAULT_ORGANIZATION_ALIAS}." >&2
      return 1
    fi
  done
}

resolve_browser_execution_id_by_name() {
  local realm_name="$1"
  local display_name="$2"

  /opt/keycloak/bin/kcadm.sh get authentication/flows/browser/executions -r "${realm_name}" 2>/dev/null \
    | grep -B4 "\"displayName\" : \"${display_name}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | tail -n 1
}

update_browser_execution_requirement() {
  local realm_name="$1"
  local execution_id="$2"
  local requirement="$3"
  local payload_file

  payload_file="$(mktemp)"
  cat > "${payload_file}" <<EOF
{
  "id": "${execution_id}",
  "requirement": "${requirement}"
}
EOF

  if /opt/keycloak/bin/kcadm.sh update authentication/flows/browser/executions -r "${realm_name}" -f "${payload_file}" >/dev/null 2>&1; then
    rm -f "${payload_file}"
    return 0
  fi

  rm -f "${payload_file}"
  return 1
}

disable_shared_realm_identity_first_login() {
  local display_name
  local execution_id

  for display_name in "Organization" "Organization Identity-First Login"; do
    execution_id="$(resolve_browser_execution_id_by_name "${M8FLOW_REALM_NAME}" "${display_name}")"
    if [ -z "${execution_id}" ]; then
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: browser execution '${display_name}' not found; nothing to disable."
      continue
    fi

    if update_browser_execution_requirement "${M8FLOW_REALM_NAME}" "${execution_id}" "DISABLED"; then
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: browser execution '${display_name}' disabled."
    else
      echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: failed to disable browser execution '${display_name}'." >&2
      return 1
    fi
  done
}

echo "[keycloak-entrypoint] Running bootstrap-admin user..."
if /opt/keycloak/bin/kc.sh bootstrap-admin user \
  --username "${BOOTSTRAP_USER}" \
  --password:env KC_BOOTSTRAP_ADMIN_PASSWORD \
  --no-prompt 2>/dev/null; then
  echo "[keycloak-entrypoint] Bootstrap-admin succeeded (master realm and admin created or already exist)."
else
  echo "[keycloak-entrypoint] Bootstrap-admin skipped or failed (non-fatal; master may already exist)."
fi

prepare_m8flow_realm_import

# Start Keycloak in background so we can run kcadm to set sslRequired=NONE after it is ready
echo "[keycloak-entrypoint] Starting Keycloak in background..."
/opt/keycloak/bin/kc.sh "$@" &
KC_PID=$!

# Admin API base URL: must include KC_HTTP_RELATIVE_PATH when set (e.g. /auth behind a proxy)
KC_PORT="${KC_HTTP_PORT:-8080}"
KC_PATH="${KC_HTTP_RELATIVE_PATH:-}"
BASE="http://127.0.0.1:${KC_PORT}${KC_PATH}"
USER="${BOOTSTRAP_USER}"
PASS="${KC_BOOTSTRAP_ADMIN_PASSWORD:-admin}"
TIMEOUT=180
ELAPSED=0
echo "[keycloak-entrypoint] Waiting for Keycloak admin API at ${BASE} (up to ${TIMEOUT}s)..."
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  if /opt/keycloak/bin/kcadm.sh config credentials --server "$BASE" --realm master \
    --user "$USER" --password "$PASS" >/dev/null 2>&1; then
    echo "[keycloak-entrypoint] Keycloak admin API ready after ${ELAPSED}s."
    break
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done
if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
  echo "[keycloak-entrypoint] WARNING: Keycloak did not become ready within ${TIMEOUT}s; skipping realm sslRequired=NONE updates." >&2
else
  # Assign master realm 'admin' role to bootstrap user so partialImport (and other manage-realm ops) are allowed
  if /opt/keycloak/bin/kcadm.sh add-roles -r master --rolename admin --uusername "$USER" 2>/dev/null; then
    echo "[keycloak-entrypoint] Assigned master realm admin role to user ${USER}."
  else
    echo "[keycloak-entrypoint] add-roles skipped or failed (user may already have admin role)." >&2
  fi

  # Create permanent admin user with full privileges (idempotent: create may fail if user exists)
  SUPERADMIN_USER="${KEYCLOAK_SUPER_ADMIN_USER:-super-admin}"
  SUPERADMIN_PASS="${KEYCLOAK_SUPER_ADMIN_PASSWORD:-super-admin}"
  if /opt/keycloak/bin/kcadm.sh create users -r master -s username="${SUPERADMIN_USER}" -s enabled=true 2>/dev/null; then
    echo "[keycloak-entrypoint] Created permanent admin user ${SUPERADMIN_USER}."
  else
    echo "[keycloak-entrypoint] Create user ${SUPERADMIN_USER} skipped (may already exist)." >&2
  fi
  if /opt/keycloak/bin/kcadm.sh set-password -r master --username "${SUPERADMIN_USER}" --new-password "${SUPERADMIN_PASS}" 2>/dev/null; then
    echo "[keycloak-entrypoint] Set password for ${SUPERADMIN_USER}."
  else
    echo "[keycloak-entrypoint] set-password for ${SUPERADMIN_USER} skipped or failed." >&2
  fi
  # Grant full access for realm creation and partial import: master realm 'admin' and 'create-realm'
  if /opt/keycloak/bin/kcadm.sh add-roles -r master --uusername "${SUPERADMIN_USER}" --rolename admin 2>/dev/null; then
    echo "[keycloak-entrypoint] Assigned realm role admin to ${SUPERADMIN_USER}."
  else
    echo "[keycloak-entrypoint] add-roles (admin) for ${SUPERADMIN_USER} skipped or failed." >&2
  fi
  if /opt/keycloak/bin/kcadm.sh add-roles -r master --uusername "${SUPERADMIN_USER}" --rolename create-realm 2>/dev/null; then
    echo "[keycloak-entrypoint] Assigned realm role create-realm to ${SUPERADMIN_USER}."
  else
    echo "[keycloak-entrypoint] add-roles (create-realm) for ${SUPERADMIN_USER} skipped or failed." >&2
  fi

  echo "[keycloak-entrypoint] Setting sslRequired=NONE and loginTheme=m8flow on realms master, ${M8FLOW_REALM_NAME}..."
  for realm in master "${M8FLOW_REALM_NAME}"; do
    if /opt/keycloak/bin/kcadm.sh update realms/${realm} -s sslRequired=NONE -s loginTheme=m8flow 2>/dev/null; then
      echo "[keycloak-entrypoint] Realm ${realm}: sslRequired=NONE and loginTheme=m8flow set successfully."
    else
      echo "[keycloak-entrypoint] Realm ${realm}: update skipped or failed (realm may not exist yet)." >&2
    fi
  done
  if /opt/keycloak/bin/kcadm.sh update "realms/${M8FLOW_REALM_NAME}" \
    -s organizationsEnabled=true \
    -s registrationEmailAsUsername=false \
    -s loginWithEmailAllowed=false \
    -s duplicateEmailsAllowed=true 2>/dev/null; then
    echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: organizations, username-only login, and duplicate-email policy set successfully."
  else
    echo "[keycloak-entrypoint] Realm ${M8FLOW_REALM_NAME}: failed to enforce organizations and username-only login policy." >&2
  fi
  ensure_shared_realm_spoke_client_scope
  ensure_default_organization
  ensure_default_organization_seed_members
  disable_shared_realm_identity_first_login
  echo "[keycloak-entrypoint] Realm configuration complete."
fi

wait $KC_PID
