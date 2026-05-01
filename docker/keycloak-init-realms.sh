#!/usr/bin/env bash
# Configure Keycloak realms for HTTP access and shared-realm login policy.
# Run after Keycloak is up; realms master and the configured shared realm must exist
# (master is built-in; the shared realm is imported via --import-realm).
# Env: KEYCLOAK_SERVER_URL (default http://localhost:8080), KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD.

set -e

BASE="${KEYCLOAK_SERVER_URL:-http://localhost:8080}"
USER="${KEYCLOAK_ADMIN:-admin}"
PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
SHARED_REALM="${M8FLOW_KEYCLOAK_SHARED_REALM:-${KEYCLOAK_REALM:-m8flow}}"
DEFAULT_ORGANIZATION_ALIAS="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS:-${SHARED_REALM}}"
DEFAULT_ORGANIZATION_NAME="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_NAME:-${DEFAULT_ORGANIZATION_ALIAS}}"
DEFAULT_ORGANIZATION_SEED_USERS="admin editor integrator reviewer viewer"
SPOKE_CLIENT_ID="${M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID:-m8flow-backend}"
TIMEOUT=120
ELAPSED=0

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

  scope_id="$(resolve_client_scope_internal_id "${SHARED_REALM}" "organization")"
  if [ -z "${scope_id}" ]; then
    if /opt/keycloak/bin/kcadm.sh create client-scopes -r "${SHARED_REALM}" \
      -s name=organization \
      -s protocol=openid-connect \
      -s 'attributes."include.in.token.scope"=true' \
      -s 'attributes."display.on.consent.screen"=false' >/dev/null 2>&1; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: created organization client scope."
      scope_id="$(resolve_client_scope_internal_id "${SHARED_REALM}" "organization")"
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to create organization client scope." >&2
      return 1
    fi
  fi

  if [ -z "${scope_id}" ]; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: could not resolve organization client scope id." >&2
    return 1
  fi

  if ! /opt/keycloak/bin/kcadm.sh get "client-scopes/${scope_id}/protocol-mappers/models" -r "${SHARED_REALM}" 2>/dev/null | grep -q 'oidc-organization-membership-mapper'; then
    if /opt/keycloak/bin/kcadm.sh create "client-scopes/${scope_id}/protocol-mappers/models" -r "${SHARED_REALM}" \
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
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: organization membership mapper ensured."
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to create organization membership mapper." >&2
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

  client_internal_id="$(resolve_client_internal_id "${SHARED_REALM}" "${SPOKE_CLIENT_ID}")"
  if [ -z "${client_internal_id}" ]; then
    echo "[keycloak-init-realms] Client ${SPOKE_CLIENT_ID} not found in realm ${SHARED_REALM}; skipping organization scope reconciliation." >&2
    return 0
  fi

  scope_id="$(resolve_client_scope_internal_id "${SHARED_REALM}" "organization")"
  if [ -z "${scope_id}" ]; then
    echo "[keycloak-init-realms] Client ${SPOKE_CLIENT_ID}: organization client scope id could not be resolved." >&2
    return 1
  fi

  if /opt/keycloak/bin/kcadm.sh update "clients/${client_internal_id}/optional-client-scopes/${scope_id}" -r "${SHARED_REALM}" -n >/dev/null 2>&1; then
    echo "[keycloak-init-realms] Client ${SPOKE_CLIENT_ID}: organization optional scope ensured."
  else
    echo "[keycloak-init-realms] Client ${SPOKE_CLIENT_ID}: failed to ensure organization optional scope." >&2
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
  if [ -z "${DEFAULT_ORGANIZATION_ALIAS}" ]; then
    return 0
  fi

  if organization_alias_exists "${SHARED_REALM}" "${DEFAULT_ORGANIZATION_ALIAS}"; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: default organization ${DEFAULT_ORGANIZATION_ALIAS} already exists."
    return 0
  fi

  if /opt/keycloak/bin/kcadm.sh create organizations -r "${SHARED_REALM}" \
    -s name="${DEFAULT_ORGANIZATION_NAME}" \
    -s alias="${DEFAULT_ORGANIZATION_ALIAS}" >/dev/null 2>&1; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: created default organization ${DEFAULT_ORGANIZATION_ALIAS}."
    return 0
  fi

  echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to create default organization ${DEFAULT_ORGANIZATION_ALIAS}." >&2
  return 1
}

