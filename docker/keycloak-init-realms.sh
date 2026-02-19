#!/usr/bin/env bash
# Configure Keycloak realms for HTTP access (sslRequired=NONE).
# Run after Keycloak is up; realms master, tenant-a, identity must exist
# (master is built-in; tenant-a and identity are imported via --import-realm).
# Env: KEYCLOAK_SERVER_URL (default http://localhost:8080), KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD.

set -e

BASE="${KEYCLOAK_SERVER_URL:-http://localhost:8080}"
USER="${KEYCLOAK_ADMIN:-admin}"
PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
TIMEOUT=120
ELAPSED=0

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

echo "[keycloak-init-realms] Setting sslRequired=NONE on realms master, tenant-a, identity..."
for realm in master tenant-a identity; do
  if /opt/keycloak/bin/kcadm.sh update realms/${realm} -s sslRequired=NONE 2>/dev/null; then
    echo "[keycloak-init-realms] Realm ${realm}: sslRequired=NONE set successfully."
  else
    echo "[keycloak-init-realms] Realm ${realm}: update failed or realm does not exist." >&2
  fi
done
echo "[keycloak-init-realms] Realm configuration complete."
