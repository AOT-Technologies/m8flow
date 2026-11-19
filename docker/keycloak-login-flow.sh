#!/usr/bin/env bash
# Configure credential collection before slower organization/user seeding. Keep
# OTP, SSO and tenant membership configuration intact. Shared by all bootstraps.
_keycloak_get_browser_executions() {
  local kcadm_bin="${M8FLOW_KEYCLOAK_KCADM_BIN:-/opt/keycloak/bin/kcadm.sh}"
  "${kcadm_bin}" get authentication/flows/browser/executions -r "$1"
}

_keycloak_update_browser_execution() {
  local kcadm_bin="${M8FLOW_KEYCLOAK_KCADM_BIN:-/opt/keycloak/bin/kcadm.sh}"
  "${kcadm_bin}" update authentication/flows/browser/executions -r "$1" -f "$2"
}

ensure_realm_single_page_login() {
  local realm_name="$1"
  local executions changes execution_id requirement payload

  if ! executions="$(_keycloak_get_browser_executions "${realm_name}")"; then
    echo "[keycloak-login] Cannot read browser flow for realm ${realm_name}." >&2
    return 1
  fi
  # Missing required credential collection is an error, not a successful no-op.
  if ! printf '%s' "${executions}" | jq -e '
    type == "array" and any(.[]; .providerId == "auth-username-password-form")
  ' >/dev/null; then
    echo "[keycloak-login] Realm ${realm_name} has no Username Password Form." >&2
    return 1
  fi

  changes="$(printf '%s' "${executions}" | jq -r '
    .[] | (
      if .providerId == "auth-username-password-form" then "REQUIRED"
      elif .providerId == "auth-username-form" or .providerId == "organization"
        or (.authenticationFlow == true and .displayName == "Organization") then "DISABLED"
      else empty end
    ) as $desired | select(.requirement != $desired) | [.id, $desired] | @tsv
  ')" || return 1
  while IFS=$'\t' read -r execution_id requirement; do
    [ -n "${execution_id}" ] || continue
    payload="$(mktemp)"
    jq -n --arg id "${execution_id}" --arg requirement "${requirement}" \
      '{id: $id, requirement: $requirement}' > "${payload}"
    if ! _keycloak_update_browser_execution "${realm_name}" "${payload}"; then
      rm -f "${payload}"
      echo "[keycloak-login] Cannot configure browser flow for realm ${realm_name}." >&2
      return 1
    fi
    rm -f "${payload}"
  done <<< "${changes}"

  # The initial GET already verifies an unchanged flow. After writes, read back
  # persisted state so a failed or ignored update cannot satisfy readiness.
  if [ -n "${changes}" ]; then
    if ! executions="$(_keycloak_get_browser_executions "${realm_name}")"; then
      return 1
    fi
  fi
  if ! printf '%s' "${executions}" | jq -e '
    type == "array"
    and any(.[]; .providerId == "auth-username-password-form")
    and all(.[];
      if .providerId == "auth-username-password-form" then .requirement == "REQUIRED"
      elif .providerId == "auth-username-form" or .providerId == "organization"
        or (.authenticationFlow == true and .displayName == "Organization") then .requirement == "DISABLED"
      else true end)
  ' >/dev/null; then
    echo "[keycloak-login] Realm ${realm_name} did not retain the combined login flow." >&2
    return 1
  fi
  echo "[keycloak-login] Realm ${realm_name}: Username Password Form verified; identity-first login disabled."
}
