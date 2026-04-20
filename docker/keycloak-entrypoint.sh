#!/usr/bin/env bash
# Create bootstrap admin user before first start (avoids "Local access required" behind proxy).
# Start Keycloak, then set sslRequired=NONE on realms for HTTP access (e.g. behind a reverse proxy without HTTPS termination at Keycloak).
set -e

BOOTSTRAP_USER="${KC_BOOTSTRAP_ADMIN_USERNAME:-admin}"
M8FLOW_REALM_IMPORT_FILE="/opt/keycloak/data/import/m8flow-tenant-template.json"
M8FLOW_REALM_NAME="${KEYCLOAK_REALM:-m8flow}"
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

  escaped_client_id="$(escape_sed_replacement "${M8FLOW_SPOKE_CLIENT_ID}")"
  escaped_backend_redirect="$(escape_sed_replacement "${BACKEND_REDIRECT_URI}")"
  escaped_frontend_redirect="$(escape_sed_replacement "${FRONTEND_LOGOUT_REDIRECT_URI}")"

  sed -i \
    -e "s|__M8FLOW_SPOKE_CLIENT_ID__|${escaped_client_id}|g" \
    -e "s|https://replace-me-with-m8flow-backend-host-and-path/\\*|${escaped_backend_redirect}|g" \
    -e "s|https://replace-me-with-m8flow-frontend-host-and-path/\\*|${escaped_frontend_redirect}|g" \
    "${M8FLOW_REALM_IMPORT_FILE}"

  echo "[keycloak-entrypoint] Prepared ${M8FLOW_REALM_NAME} realm import for client ${M8FLOW_SPOKE_CLIENT_ID}."
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

  echo "[keycloak-entrypoint] Setting sslRequired=NONE on realms master, m8flow..."
  for realm in master m8flow; do
    if /opt/keycloak/bin/kcadm.sh update realms/${realm} -s sslRequired=NONE 2>/dev/null; then
      echo "[keycloak-entrypoint] Realm ${realm}: sslRequired=NONE set successfully."
    else
      echo "[keycloak-entrypoint] Realm ${realm}: update skipped or failed (realm may not exist yet)." >&2
    fi
  done
  echo "[keycloak-entrypoint] Realm configuration complete."
fi

wait $KC_PID
