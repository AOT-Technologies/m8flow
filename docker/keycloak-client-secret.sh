#!/usr/bin/env bash

# Keep client lookup and secret synchronization in a small sourceable file so
# startup behavior can be exercised with a mocked kcadm command.
resolve_client_internal_id() {
  local realm_name="$1"
  local client_name="$2"
  local kcadm_bin="${M8FLOW_KEYCLOAK_KCADM_BIN:-/opt/keycloak/bin/kcadm.sh}"
  local clients_json
  local client_internal_id

  if ! clients_json="$("${kcadm_bin}" get clients -r "${realm_name}" \
    -q clientId="${client_name}" --fields id,clientId)"; then
    echo "[keycloak-entrypoint] ERROR: Failed to query client ${client_name} in realm ${realm_name}." >&2
    return 1
  fi

  if ! client_internal_id="$(printf '%s' "${clients_json}" | jq -er --arg client_id "${client_name}" '
    if type != "array" then
      error("expected an array of clients")
    else
      [ .[] | select(.clientId == $client_id) ] as $matches
      | if ($matches | length) == 0 then
          ""
        elif ($matches | length) == 1
          and ($matches[0].id | type) == "string"
          and ($matches[0].id | length) > 0 then
          $matches[0].id
        else
          error("expected exactly one matching client with a non-empty id")
        end
    end
  ' 2>/dev/null)"; then
    echo "[keycloak-entrypoint] ERROR: Client lookup for ${client_name} in realm ${realm_name} returned invalid or ambiguous results." >&2
    return 1
  fi

  printf '%s' "${client_internal_id}"
}

ensure_shared_realm_spoke_client_secret() {
  local realm_name="$1"
  local client_name="$2"
  local client_secret="$3"
  local kcadm_bin="${M8FLOW_KEYCLOAK_KCADM_BIN:-/opt/keycloak/bin/kcadm.sh}"
  local client_internal_id

  if ! client_internal_id="$(resolve_client_internal_id "${realm_name}" "${client_name}")"; then
    echo "[keycloak-entrypoint] ERROR: Cannot safely synchronize the ${client_name} client secret in realm ${realm_name}." >&2
    return 1
  fi
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
