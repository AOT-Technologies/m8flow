#!/usr/bin/env bash
# Configure Keycloak realms for HTTP access and shared-realm login policy.
# Run after Keycloak is up; realms master and the configured shared realm must exist
# (master is built-in; the shared realm is imported via --import-realm).
# Env: KEYCLOAK_SERVER_URL (default http://localhost:8080), KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD.

set -e

BASE="${KEYCLOAK_SERVER_URL:-http://localhost:8080}"
USER="${KEYCLOAK_ADMIN:-admin}"
PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
SHARED_REALM="${M8FLOW_KEYCLOAK_SHARED_REALM:-${KEYCLOAK_REALM:-m8flow}}"
DEFAULT_ORGANIZATION_ALIAS="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_ALIAS:-${SHARED_REALM}}"
DEFAULT_ORGANIZATION_NAME="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_NAME:-${DEFAULT_ORGANIZATION_ALIAS}}"
DEFAULT_ORGANIZATION_SEED_USERS="admin editor integrator reviewer submitter viewer"
ORGANIZATION_ROLE_GROUPS="Approvers Designers Administrators Support Submitters Viewers"
LEGACY_ORGANIZATION_ROLE_GROUPS="tenant-admin editor integrator reviewer submitter viewer"
DEFAULT_ORGANIZATION_SEED_ROLE_ASSIGNMENTS="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_SEED_ROLE_ASSIGNMENTS:-reviewer:Approvers editor:Designers admin:Administrators integrator:Support submitter:Submitters viewer:Viewers}"
DEFAULT_ORGANIZATION_SEED_USER_ROLE_ASSIGNMENTS="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_SEED_USER_ROLE_ASSIGNMENTS:-admin:tenant-admin editor:editor integrator:integrator reviewer:reviewer submitter:submitter viewer:viewer}"
ORGANIZATION_GROUP_ROLE_MAPPINGS="${M8FLOW_KEYCLOAK_ORGANIZATION_GROUP_ROLE_MAPPINGS:-Administrators:tenant-admin Approvers:reviewer Designers:editor Support:integrator Submitters:submitter Viewers:viewer}"
SPOKE_CLIENT_ID="${M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID:-m8flow-backend}"
TIMEOUT=120
ELAPSED=0

