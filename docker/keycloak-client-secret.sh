#!/usr/bin/env bash

# Keep client lookup and secret synchronization in a small sourceable file so
# startup behavior can be exercised with a mocked kcadm command.
resolve_client_internal_id() {
  local realm_name="$1"
  local client_name="$2"
  local kcadm_bin="${M8FLOW_KEYCLOAK_KCADM_BIN:-/opt/keycloak/bin/kcadm.sh}"

  "${kcadm_bin}" get clients -r "${realm_name}" -q clientId="${client_name}" --fields id,clientId \
    | sed -nE 's/^[[:space:]]*"id"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' \
    | head -n 1
}

ensure_shared_realm_spoke_client_secret() {
  local realm_name="$1"
  local client_name="$2"
  local client_secret="$3"
  local kcadm_bin="${M8FLOW_KEYCLOAK_KCADM_BIN:-/opt/keycloak/bin/kcadm.sh}"
  local client_internal_id

  client_internal_id="$(resolve_client_internal_id "${realm_name}" "${client_name}")"
  if [ -z "${client_internal_id}" ]; then
    echo "[keycloak-entrypoint] ERROR: Client ${client_name} was not found in realm ${realm_name}; cannot synchronize its secret." >&2
    return 1
  fi

  if ! "${kcadm_bin}" update "clients/${client_internal_id}" \
    -r "${realm_name}" \
    -s clientAuthenticatorType=client-secret \
    -s "secret=${client_secret}" >/dev/null; then
    echo "[keycloak-entrypoint] ERROR: Failed to synchronize the ${client_name} client secret in realm ${realm_name}." >&2
    return 1
  fi

  echo "[keycloak-entrypoint] Synchronized the ${client_name} client secret in realm ${realm_name}."
}
