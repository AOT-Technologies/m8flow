#!/bin/sh
set -eu

keycloak_http_port="${KC_HTTP_PORT:-8080}"
keycloak_url="${KEYCLOAK_INTERNAL_URL:-http://keycloak:${keycloak_http_port}}"
keycloak_admin_user="${KEYCLOAK_ADMIN:-admin}"
keycloak_admin_password="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
keycloak_super_admin_user="${KEYCLOAK_SUPER_ADMIN_USER:-super-admin}"
keycloak_super_admin_password="${KEYCLOAK_SUPER_ADMIN_PASSWORD:-super-admin}"
keycloak_master_realm_name="${M8FLOW_KEYCLOAK_MASTER_REALM:-master}"
keycloak_client_id="${M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID:-m8flow-backend}"
keycloak_client_secret="${M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET:-${M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET:-JXeQExm0JhQPLumgHtIIqf52bDalHz0q}}"
backend_public_url="${M8FLOW_BACKEND_URL:-http://localhost:6840}"
frontend_public_url="${M8FLOW_BACKEND_URL_FOR_FRONTEND:-http://localhost:6841}"
backend_redirect_uri="${backend_public_url%/}/*"
frontend_logout_redirect_uri="${frontend_public_url%/}/*"
m8flow_realm_name="${M8FLOW_KEYCLOAK_SHARED_REALM:-${KEYCLOAK_REALM:-m8flow}}"
placeholder_client_id="__M8FLOW_SPOKE_CLIENT_ID__"

echo ":: Waiting for Keycloak master realm at ${keycloak_url}..."
i=0
until /opt/keycloak/bin/kcadm.sh config credentials \
  --server "${keycloak_url}" \
  --realm master \
  --user "${keycloak_admin_user}" \
  --password "${keycloak_admin_password}" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo >&2 "ERROR: Keycloak did not become ready in time."
    exit 1
  fi
  sleep 2
done

echo ":: Connected to Keycloak admin API."

/opt/keycloak/bin/kcadm.sh update realms/master -s sslRequired=NONE >/dev/null 2>&1 || true

ensure_admin_realm_exists() {
  realm_name="$1"
  if [ "${realm_name}" = "master" ]; then
    return 0
  fi

  if /opt/keycloak/bin/kcadm.sh get "realms/${realm_name}" >/dev/null 2>&1; then
    /opt/keycloak/bin/kcadm.sh update "realms/${realm_name}" -s sslRequired=NONE >/dev/null 2>&1 || true
    return 0
  fi

  echo ":: Creating admin realm ${realm_name}..."
  /opt/keycloak/bin/kcadm.sh create realms \
    -s realm="${realm_name}" \
    -s enabled=true \
    -s sslRequired=NONE >/dev/null
}

resolve_named_resource_id() {
  match_field="$1"
  match_value="$2"
  current_id=""
  resolved_id=""

  while IFS= read -r line; do
    next_id="$(printf '%s\n' "${line}" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    if [ -n "${next_id}" ]; then
      current_id="${next_id}"
    fi

    next_value="$(
      printf '%s\n' "${line}" \
        | sed -n 's/.*"'"${match_field}"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
    )"
    if [ "${next_value}" = "${match_value}" ]; then
      resolved_id="${current_id}"
    fi
  done

  if [ -n "${resolved_id}" ]; then
    printf '%s\n' "${resolved_id}"
  fi
}

resolve_client_internal_id() {
  realm_name="$1"
  client_name="$2"
  /opt/keycloak/bin/kcadm.sh get clients -r "${realm_name}" -q clientId="${client_name}" --fields id,clientId \
    | resolve_named_resource_id clientId "${client_name}"
}

resolve_client_scope_internal_id() {
  realm_name="$1"
  scope_name="$2"
  /opt/keycloak/bin/kcadm.sh get client-scopes -r "${realm_name}" -q name="${scope_name}" --fields id,name \
    | resolve_named_resource_id name "${scope_name}"
}

resolve_user_internal_id() {
  realm_name="$1"
  username="$2"
  /opt/keycloak/bin/kcadm.sh get users -r "${realm_name}" -q username="${username}" --fields id,username \
    | resolve_named_resource_id username "${username}"
}

resolve_protocol_mapper_id() {
  resource_path="$1"
  realm_name="$2"
  mapper_name="$3"
  /opt/keycloak/bin/kcadm.sh get "${resource_path}/protocol-mappers/models" -r "${realm_name}" --fields id,name 2>/dev/null \
    | resolve_named_resource_id name "${mapper_name}"
}