resolve_client_internal_id() {
  local realm_name="$1"
  local client_name="$2"

  /opt/keycloak/bin/kcadm.sh get clients -r "${realm_name}" -q clientId="${client_name}" --fields id,clientId \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

resolve_client_scope_internal_id() {
  local realm_name="$1"
  local scope_name="$2"

  /opt/keycloak/bin/kcadm.sh get client-scopes -r "${realm_name}" --fields id,name \
    | grep -B1 "\"name\" : \"${scope_name}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

resolve_client_scope_protocol_mapper_internal_id() {
  local realm_name="$1"
  local scope_id="$2"
  local protocol_mapper_name="$3"

  /opt/keycloak/bin/kcadm.sh get "client-scopes/${scope_id}/protocol-mappers/models" -r "${realm_name}" 2>/dev/null \
    | grep -B8 "\"protocolMapper\" : \"${protocol_mapper_name}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | tail -n 1
}

resolve_resource_protocol_mapper_id_by_name() {
  local resource_path="$1"
  local realm_name="$2"
  local mapper_name="$3"

  /opt/keycloak/bin/kcadm.sh get "${resource_path}/protocol-mappers/models" -r "${realm_name}" 2>/dev/null \
    | grep -B6 "\"name\" : \"${mapper_name}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

remove_legacy_root_groups_mapper() {
  local realm_name="$1"
  local resource_path="$2"
  local mapper_id

  mapper_id="$(resolve_resource_protocol_mapper_id_by_name "${resource_path}" "${realm_name}" "groups")"
  if [ -z "${mapper_id}" ]; then
    return 0
  fi

  if /opt/keycloak/bin/kcadm.sh delete "${resource_path}/protocol-mappers/models/${mapper_id}" -r "${realm_name}" >/dev/null 2>&1; then
    echo "[keycloak-init-realms] Realm ${realm_name}: removed legacy root groups mapper from ${resource_path}."
    return 0
  fi

  echo "[keycloak-init-realms] Realm ${realm_name}: failed to remove legacy root groups mapper from ${resource_path}." >&2
  return 1
}

remove_shared_realm_legacy_root_group_mappers() {
  local client_internal_id
  local profile_scope_id

  client_internal_id="$(resolve_client_internal_id "${SHARED_REALM}" "${SPOKE_CLIENT_ID}")"
  if [ -n "${client_internal_id}" ]; then
    remove_legacy_root_groups_mapper "${SHARED_REALM}" "clients/${client_internal_id}" || return 1
  fi

  profile_scope_id="$(resolve_client_scope_internal_id "${SHARED_REALM}" "profile")"
  if [ -n "${profile_scope_id}" ]; then
    remove_legacy_root_groups_mapper "${SHARED_REALM}" "client-scopes/${profile_scope_id}" || return 1
  fi
}

ensure_shared_realm_organization_scope() {
  local scope_id
  local organization_membership_mapper_id
  local organization_group_membership_mapper_id

  scope_id="$(resolve_client_scope_internal_id "${SHARED_REALM}" "organization")"
  if [ -z "${scope_id}" ]; then
    if /opt/keycloak/bin/kcadm.sh create client-scopes -r "${SHARED_REALM}" \
      -s name=organization \
      -s protocol=openid-connect \
      -s 'attributes."include.in.token.scope"=true' \
      -s 'attributes."display.on.consent.screen"=false' >/dev/null 2>&1; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: created organization client scope."
      scope_id="$(resolve_client_scope_internal_id "${SHARED_REALM}" "organization")"
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to create organization client scope." >&2
      return 1
    fi
  fi

  if [ -z "${scope_id}" ]; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: could not resolve organization client scope id." >&2
    return 1
  fi

  organization_membership_mapper_id="$(
    resolve_client_scope_protocol_mapper_internal_id \
      "${SHARED_REALM}" \
      "${scope_id}" \
      "oidc-organization-membership-mapper"
  )"
  if [ -z "${organization_membership_mapper_id}" ]; then
    if /opt/keycloak/bin/kcadm.sh create "client-scopes/${scope_id}/protocol-mappers/models" -r "${SHARED_REALM}" \
      -s name=organization \
      -s protocol=openid-connect \
      -s protocolMapper=oidc-organization-membership-mapper \
      -s consentRequired=false \
      -s 'config."claim.name"=organization' \
      -s 'config."id.token.claim"=true' \
      -s 'config."access.token.claim"=true' \
      -s 'config."userinfo.token.claim"=true' \
      -s 'config."introspection.token.claim"=true' \
      -s 'config."addOrganizationId"=true' \
      -s 'config.multivalued=true' \
      -s 'config."jsonType.label"=String' >/dev/null 2>&1; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: organization membership mapper ensured."
      organization_membership_mapper_id="$(
        resolve_client_scope_protocol_mapper_internal_id \
          "${SHARED_REALM}" \
          "${scope_id}" \
          "oidc-organization-membership-mapper"
      )"
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to create organization membership mapper." >&2
      return 1
    fi
  fi

  if [ -z "${organization_membership_mapper_id}" ]; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: could not resolve organization membership mapper id." >&2
    return 1
  fi

  if ! /opt/keycloak/bin/kcadm.sh update \
    "client-scopes/${scope_id}/protocol-mappers/models/${organization_membership_mapper_id}" \
    -r "${SHARED_REALM}" \
    -s name=organization \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-organization-membership-mapper \
    -s consentRequired=false \
    -s 'config."claim.name"=organization' \
    -s 'config."id.token.claim"=true' \
    -s 'config."access.token.claim"=true' \
    -s 'config."userinfo.token.claim"=true' \
    -s 'config."introspection.token.claim"=true' \
    -s 'config."addOrganizationId"=true' \
    -s 'config.multivalued=true' \
    -s 'config."jsonType.label"=String' >/dev/null 2>&1; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to update organization membership mapper." >&2
    return 1
  fi

  organization_group_membership_mapper_id="$(
    resolve_client_scope_protocol_mapper_internal_id \
      "${SHARED_REALM}" \
      "${scope_id}" \
      "oidc-organization-group-membership-mapper"
  )"
  if [ -z "${organization_group_membership_mapper_id}" ]; then
    organization_group_membership_mapper_id="$(
      resolve_resource_protocol_mapper_id_by_name \
        "client-scopes/${scope_id}" \
        "${SHARED_REALM}" \
        "organization-groups"
    )"
  fi

  if [ -z "${organization_group_membership_mapper_id}" ]; then
    if /opt/keycloak/bin/kcadm.sh create "client-scopes/${scope_id}/protocol-mappers/models" -r "${SHARED_REALM}" \
      -s name=organization-groups \
      -s protocol=openid-connect \
      -s protocolMapper=oidc-organization-group-membership-mapper \
      -s consentRequired=false \
      -s 'config."claim.name"=organization' \
      -s 'config."id.token.claim"=true' \
      -s 'config."access.token.claim"=true' \
      -s 'config."userinfo.token.claim"=true' \
      -s 'config."introspection.token.claim"=true' >/dev/null 2>&1; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: organization group membership mapper ensured."
      organization_group_membership_mapper_id="$(
        resolve_client_scope_protocol_mapper_internal_id \
          "${SHARED_REALM}" \
          "${scope_id}" \
          "oidc-organization-group-membership-mapper"
      )"
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to create organization group membership mapper." >&2
      return 1
    fi
  fi

  if [ -z "${organization_group_membership_mapper_id}" ]; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: could not resolve organization group membership mapper id." >&2
    return 1
  fi

  if ! /opt/keycloak/bin/kcadm.sh update \
    "client-scopes/${scope_id}/protocol-mappers/models/${organization_group_membership_mapper_id}" \
    -r "${SHARED_REALM}" \
    -s name=organization-groups \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-organization-group-membership-mapper \
    -s consentRequired=false \
    -s 'config."claim.name"=organization' \
    -s 'config."id.token.claim"=true' \
    -s 'config."access.token.claim"=true' \
    -s 'config."userinfo.token.claim"=true' \
    -s 'config."introspection.token.claim"=true' >/dev/null 2>&1; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to update organization group membership mapper." >&2
    return 1
  fi

  normalized_organization_membership_mapper_id="$(
    resolve_client_scope_protocol_mapper_internal_id \
      "${SHARED_REALM}" \
      "${scope_id}" \
      "oidc-normalized-organization-membership-mapper"
  )"
  if [ -z "${normalized_organization_membership_mapper_id}" ]; then
    if /opt/keycloak/bin/kcadm.sh create "client-scopes/${scope_id}/protocol-mappers/models" -r "${SHARED_REALM}" \
      -s name=normalized-organization \
      -s protocol=openid-connect \
      -s protocolMapper=oidc-normalized-organization-membership-mapper \
      -s consentRequired=false \
      -s 'config."claim.name"=organization' \
      -s 'config."id.token.claim"=true' \
      -s 'config."access.token.claim"=true' \
      -s 'config."userinfo.token.claim"=true' \
      -s 'config."introspection.token.claim"=true' >/dev/null 2>&1; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: normalized organization membership mapper ensured."
      normalized_organization_membership_mapper_id="$(
        resolve_client_scope_protocol_mapper_internal_id \
          "${SHARED_REALM}" \
          "${scope_id}" \
          "oidc-normalized-organization-membership-mapper"
      )"
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to create normalized organization membership mapper." >&2
      return 1
    fi
  fi

  if [ -z "${normalized_organization_membership_mapper_id}" ]; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: could not resolve normalized organization membership mapper id." >&2
    return 1
  fi

  if ! /opt/keycloak/bin/kcadm.sh update \
    "client-scopes/${scope_id}/protocol-mappers/models/${normalized_organization_membership_mapper_id}" \
    -r "${SHARED_REALM}" \
    -s name=normalized-organization \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-normalized-organization-membership-mapper \
    -s consentRequired=false \
    -s 'config."claim.name"=organization' \
    -s 'config."id.token.claim"=true' \
    -s 'config."access.token.claim"=true' \
    -s 'config."userinfo.token.claim"=true' \
    -s 'config."introspection.token.claim"=true' >/dev/null 2>&1; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to update normalized organization membership mapper." >&2
    return 1
  fi
}

