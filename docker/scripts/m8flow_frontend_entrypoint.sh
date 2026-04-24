#!/usr/bin/env bash
# m8flow_frontend_entrypoint.sh
# ──────────────────────────────────────────────────────────────────────────────
# Production-grade entrypoint for the m8flow-frontend container.
#
# This script replaces the upstream boot_server_in_docker helper so we can
# own our env-var naming without modifying upstream code.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

function error_handler() {
  echo >&2 "Exited with BAD EXIT CODE '${2}' in ${0} script at line: ${1}."
  exit "$2"
}
trap 'error_handler ${LINENO} $?' ERR
set -o errtrace

# ── Step 1: Map plain env vars into M8FLOW_FRONTEND_RUNTIME_CONFIG_* ─────────
if [[ -n "${BACKEND_BASE_URL:-}" ]] && [[ -z "${M8FLOW_FRONTEND_RUNTIME_CONFIG_BACKEND_BASE_URL:-}" ]]; then
  export M8FLOW_FRONTEND_RUNTIME_CONFIG_BACKEND_BASE_URL="$BACKEND_BASE_URL"
fi

if [[ -n "${MULTI_TENANT_ON:-}" ]] && [[ -z "${M8FLOW_FRONTEND_RUNTIME_CONFIG_MULTI_TENANT_ON:-}" ]]; then
  export M8FLOW_FRONTEND_RUNTIME_CONFIG_MULTI_TENANT_ON="$MULTI_TENANT_ON"
fi

# ── Step 2: Inject runtime config into index.html ────────────────────────────
# Mirrors the upstream boot_server_in_docker logic but reads
# M8FLOW_FRONTEND_RUNTIME_CONFIG_* instead of SPIFFWORKFLOW_FRONTEND_RUNTIME_CONFIG_*.
# The target JS object (window.spiffworkflowFrontendJsenv) stays unchanged
# because the React app expects exactly that name.
runtime_configs=$(env | grep -E "^M8FLOW_FRONTEND_RUNTIME_CONFIG_" || echo '')
if [[ -n "$runtime_configs" ]]; then
  index_html_file="/usr/share/nginx/html/index.html"
  if [[ ! -f "$index_html_file" ]]; then
    echo >&2 "ERROR: Could not find '${index_html_file}'. Cannot use M8FLOW_FRONTEND_RUNTIME_CONFIG values without it."
    exit 1
  fi

  if ! command -v sed >/dev/null; then
    echo >&2 "ERROR: sed command not found. Cannot use M8FLOW_FRONTEND_RUNTIME_CONFIG values without it."
    exit 1
  fi

  while IFS= read -r config_line; do
    [[ -z "$config_line" ]] && continue

    env_var=$(awk -F '=' '{print $1}' <<<"$config_line" | sed -E 's/^M8FLOW_FRONTEND_RUNTIME_CONFIG_//')
    env_value=$(awk -F '=' '{print $2}' <<<"$config_line" | sed -E "s/(^['\"]|['\"]$)//g")

    if [[ -z "$env_var" ]]; then
      echo >&2 "ERROR: Could not parse runtime config line: '${config_line}'."
      exit 1
    fi

    if [[ -n "$env_value" ]]; then
      escaped_value=$(sed -E 's|/|\\/|g' <<<"${env_value}")
      # Inject into the JS config object in the html page
      sed -i "s/\(window.spiffworkflowFrontendJsenv *= *{}\)/\1;window.spiffworkflowFrontendJsenv.${env_var} = '${escaped_value}'/" "$index_html_file"

      env_value_grep_escaped=$(sed -E 's/\[/\\[/g' <<<"$env_value")
      if ! grep -q "${env_var} = '${env_value_grep_escaped}'" "$index_html_file"; then
        echo >&2 "ERROR: Could not find \"${env_var} = '${env_value}'\" in '${index_html_file}' after search and replace. The assumptions about index.html contents may have changed."
        echo >&2 "index.html: $(cat "$index_html_file")"
        exit 1
      fi
    fi
  done <<<"$runtime_configs"
fi

# ── Step 3: Render nginx config template ─────────────────────────────────────
port_to_use="${PORT0:-80}"
if [[ -n "${M8FLOW_FRONTEND_INTERNAL_PORT:-}" ]]; then
  port_to_use="$M8FLOW_FRONTEND_INTERNAL_PORT"
fi
sed "s/{{M8FLOW_FRONTEND_INTERNAL_PORT}}/${port_to_use}/g" /var/tmp/nginx.conf.template >/etc/nginx/conf.d/default.conf

# ── Step 4: Start nginx ──────────────────────────────────────────────────────
exec nginx -g "daemon off;"