remove_legacy_groups_mapper_from_resource() {
  realm_name="$1"
  resource_path="$2"
  mapper_id="$(resolve_protocol_mapper_id "${resource_path}" "${realm_name}" groups)"
  if [ -z "${mapper_id}" ]; then
    return 0
  fi

  if /opt/keycloak/bin/kcadm.sh delete "${resource_path}/protocol-mappers/models/${mapper_id}" -r "${realm_name}" >/dev/null 2>&1; then
    echo ":: Realm ${realm_name}: removed legacy root groups mapper from ${resource_path}."
    return 0
  fi

  echo >&2 "ERROR: Failed to remove legacy root groups mapper from ${resource_path} in realm ${realm_name}"
  return 1
}

remove_legacy_root_group_mappers() {
  realm_name="$1"
  client_internal_id="$2"
  profile_scope_internal_id=""

  if [ -n "${client_internal_id}" ]; then
    remove_legacy_groups_mapper_from_resource "${realm_name}" "clients/${client_internal_id}" || return 1
  fi

  profile_scope_internal_id="$(resolve_client_scope_internal_id "${realm_name}" profile)"
  if [ -n "${profile_scope_internal_id}" ]; then
    remove_legacy_groups_mapper_from_resource "${realm_name}" "client-scopes/${profile_scope_internal_id}" || return 1
  fi
}

ensure_roles_mapper() {
  realm_name="$1"
  client_internal_id="$2"

  # Fast path: skip if a "roles" mapper already exists on the client.
  if /opt/keycloak/bin/kcadm.sh get "clients/${client_internal_id}/protocol-mappers/models" -r "${realm_name}" 2>/dev/null \
    | grep -q '"name"[[:space:]]*:[[:space:]]*"roles"'; then
    return 0
  fi

  # Create idempotently. The pre-check above can race with the keycloak container's
  # own post-start realm configuration (the init service starts as soon as Keycloak is
  # *healthy*, while the entrypoint is still configuring it) or transiently return empty
  # under load. Tolerate an "exists with same name" response instead of aborting the
  # whole init script under `set -eu`.
  if create_output="$(
    /opt/keycloak/bin/kcadm.sh create "clients/${client_internal_id}/protocol-mappers/models" -r "${realm_name}" \
      -s name=roles \
      -s protocol=openid-connect \
      -s protocolMapper=oidc-usermodel-realm-role-mapper \
      -s consentRequired=false \
      -s 'config."introspection.token.claim"=true' \
      -s 'config.multivalued=true' \
      -s 'config."userinfo.token.claim"=true' \
      -s 'config."id.token.claim"=true' \
      -s 'config."access.token.claim"=true' \
      -s 'config."claim.name"=roles' \
      -s 'config."jsonType.label"=String' 2>&1
  )"; then
    return 0
  fi

  if printf '%s' "${create_output}" | grep -qi 'exists'; then
    echo ":: Realm ${realm_name}: roles protocol mapper already exists; skipping."
    return 0
  fi

  echo >&2 "ERROR: Realm ${realm_name}: failed to create roles protocol mapper: ${create_output}"
  return 1
}

ensure_spoke_client_in_realm() {
  realm_name="$1"

  /opt/keycloak/bin/kcadm.sh get "realms/${realm_name}" >/dev/null 2>&1 || {
    echo ":: Realm ${realm_name} not present; skipping spoke client reconciliation."
    return 0
  }

  current_client_internal_id="$(resolve_client_internal_id "${realm_name}" "${keycloak_client_id}")"
  placeholder_client_internal_id="$(resolve_client_internal_id "${realm_name}" "${placeholder_client_id}")"

  if [ -z "${current_client_internal_id}" ] && [ -n "${placeholder_client_internal_id}" ]; then
    current_client_internal_id="${placeholder_client_internal_id}"
    echo ":: Renaming placeholder client ${placeholder_client_id} to ${keycloak_client_id} in realm ${realm_name}."
  elif [ -z "${current_client_internal_id}" ]; then
    echo ":: Creating spoke client ${keycloak_client_id} in realm ${realm_name}."
    /opt/keycloak/bin/kcadm.sh create clients -r "${realm_name}" \
      -s clientId="${keycloak_client_id}" \
      -s enabled=true \
      -s publicClient=false \
      -s secret="${keycloak_client_secret}" \
      -s standardFlowEnabled=true \
      -s directAccessGrantsEnabled=true \
      -s serviceAccountsEnabled=true \
      -s fullScopeAllowed=true \
      -s bearerOnly=false \
      -s authorizationServicesEnabled=true \
      -s 'defaultClientScopes=["web-origins","acr","profile","roles","email"]' \
      -s 'optionalClientScopes=["address","phone","offline_access","microprofile-jwt"]' \
      -s "redirectUris=[\"${backend_redirect_uri}\"]" \
      -s "webOrigins=[\"${frontend_public_url%/}\"]" \
      -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" \
      >/dev/null
    current_client_internal_id="$(resolve_client_internal_id "${realm_name}" "${keycloak_client_id}")"
  fi

  if [ -z "${current_client_internal_id}" ]; then
    echo >&2 "ERROR: Failed to resolve realm ${realm_name} client id for ${keycloak_client_id}"
    exit 1
  fi

  /opt/keycloak/bin/kcadm.sh update "clients/${current_client_internal_id}" -r "${realm_name}" \
    -s clientId="${keycloak_client_id}" \
    -s enabled=true \
    -s publicClient=false \
    -s bearerOnly=false \
    -s secret="${keycloak_client_secret}" \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=true \
    -s serviceAccountsEnabled=true \
    -s authorizationServicesEnabled=true \
    -s fullScopeAllowed=true \
    -s "redirectUris=[\"${backend_redirect_uri}\"]" \
    -s "webOrigins=[\"${frontend_public_url%/}\"]" \
    -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" \
    >/dev/null

  ensure_roles_mapper "${realm_name}" "${current_client_internal_id}"
  remove_legacy_root_group_mappers "${realm_name}" "${current_client_internal_id}"
  echo ":: Realm ${realm_name} client ${keycloak_client_id} ensured."
}

