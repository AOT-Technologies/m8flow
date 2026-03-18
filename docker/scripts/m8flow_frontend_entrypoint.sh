#!/usr/bin/env bash
# Map plain env vars (BACKEND_BASE_URL, MULTI_TENANT_ON) into SPIFFWORKFLOW_FRONTEND_RUNTIME_CONFIG_*
# so upstream boot_server_in_docker injects them into window.spiffworkflowFrontendJsenv.
# Do not override if the prefixed env is already set.
set -euo pipefail

if [[ -n "${BACKEND_BASE_URL:-}" ]] && [[ -z "${SPIFFWORKFLOW_FRONTEND_RUNTIME_CONFIG_BACKEND_BASE_URL:-}" ]]; then
  export SPIFFWORKFLOW_FRONTEND_RUNTIME_CONFIG_BACKEND_BASE_URL="$BACKEND_BASE_URL"
fi

if [[ -n "${MULTI_TENANT_ON:-}" ]] && [[ -z "${SPIFFWORKFLOW_FRONTEND_RUNTIME_CONFIG_MULTI_TENANT_ON:-}" ]]; then
  export SPIFFWORKFLOW_FRONTEND_RUNTIME_CONFIG_MULTI_TENANT_ON="$MULTI_TENANT_ON"
fi

/app/bin/boot_server_in_docker "$@"

exec nginx -g "daemon off;"
