#!/usr/bin/env bash
# Custom entrypoint: start Keycloak briefly, set master realm sslRequired=NONE for HTTP,
# then run Keycloak in foreground (same as start_keycloak.sh post-start step).
set -e

PORT="${KC_HTTP_PORT:-8080}"
BASE="http://localhost:${PORT}"
TIMEOUT=120
ELAPSED=0

# Start Keycloak in background so we can run kcadm against it.
/opt/keycloak/bin/kc.sh "$@" &
KC_PID=$!

# Wait for admin API to be ready (use kcadm since image has no curl).
echo "Waiting for Keycloak admin API (up to ${TIMEOUT}s)..."
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  if /opt/keycloak/bin/kcadm.sh config credentials --server "$BASE" --realm master \
    --user "${KEYCLOAK_ADMIN:-admin}" --password "${KEYCLOAK_ADMIN_PASSWORD:-admin}" &>/dev/null; then
    echo "Keycloak is ready."
    break
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done

if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
  echo "WARNING: Keycloak did not become ready within ${TIMEOUT}s; attempting realm update anyway."
fi

# Set master and imported realms sslRequired=NONE so "HTTPS required" does not appear over HTTP.
echo "Configuring realms for HTTP access..."
/opt/keycloak/bin/kcadm.sh update realms/master -s sslRequired=NONE 2>/dev/null || true
/opt/keycloak/bin/kcadm.sh update realms/tenant-a -s sslRequired=NONE 2>/dev/null || true
/opt/keycloak/bin/kcadm.sh update realms/identity -s sslRequired=NONE 2>/dev/null || true

# Stop background Keycloak so we can run it in foreground as PID 1.
kill -TERM "$KC_PID" 2>/dev/null || true
wait "$KC_PID" 2>/dev/null || true

# Run Keycloak in foreground (replaces this process so it receives signals).
exec /opt/keycloak/bin/kc.sh "$@"
