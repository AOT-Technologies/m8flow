#!/usr/bin/env bash
#
# Wait for the m8flow stack to be ready before running the Playwright E2E suite.
#
# Polls the three endpoints the browser tests depend on:
#   - Backend  : GET http://localhost:${BACKEND_PORT}/v1.0/status  -> {"ok": true, ...}
#   - Frontend : GET http://localhost:${FRONTEND_PORT}/            -> HTTP 200
#   - Keycloak : GET http://localhost:${KEYCLOAK_PORT}/realms/${REALM} -> HTTP 200
#
# The backend service has no compose healthcheck, so we poll its status endpoint
# directly. Keycloak has a slow start (180s start_period) so it gets the longest budget.
#
# Env overrides (all optional, defaults match docker/m8flow-docker-compose.yml + sample.env):
#   BACKEND_PORT (6840), FRONTEND_PORT (6841), KEYCLOAK_PORT (6842), REALM (m8flow),
#   STACK_READY_TIMEOUT (seconds, default 300)

set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-6840}"
FRONTEND_PORT="${FRONTEND_PORT:-6841}"
KEYCLOAK_PORT="${KEYCLOAK_PORT:-6842}"
REALM="${REALM:-m8flow}"
TIMEOUT="${STACK_READY_TIMEOUT:-300}"

backend_url="http://localhost:${BACKEND_PORT}/v1.0/status"
frontend_url="http://localhost:${FRONTEND_PORT}/"
keycloak_url="http://localhost:${KEYCLOAK_PORT}/realms/${REALM}"

# wait_for <name> <url> <expected-substring-or-empty>
# Polls until curl gets an HTTP 2xx response and, if a substring is given, the body contains it.
wait_for() {
  local name="$1" url="$2" expect="${3:-}"
  local deadline=$(( SECONDS + TIMEOUT ))
  local body
  echo "⏳ Waiting for ${name} at ${url} (timeout ${TIMEOUT}s)..."
  while (( SECONDS < deadline )); do
    if body="$(curl -fsS --max-time 5 "${url}" 2>/dev/null)"; then
      if [[ -z "${expect}" || "${body}" == *"${expect}"* ]]; then
        echo "✅ ${name} is ready."
        return 0
      fi
    fi
    sleep 3
  done
  echo "::error::${name} did not become ready within ${TIMEOUT}s (${url})"
  return 1
}

wait_for "Keycloak realm" "${keycloak_url}" ""
# Backend /v1.0/status returns JSON like {"ok": true, ...}; match the key loosely
# (whitespace between key and value is not guaranteed).
wait_for "Backend"        "${backend_url}"  '"ok"'
wait_for "Frontend"       "${frontend_url}" ""

echo "🎉 Full stack is ready for E2E tests."