ensure_default_organization_seed_members() {
  local organization_id
  local username
  local user_id

  organization_id="$(resolve_organization_id_by_alias "${SHARED_REALM}" "${DEFAULT_ORGANIZATION_ALIAS}")"
  if [ -z "${organization_id}" ]; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: could not resolve default organization id for ${DEFAULT_ORGANIZATION_ALIAS}." >&2
    return 1
  fi

  for username in ${DEFAULT_ORGANIZATION_SEED_USERS}; do
    user_id="$(resolve_user_id_by_username "${SHARED_REALM}" "${username}")"
    if [ -z "${user_id}" ]; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: seed user ${username} not found; skipping default organization membership."
      continue
    fi

    if organization_has_member "${SHARED_REALM}" "${organization_id}" "${username}"; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: user ${username} already belongs to organization ${DEFAULT_ORGANIZATION_ALIAS}."
      continue
    fi

    if add_user_to_organization "${SHARED_REALM}" "${organization_id}" "${user_id}"; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: added user ${username} to organization ${DEFAULT_ORGANIZATION_ALIAS}."
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to add user ${username} to organization ${DEFAULT_ORGANIZATION_ALIAS}." >&2
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
    execution_id="$(resolve_browser_execution_id_by_name "${SHARED_REALM}" "${display_name}")"
    if [ -z "${execution_id}" ]; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: browser execution '${display_name}' not found; nothing to disable."
      continue
    fi

    if update_browser_execution_requirement "${SHARED_REALM}" "${execution_id}" "DISABLED"; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: browser execution '${display_name}' disabled."
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to disable browser execution '${display_name}'." >&2
      return 1
    fi
  done
}

echo "[keycloak-init-realms] Waiting for Keycloak admin API at ${BASE} (up to ${TIMEOUT}s)..."
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  if /opt/keycloak/bin/kcadm.sh config credentials --server "$BASE" --realm master \
    --user "$USER" --password "$PASS" >/dev/null 2>&1; then
    echo "[keycloak-init-realms] Keycloak admin API ready after ${ELAPSED}s."
    break
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done

if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
  echo "[keycloak-init-realms] WARNING: Keycloak did not become ready within ${TIMEOUT}s; attempting realm update anyway." >&2
fi

echo "[keycloak-init-realms] Setting sslRequired=NONE on realms master, ${SHARED_REALM}..."
for realm in master "${SHARED_REALM}"; do
  if /opt/keycloak/bin/kcadm.sh update realms/${realm} -s sslRequired=NONE 2>/dev/null; then
    echo "[keycloak-init-realms] Realm ${realm}: sslRequired=NONE set successfully."
  else
    echo "[keycloak-init-realms] Realm ${realm}: update failed or realm does not exist." >&2
  fi
done
if /opt/keycloak/bin/kcadm.sh update "realms/${SHARED_REALM}" \
  -s organizationsEnabled=true \
  -s registrationEmailAsUsername=false \
  -s loginWithEmailAllowed=false \
  -s duplicateEmailsAllowed=true 2>/dev/null; then
  echo "[keycloak-init-realms] Realm ${SHARED_REALM}: organizations, username-only login, and duplicate-email policy set successfully."
else
  echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to enforce organizations and username-only login policy." >&2
fi
ensure_shared_realm_spoke_client_scope
ensure_default_organization
ensure_default_organization_seed_members
disable_shared_realm_identity_first_login
echo "[keycloak-init-realms] Realm configuration complete."