ensure_shared_realm_spoke_client_scope() {
  if ! ensure_shared_realm_organization_scope; then
    return 1
  fi

  local client_internal_id
  local scope_id

  client_internal_id="$(resolve_client_internal_id "${SHARED_REALM}" "${SPOKE_CLIENT_ID}")"
  if [ -z "${client_internal_id}" ]; then
    echo "[keycloak-init-realms] Client ${SPOKE_CLIENT_ID} not found in realm ${SHARED_REALM}; skipping organization scope reconciliation." >&2
    return 0
  fi

  scope_id="$(resolve_client_scope_internal_id "${SHARED_REALM}" "organization")"
  if [ -z "${scope_id}" ]; then
    echo "[keycloak-init-realms] Client ${SPOKE_CLIENT_ID}: organization client scope id could not be resolved." >&2
    return 1
  fi

  if /opt/keycloak/bin/kcadm.sh update "clients/${client_internal_id}/optional-client-scopes/${scope_id}" -r "${SHARED_REALM}" -n >/dev/null 2>&1; then
    echo "[keycloak-init-realms] Client ${SPOKE_CLIENT_ID}: organization optional scope ensured."
  else
    echo "[keycloak-init-realms] Client ${SPOKE_CLIENT_ID}: failed to ensure organization optional scope." >&2
    return 1
  fi
}

