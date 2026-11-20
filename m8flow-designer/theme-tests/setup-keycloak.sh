#!/usr/bin/env bash
# Run ONLY inside the disposable container described in README.md.
set -euo pipefail
kc=/opt/keycloak/bin/kcadm.sh
"$kc" config credentials --server http://localhost:8080 --realm master \
  --user theme-test-admin --password theme-test-only-password
"$kc" create realms -s realm=m8flow -s enabled=true -s loginTheme=m8flow
for realm in m8flow master; do
  "$kc" update "realms/$realm" -s loginTheme=m8flow -s sslRequired=none
  "$kc" create clients -r "$realm" -s clientId=theme-test -s enabled=true \
    -s publicClient=true -s 'redirectUris=["http://localhost:16842/callback"]'
  "$kc" create users -r "$realm" -s username=theme-editor -s enabled=true \
    -s firstName=Theme -s lastName=Editor -s email=theme-editor@example.test
  "$kc" set-password -r "$realm" --username theme-editor --new-password theme-test-password
  "$kc" create authentication/flows -r "$realm" -s alias=theme-username \
    -s providerId=basic-flow -s topLevel=true -s builtIn=false
  "$kc" create authentication/flows/theme-username/executions/execution -r "$realm" \
    -s provider=auth-username-form
  execution_id="$("$kc" get authentication/flows/theme-username/executions -r "$realm" | jq -r '.[0].id')"
  "$kc" update authentication/flows/theme-username/executions -r "$realm" --no-merge \
    -s "id=$execution_id" -s requirement=REQUIRED
  flow_id="$("$kc" get authentication/flows -r "$realm" | jq -r '.[] | select(.alias == "theme-username") | .id')"
  "$kc" create clients -r "$realm" -s clientId=theme-username -s enabled=true \
    -s publicClient=true -s 'redirectUris=["http://localhost:16842/callback"]' \
    -s "authenticationFlowBindingOverrides={\"browser\":\"$flow_id\"}"
done