echo ":: Ensuring admin realm ${keycloak_master_realm_name} super-admin role/user..."
ensure_admin_realm_exists "${keycloak_master_realm_name}"
/opt/keycloak/bin/kcadm.sh get roles/super-admin -r "${keycloak_master_realm_name}" >/dev/null 2>&1 \
  || /opt/keycloak/bin/kcadm.sh create roles -r "${keycloak_master_realm_name}" -s name=super-admin >/dev/null

client_id=$(
  /opt/keycloak/bin/kcadm.sh get clients -r "${keycloak_master_realm_name}" -q clientId="${keycloak_client_id}" --fields id,clientId \
    | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    | head -n 1
)

if [ -z "${client_id}" ]; then
  /opt/keycloak/bin/kcadm.sh create clients -r "${keycloak_master_realm_name}" \
    -s clientId="${keycloak_client_id}" \
    -s enabled=true \
    -s publicClient=false \
    -s secret="${keycloak_client_secret}" \
    -s standardFlowEnabled=true \
    -s directAccessGrantsEnabled=true \
    -s serviceAccountsEnabled=true \
    -s fullScopeAllowed=true \
    -s bearerOnly=false \
    -s 'defaultClientScopes=["web-origins","acr","profile","roles","email"]' \
    -s 'optionalClientScopes=["address","phone","offline_access","microprofile-jwt"]' \
    -s "redirectUris=[\"${backend_redirect_uri}\"]" \
    -s "webOrigins=[\"${frontend_public_url%/}\"]" \
    -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" \
    >/dev/null

  client_id=$(
    /opt/keycloak/bin/kcadm.sh get clients -r "${keycloak_master_realm_name}" -q clientId="${keycloak_client_id}" --fields id,clientId \
      | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
      | head -n 1
  )
fi

if [ -z "${client_id}" ]; then
  echo >&2 "ERROR: Failed to resolve admin realm ${keycloak_master_realm_name} client id for ${keycloak_client_id}"
  exit 1
fi

/opt/keycloak/bin/kcadm.sh update "clients/${client_id}" -r "${keycloak_master_realm_name}" \
  -s secret="${keycloak_client_secret}" \
  -s standardFlowEnabled=true \
  -s directAccessGrantsEnabled=true \
  -s serviceAccountsEnabled=true \
  -s fullScopeAllowed=true \
  -s "redirectUris=[\"${backend_redirect_uri}\"]" \
  -s "webOrigins=[\"${frontend_public_url%/}\"]" \
  -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" \
  >/dev/null

ensure_roles_mapper "${keycloak_master_realm_name}" "${client_id}"
remove_legacy_root_group_mappers "${keycloak_master_realm_name}" "${client_id}"

/opt/keycloak/bin/kcadm.sh create users -r "${keycloak_master_realm_name}" \
  -s username="${keycloak_super_admin_user}" \
  -s enabled=true \
  -s firstName=Super \
  -s lastName=Admin >/dev/null 2>&1 || true

/opt/keycloak/bin/kcadm.sh set-password \
  -r "${keycloak_master_realm_name}" \
  --username "${keycloak_super_admin_user}" \
  --new-password "${keycloak_super_admin_password}" >/dev/null

/opt/keycloak/bin/kcadm.sh add-roles \
  -r "${keycloak_master_realm_name}" \
  --uusername "${keycloak_super_admin_user}" \
  --rolename super-admin >/dev/null 2>&1 || true

ensure_spoke_client_in_realm "${m8flow_realm_name}"

echo ":: Admin realm ${keycloak_master_realm_name} client, role, and super-admin ensured."