organization_alias_exists() {
  local realm_name="$1"
  local organization_alias="$2"

  [ -n "${organization_alias}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get organizations -r "${realm_name}" -q search="${organization_alias}" 2>/dev/null \
    | grep -q "\"alias\" : \"${organization_alias}\""
}

resolve_organization_id_by_alias() {
  local realm_name="$1"
  local organization_alias="$2"

  [ -n "${organization_alias}" ] || return 1

  # Match by alias, not Keycloak's exact= filter (which matches name). sed holds
  # the last "id" and prints it at the matching "alias" line (no awk/jq in image).
  /opt/keycloak/bin/kcadm.sh get organizations -r "${realm_name}" -q search="${organization_alias}" 2>/dev/null \
    | sed -n "/\"id\" : \"/ { s/.*\"id\" : \"\([^\"]*\)\".*/\1/; h; }; /\"alias\" : \"${organization_alias}\"/ { x; p; q; }"
}

resolve_user_id_by_username() {
  local realm_name="$1"
  local username="$2"

  [ -n "${username}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get users -r "${realm_name}" -q username="${username}" -q exact=true --fields id,username 2>/dev/null \
    | grep -B2 "\"username\" : \"${username}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

organization_has_member() {
  local realm_name="$1"
  local organization_id="$2"
  local username="$3"

  [ -n "${organization_id}" ] || return 1
  [ -n "${username}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get "organizations/${organization_id}/members" -r "${realm_name}" -q search="${username}" -q exact=true -q max=100 2>/dev/null \
    | grep -q "\"username\" : \"${username}\""
}

add_user_to_organization() {
  local realm_name="$1"
  local organization_id="$2"
  local user_id="$3"
  local payload_file

  payload_file="$(mktemp)"
  printf '"%s"\n' "${user_id}" > "${payload_file}"

  if /opt/keycloak/bin/kcadm.sh create "organizations/${organization_id}/members" -r "${realm_name}" -f "${payload_file}" >/dev/null 2>&1; then
    rm -f "${payload_file}"
    return 0
  fi

  rm -f "${payload_file}"
  return 1
}

list_organization_ids() {
  local realm_name="$1"

  /opt/keycloak/bin/kcadm.sh get organizations -r "${realm_name}" 2>/dev/null \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p'
}

organization_group_exists() {
  local realm_name="$1"
  local organization_id="$2"
  local group_name="$3"

  [ -n "${organization_id}" ] || return 1
  [ -n "${group_name}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get "organizations/${organization_id}/groups" -r "${realm_name}" \
    -q search="${group_name}" \
    -q exact=true \
    -q briefRepresentation=true \
    -q populateHierarchy=false \
    -q subGroupsCount=false \
    -q max=100 2>/dev/null \
    | grep -q "\"name\" : \"${group_name}\""
}

resolve_organization_group_id_by_name() {
  local realm_name="$1"
  local organization_id="$2"
  local group_name="$3"

  [ -n "${organization_id}" ] || return 1
  [ -n "${group_name}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get "organizations/${organization_id}/groups" -r "${realm_name}" \
    -q search="${group_name}" \
    -q exact=true \
    -q briefRepresentation=true \
    -q populateHierarchy=false \
    -q subGroupsCount=false \
    -q max=100 2>/dev/null \
    | grep -B4 "\"name\" : \"${group_name}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

create_organization_group() {
  local realm_name="$1"
  local organization_id="$2"
  local group_name="$3"

  /opt/keycloak/bin/kcadm.sh create "organizations/${organization_id}/groups" -r "${realm_name}" \
    -s name="${group_name}" >/dev/null 2>&1
}

resolve_realm_role_id_by_name() {
  local realm_name="$1"
  local role_name="$2"

  [ -n "${role_name}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get "roles/${role_name}" -r "${realm_name}" 2>/dev/null \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | head -n 1
}

organization_group_has_realm_role() {
  local realm_name="$1"
  local organization_id="$2"
  local group_id="$3"
  local role_name="$4"

  [ -n "${organization_id}" ] || return 1
  [ -n "${group_id}" ] || return 1
  [ -n "${role_name}" ] || return 1

  # Keycloak 26+ rejects /groups/{id}/role-mappings/realm on organization-
  # owned groups with "Cannot manage organization related group via non
  # Organization API." Use the Organization-scoped endpoint instead.
  /opt/keycloak/bin/kcadm.sh get \
    "organizations/${organization_id}/groups/${group_id}/role-mappings/realm/composite" \
    -r "${realm_name}" 2>/dev/null \
    | grep -q "\"name\" : \"${role_name}\""
}

add_realm_role_to_organization_group() {
  local realm_name="$1"
  local organization_id="$2"
  local group_id="$3"
  local role_name="$4"
  local role_payload_file
  local payload_file
  local kcadm_output
  local kcadm_rc

  [ -n "${organization_id}" ] || return 1
  [ -n "${group_id}" ] || return 1
  [ -n "${role_name}" ] || return 1

  if [ -z "$(resolve_realm_role_id_by_name "${realm_name}" "${role_name}")" ]; then
    echo "[keycloak-init-realms] Realm ${realm_name}: realm role ${role_name} does not exist; cannot map to org group ${group_id}." >&2
    return 1
  fi

  role_payload_file="$(mktemp)"
  payload_file="$(mktemp)"

  if ! /opt/keycloak/bin/kcadm.sh get "roles/${role_name}" -r "${realm_name}" > "${role_payload_file}" 2>/dev/null; then
    echo "[keycloak-init-realms] Realm ${realm_name}: failed to fetch role payload for ${role_name}." >&2
    rm -f "${role_payload_file}" "${payload_file}"
    return 1
  fi

  printf '[\n' > "${payload_file}"
  cat "${role_payload_file}" >> "${payload_file}"
  printf '\n]\n' >> "${payload_file}"
  rm -f "${role_payload_file}"

  # Post via the Organization-scoped role-mappings endpoint. Keycloak 26+
  # requires this for groups created under /organizations/{org-id}/groups —
  # the standard /groups/{gid}/role-mappings/realm path returns
  # "Cannot manage organization related group via non Organization API."
  kcadm_output="$(/opt/keycloak/bin/kcadm.sh create \
    "organizations/${organization_id}/groups/${group_id}/role-mappings/realm" \
    -r "${realm_name}" -f "${payload_file}" 2>&1)"
  kcadm_rc=$?
  rm -f "${payload_file}"

  if [ "${kcadm_rc}" -eq 0 ]; then
    return 0
  fi

  echo "[keycloak-init-realms] Realm ${realm_name}: kcadm create org role-mapping failed for ${role_name} on group ${group_id} (exit ${kcadm_rc}): ${kcadm_output}" >&2
  return 1
}

list_organization_member_ids() {
  local realm_name="$1"
  local organization_id="$2"

  [ -n "${organization_id}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get "organizations/${organization_id}/members" -r "${realm_name}" -q max=500 2>/dev/null \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p'
}

remove_user_from_organization_group() {
  local realm_name="$1"
  local organization_id="$2"
  local group_id="$3"
  local member_id="$4"

  [ -n "${organization_id}" ] || return 1
  [ -n "${group_id}" ] || return 1
  [ -n "${member_id}" ] || return 1

  /opt/keycloak/bin/kcadm.sh delete "organizations/${organization_id}/groups/${group_id}/members/${member_id}" \
    -r "${realm_name}" >/dev/null 2>&1
}

remove_legacy_organization_role_memberships() {
  local realm_name="$1"
  local organization_id="$2"
  local group_name
  local group_id
  local member_id

  [ -n "${organization_id}" ] || return 1

  for group_name in ${LEGACY_ORGANIZATION_ROLE_GROUPS}; do
    group_id="$(resolve_organization_group_id_by_name "${realm_name}" "${organization_id}" "${group_name}")"
    if [ -z "${group_id}" ]; then
      continue
    fi

    while IFS= read -r member_id; do
      [ -n "${member_id}" ] || continue
      if ! organization_member_has_group "${realm_name}" "${organization_id}" "${member_id}" "${group_name}"; then
        continue
      fi

      if remove_user_from_organization_group "${realm_name}" "${organization_id}" "${group_id}" "${member_id}"; then
        echo "[keycloak-init-realms] Realm ${realm_name}: removed legacy organization group ${group_name} from member ${member_id} in organization ${organization_id}."
      else
        echo "[keycloak-init-realms] Realm ${realm_name}: failed to remove legacy organization group ${group_name} from member ${member_id} in organization ${organization_id}." >&2
        return 1
      fi
    done <<EOF
$(list_organization_member_ids "${realm_name}" "${organization_id}")
EOF
  done
}

ensure_organization_role_groups() {
  local realm_name="$1"
  local organization_id="$2"
  local group_name

  [ -n "${organization_id}" ] || return 1

  for group_name in ${ORGANIZATION_ROLE_GROUPS}; do
    if organization_group_exists "${realm_name}" "${organization_id}" "${group_name}"; then
      echo "[keycloak-init-realms] Realm ${realm_name}: organization ${organization_id} already has group ${group_name}."
      continue
    fi

    if create_organization_group "${realm_name}" "${organization_id}" "${group_name}"; then
      echo "[keycloak-init-realms] Realm ${realm_name}: created group ${group_name} for organization ${organization_id}."
    else
      echo "[keycloak-init-realms] Realm ${realm_name}: failed to create group ${group_name} for organization ${organization_id}." >&2
      return 1
    fi
  done
}

ensure_organization_group_role_mappings() {
  # Keycloak 26 does not expose any API for assigning realm roles to
  # organization-owned groups: the standard /groups/{id}/role-mappings/realm
  # endpoint rejects org groups ("Cannot manage organization related group
  # via non Organization API"), there is no /organizations/{org-id}/groups/
  # {gid}/role-mappings endpoint, and the org-group PUT endpoint only
  # accepts name/description/attributes. Upstream tracks adding this at
  # https://github.com/keycloak/keycloak/issues/30180. Until that ships,
  # M8Flow stores organization-group role mappings in group attributes and
  # derives tenant-local permissions from those groups at login time.
  local realm_name="$1"
  local organization_id="$2"

  [ -n "${organization_id}" ] || return 1

  echo "[keycloak-init-realms] Realm ${realm_name}: skipping Keycloak realm-role mapping for organization group ${organization_id} (Keycloak 26 limitation; M8Flow derives tenant permissions from organization-group membership instead)."
  return 0
}

ensure_all_organization_role_groups() {
  local realm_name="$1"
  local organization_id

  while IFS= read -r organization_id; do
    [ -n "${organization_id}" ] || continue
    remove_legacy_organization_role_memberships "${realm_name}" "${organization_id}" || return 1
    ensure_organization_role_groups "${realm_name}" "${organization_id}" || return 1
    ensure_organization_group_role_mappings "${realm_name}" "${organization_id}" || return 1
  done <<EOF
$(list_organization_ids "${realm_name}")
EOF
}

organization_member_has_group() {
  local realm_name="$1"
  local organization_id="$2"
  local member_id="$3"
  local group_name="$4"

  [ -n "${organization_id}" ] || return 1
  [ -n "${member_id}" ] || return 1
  [ -n "${group_name}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get "organizations/${organization_id}/members/${member_id}/groups" -r "${realm_name}" \
    -q briefRepresentation=true \
    -q max=100 2>/dev/null \
    | grep -q "\"name\" : \"${group_name}\""
}

add_user_to_organization_group() {
  local realm_name="$1"
  local organization_id="$2"
  local group_id="$3"
  local member_id="$4"

  [ -n "${organization_id}" ] || return 1
  [ -n "${group_id}" ] || return 1
  [ -n "${member_id}" ] || return 1

  /opt/keycloak/bin/kcadm.sh update "organizations/${organization_id}/groups/${group_id}/members/${member_id}" \
    -r "${realm_name}" \
    -n >/dev/null 2>&1
}

ensure_default_organization() {
  if [ -z "${DEFAULT_ORGANIZATION_ALIAS}" ]; then
    return 0
  fi

  if organization_alias_exists "${SHARED_REALM}" "${DEFAULT_ORGANIZATION_ALIAS}"; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: default organization ${DEFAULT_ORGANIZATION_ALIAS} already exists."
    return 0
  fi

  if /opt/keycloak/bin/kcadm.sh create organizations -r "${SHARED_REALM}" \
    -s name="${DEFAULT_ORGANIZATION_NAME}" \
    -s alias="${DEFAULT_ORGANIZATION_ALIAS}" >/dev/null 2>&1; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: created default organization ${DEFAULT_ORGANIZATION_ALIAS}."
    return 0
  fi

  echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to create default organization ${DEFAULT_ORGANIZATION_ALIAS}." >&2
  return 1
}

ensure_default_organization_seed_members() {
  local organization_id
  local username
  local user_id

  organization_id="$(resolve_organization_id_by_alias "${SHARED_REALM}" "${DEFAULT_ORGANIZATION_ALIAS}")"
  if [ -z "${organization_id}" ]; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: could not resolve default organization id for ${DEFAULT_ORGANIZATION_ALIAS}." >&2
    return 1
  fi

  for username in ${DEFAULT_ORGANIZATION_SEED_USERS}; do
    user_id="$(resolve_user_id_by_username "${SHARED_REALM}" "${username}")"
    if [ -z "${user_id}" ]; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: seed user ${username} not found; skipping default organization membership."
      continue
    fi

    if organization_has_member "${SHARED_REALM}" "${organization_id}" "${username}"; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: user ${username} already belongs to organization ${DEFAULT_ORGANIZATION_ALIAS}."
      continue
    fi

    if add_user_to_organization "${SHARED_REALM}" "${organization_id}" "${user_id}"; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: added user ${username} to organization ${DEFAULT_ORGANIZATION_ALIAS}."
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to add user ${username} to organization ${DEFAULT_ORGANIZATION_ALIAS}." >&2
      return 1
    fi
  done
}

ensure_default_organization_seed_roles() {
  local organization_id
  local assignment
  local username
  local group_name
  local user_id
  local group_id

  organization_id="$(resolve_organization_id_by_alias "${SHARED_REALM}" "${DEFAULT_ORGANIZATION_ALIAS}")"
  if [ -z "${organization_id}" ]; then
    echo "[keycloak-init-realms] Realm ${SHARED_REALM}: could not resolve default organization id for ${DEFAULT_ORGANIZATION_ALIAS} while applying seed roles." >&2
    return 1
  fi

  for assignment in ${DEFAULT_ORGANIZATION_SEED_ROLE_ASSIGNMENTS}; do
    username="${assignment%%:*}"
    group_name="${assignment#*:}"
    if [ -z "${username}" ] || [ -z "${group_name}" ]; then
      continue
    fi

    user_id="$(resolve_user_id_by_username "${SHARED_REALM}" "${username}")"
    if [ -z "${user_id}" ]; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: seed user ${username} not found; skipping default organization role ${group_name}."
      continue
    fi

    if ! organization_has_member "${SHARED_REALM}" "${organization_id}" "${username}"; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: user ${username} is not a member of ${DEFAULT_ORGANIZATION_ALIAS}; skipping default organization role ${group_name}." >&2
      continue
    fi

    group_id="$(resolve_organization_group_id_by_name "${SHARED_REALM}" "${organization_id}" "${group_name}")"
    if [ -z "${group_id}" ]; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: could not resolve organization group ${group_name} in ${DEFAULT_ORGANIZATION_ALIAS}." >&2
      return 1
    fi

    if organization_member_has_group "${SHARED_REALM}" "${organization_id}" "${user_id}" "${group_name}"; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: user ${username} already has organization role ${group_name} in ${DEFAULT_ORGANIZATION_ALIAS}."
      continue
    fi

    if add_user_to_organization_group "${SHARED_REALM}" "${organization_id}" "${group_id}" "${user_id}"; then
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: assigned organization role ${group_name} to user ${username} in ${DEFAULT_ORGANIZATION_ALIAS}."
    else
      echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to assign organization role ${group_name} to user ${username} in ${DEFAULT_ORGANIZATION_ALIAS}." >&2
      return 1
    fi
  done
}

user_has_realm_role() {
  local realm_name="$1"
  local user_id="$2"
  local role_name="$3"

  [ -n "${user_id}" ] || return 1
  [ -n "${role_name}" ] || return 1

  /opt/keycloak/bin/kcadm.sh get "users/${user_id}/role-mappings/realm/composite" -r "${realm_name}" 2>/dev/null \
    | grep -q "\"name\" : \"${role_name}\""
}

remove_default_organization_seed_user_realm_roles() {
  local realm_name="$1"
  local assignment
  local username
  local role_name
  local user_id
  local kcadm_output
  local kcadm_rc

  for assignment in ${DEFAULT_ORGANIZATION_SEED_USER_ROLE_ASSIGNMENTS}; do
    username="${assignment%%:*}"
    role_name="${assignment#*:}"
    if [ -z "${username}" ] || [ -z "${role_name}" ]; then
      continue
    fi

    user_id="$(resolve_user_id_by_username "${realm_name}" "${username}")"
    if [ -z "${user_id}" ]; then
      echo "[keycloak-init-realms] Realm ${realm_name}: seed user ${username} not found; skipping direct realm-role cleanup for ${role_name}."
      continue
    fi

    if ! user_has_realm_role "${realm_name}" "${user_id}" "${role_name}"; then
      echo "[keycloak-init-realms] Realm ${realm_name}: user ${username} does not hold direct realm role ${role_name}; nothing to remove."
      continue
    fi

    kcadm_output="$(/opt/keycloak/bin/kcadm.sh remove-roles -r "${realm_name}" --uid "${user_id}" --rolename "${role_name}" 2>&1)"
    kcadm_rc=$?
    if [ "${kcadm_rc}" -eq 0 ]; then
      echo "[keycloak-init-realms] Realm ${realm_name}: removed direct realm role ${role_name} from user ${username}."
    else
      echo "[keycloak-init-realms] Realm ${realm_name}: failed to remove realm role ${role_name} from user ${username} (exit ${kcadm_rc}): ${kcadm_output}" >&2
      return 1
    fi
  done
}

resolve_browser_execution_id_by_name() {
  local realm_name="$1"
  local display_name="$2"

  /opt/keycloak/bin/kcadm.sh get authentication/flows/browser/executions -r "${realm_name}" 2>/dev/null \
    | grep -B4 "\"displayName\" : \"${display_name}\"" \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' \
    | tail -n 1
}

update_browser_execution_requirement() {
  local realm_name="$1"
  local execution_id="$2"
  local requirement="$3"
  local payload_file

  payload_file="$(mktemp)"
  cat > "${payload_file}" <<EOF
{
  "id": "${execution_id}",
  "requirement": "${requirement}"
}
EOF

  if /opt/keycloak/bin/kcadm.sh update authentication/flows/browser/executions -r "${realm_name}" -f "${payload_file}" >/dev/null 2>&1; then
    rm -f "${payload_file}"
    return 0
  fi

  rm -f "${payload_file}"
  return 1
}

set_browser_execution_requirement_by_name() {
  local realm_name="$1"
  local display_name="$2"
  local requirement="$3"
  local execution_id

  execution_id="$(resolve_browser_execution_id_by_name "${realm_name}" "${display_name}")"
  if [ -z "${execution_id}" ]; then
    echo "[keycloak-init-realms] Realm ${realm_name}: browser execution '${display_name}' not found; nothing to update."
    return 0
  fi

  if update_browser_execution_requirement "${realm_name}" "${execution_id}" "${requirement}"; then
    echo "[keycloak-init-realms] Realm ${realm_name}: browser execution '${display_name}' set to ${requirement}."
    return 0
  fi

  echo "[keycloak-init-realms] Realm ${realm_name}: failed to set browser execution '${display_name}' to ${requirement}." >&2
  return 1
}

disable_shared_realm_identity_first_login() {
  local display_name

  for display_name in "Organization" "Organization Identity-First Login"; do
    if ! set_browser_execution_requirement_by_name "${SHARED_REALM}" "${display_name}" "DISABLED"; then
      return 1
    fi
  done
}

ensure_shared_realm_single_page_login() {
  if ! set_browser_execution_requirement_by_name "${SHARED_REALM}" "Username" "DISABLED"; then
    return 1
  fi

  if ! set_browser_execution_requirement_by_name "${SHARED_REALM}" "Username Password Form" "REQUIRED"; then
    return 1
  fi
}

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

echo "[keycloak-init-realms] Setting sslRequired=NONE on realms master, ${SHARED_REALM}..."
for realm in master "${SHARED_REALM}"; do
  if /opt/keycloak/bin/kcadm.sh update realms/${realm} -s sslRequired=NONE 2>/dev/null; then
    echo "[keycloak-init-realms] Realm ${realm}: sslRequired=NONE set successfully."
  else
    echo "[keycloak-init-realms] Realm ${realm}: update failed or realm does not exist." >&2
  fi
done
if /opt/keycloak/bin/kcadm.sh update "realms/${SHARED_REALM}" \
  -s organizationsEnabled=true \
  -s registrationEmailAsUsername=false \
  -s loginWithEmailAllowed=false 2>/dev/null; then
  echo "[keycloak-init-realms] Realm ${SHARED_REALM}: organizations and username-only login policy set successfully."
else
  echo "[keycloak-init-realms] Realm ${SHARED_REALM}: failed to enforce organizations and username-only login policy." >&2
fi
ensure_shared_realm_spoke_client_scope
remove_shared_realm_legacy_root_group_mappers
ensure_default_organization
ensure_all_organization_role_groups "${SHARED_REALM}"
ensure_default_organization_seed_members
ensure_default_organization_seed_roles
remove_default_organization_seed_user_realm_roles "${SHARED_REALM}"
disable_shared_realm_identity_first_login
ensure_shared_realm_single_page_login
echo "[keycloak-init-realms] Realm configuration complete."
