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

# Realms whose Keycloak login page must be warmed (see warm_login_page below).
# Shared tenant realm + master (platform-admin) realm, matching the backend
# SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS identifiers in sample.env.
MASTER_REALM="${MASTER_REALM:-master}"

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

# warm_login_page <realm-identifier>
# Drive the backend login redirect for a realm and follow it to the rendered
# Keycloak login page. Keycloak compiles the custom FreeMarker theme templates
# on the FIRST request per template; under CI's parallel test start-up
# (pytest -n auto) many workers hit that cold compile at once and each can
# exceed the 30s KC_TIMEOUT, so login fixtures fail with "waiting for #username".
# Warming both realm login pages once here forces that compile before the suite
# runs. Success = the response body contains the login form (id="kc-form-login").
warm_login_page() {
  local identifier="$1"
  local url="http://localhost:${BACKEND_PORT}/v1.0/login?authentication_identifier=${identifier}&redirect_url=${frontend_url}"
  local deadline=$(( SECONDS + TIMEOUT ))
  local body
  echo "🔥 Warming ${identifier}-realm Keycloak login page (timeout ${TIMEOUT}s)..."
  while (( SECONDS < deadline )); do
    # -L follows the backend -> Keycloak redirect chain; a cookie jar carries the
    # OIDC state cookie the backend sets before redirecting.
    if body="$(curl -fsSL --max-time 15 --cookie-jar /dev/null --cookie /dev/null "${url}" 2>/dev/null)"; then
      if [[ "${body}" == *'id="kc-form-login"'* || "${body}" == *'id="username"'* ]]; then
        echo "✅ ${identifier}-realm login page is warm."
        return 0
      fi
    fi
    sleep 3
  done
  echo "::error::${identifier}-realm login page did not render within ${TIMEOUT}s (${url})"
  return 1
}

warm_login_page "${REALM}"
warm_login_page "${MASTER_REALM}"

echo "🎉 Full stack is ready for E2E tests."
