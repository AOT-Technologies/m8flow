#!/bin/sh
set -eu

keycloak_http_port="${KC_HTTP_PORT:-8080}"
keycloak_url="${KEYCLOAK_INTERNAL_URL:-http://keycloak:${keycloak_http_port}}"
keycloak_admin_user="${KEYCLOAK_ADMIN:-admin}"
keycloak_admin_password="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
keycloak_super_admin_user="${KEYCLOAK_SUPER_ADMIN_USER:-super-admin}"
keycloak_super_admin_password="${KEYCLOAK_SUPER_ADMIN_PASSWORD:-super-admin}"
keycloak_client_id="${M8FLOW_KEYCLOAK_SPOKE_CLIENT_ID:-spiffworkflow-backend}"
keycloak_client_secret="${M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET:-${M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET:-JXeQExm0JhQPLumgHtIIqf52bDalHz0q}}"
backend_public_url="${SPIFFWORKFLOW_BACKEND_URL:-${M8FLOW_BACKEND_URL:-http://localhost:8000}}"
frontend_public_url="${SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND:-${M8FLOW_BACKEND_URL_FOR_FRONTEND:-http://localhost:8001}}"
backend_redirect_uri="${backend_public_url%/}/*"
frontend_logout_redirect_uri="${frontend_public_url%/}/*"

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

echo ":: Ensuring master realm super-admin role/user..."
/opt/keycloak/bin/kcadm.sh get roles/super-admin -r master >/dev/null 2>&1 \
  || /opt/keycloak/bin/kcadm.sh create roles -r master -s name=super-admin >/dev/null

client_id=$(
  /opt/keycloak/bin/kcadm.sh get clients -r master -q clientId="${keycloak_client_id}" --fields id,clientId \
    | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    | head -n 1
)

if [ -z "${client_id}" ]; then
  /opt/keycloak/bin/kcadm.sh create clients -r master \
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
    /opt/keycloak/bin/kcadm.sh get clients -r master -q clientId="${keycloak_client_id}" --fields id,clientId \
      | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
      | head -n 1
  )
fi

if [ -z "${client_id}" ]; then
  echo >&2 "ERROR: Failed to resolve master realm client id for ${keycloak_client_id}"
  exit 1
fi

/opt/keycloak/bin/kcadm.sh update "clients/${client_id}" -r master \
  -s secret="${keycloak_client_secret}" \
  -s standardFlowEnabled=true \
  -s directAccessGrantsEnabled=true \
  -s serviceAccountsEnabled=true \
  -s fullScopeAllowed=true \
  -s "redirectUris=[\"${backend_redirect_uri}\"]" \
  -s "webOrigins=[\"${frontend_public_url%/}\"]" \
  -s "attributes.\"post.logout.redirect.uris\"=${frontend_logout_redirect_uri}" \
  >/dev/null

if ! /opt/keycloak/bin/kcadm.sh get "clients/${client_id}/protocol-mappers/models" -r master 2>/dev/null | grep -q '"name" : "groups"\|"name":"groups"'; then
  /opt/keycloak/bin/kcadm.sh create "clients/${client_id}/protocol-mappers/models" -r master \
    -s name=groups \
    -s protocol=openid-connect \
    -s protocolMapper=oidc-usermodel-realm-role-mapper \
    -s consentRequired=false \
    -s 'config."introspection.token.claim"=true' \
    -s 'config.multivalued=true' \
    -s 'config."userinfo.token.claim"=true' \
    -s 'config."id.token.claim"=true' \
    -s 'config."access.token.claim"=true' \
    -s 'config."claim.name"=groups' \
    -s 'config."jsonType.label"=String' \
    >/dev/null
fi

/opt/keycloak/bin/kcadm.sh create users -r master \
  -s username="${keycloak_super_admin_user}" \
  -s enabled=true \
  -s firstName=Super \
  -s lastName=Admin >/dev/null 2>&1 || true

/opt/keycloak/bin/kcadm.sh set-password \
  -r master \
  --username "${keycloak_super_admin_user}" \
  --new-password "${keycloak_super_admin_password}" >/dev/null

/opt/keycloak/bin/kcadm.sh add-roles \
  -r master \
  --uusername "${keycloak_super_admin_user}" \
  --rolename super-admin >/dev/null 2>&1 || true

echo ":: Master realm client, role, and super-admin ensured."
