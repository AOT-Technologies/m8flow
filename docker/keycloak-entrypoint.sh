#!/usr/bin/env bash
# Create bootstrap admin user before first start (avoids "Local access required" behind proxy).
# Start Keycloak, then set sslRequired=NONE on realms for HTTP access (e.g. behind ALB without HTTPS).
set -e

echo "[keycloak-entrypoint] Running bootstrap-admin user..."
if /opt/keycloak/bin/kc.sh bootstrap-admin user \
  --username admin \
  --password:env KC_BOOTSTRAP_ADMIN_PASSWORD \
  --no-prompt 2>/dev/null; then
  echo "[keycloak-entrypoint] Bootstrap-admin succeeded (master realm and admin created or already exist)."
else
  echo "[keycloak-entrypoint] Bootstrap-admin skipped or failed (non-fatal; master may already exist)."
fi

# Start Keycloak in background so we can run kcadm to set sslRequired=NONE after it is ready
echo "[keycloak-entrypoint] Starting Keycloak in background..."
/opt/keycloak/bin/kc.sh "$@" &
KC_PID=$!

# Admin API base URL: must include KC_HTTP_RELATIVE_PATH when set (e.g. /auth on ECS)
KC_PORT="${KC_HTTP_PORT:-8080}"
KC_PATH="${KC_HTTP_RELATIVE_PATH:-}"
BASE="http://127.0.0.1:${KC_PORT}${KC_PATH}"
USER="admin"
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
  echo "[keycloak-entrypoint] Setting sslRequired=NONE on realms master, tenant-a, identity..."
  for realm in master tenant-a identity; do
    if /opt/keycloak/bin/kcadm.sh update realms/${realm} -s sslRequired=NONE 2>/dev/null; then
      echo "[keycloak-entrypoint] Realm ${realm}: sslRequired=NONE set successfully."
    else
      echo "[keycloak-entrypoint] Realm ${realm}: update skipped or failed (realm may not exist yet)." >&2
    fi
  done
  echo "[keycloak-entrypoint] Realm configuration complete."
fi

wait $KC_PID
