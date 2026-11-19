#!/usr/bin/env bash
# Run with bash/jq, or inside the Keycloak image with the repo mounted read-only.
set -euo pipefail
source "$(dirname "$0")/../keycloak-login-flow.sh"
test_dir="$(mktemp -d)"
trap 'rm -rf "${test_dir}"' EXIT
export MOCK_FLOW_STATE="${test_dir}/flow.json"
export MOCK_FLOW_UPDATES="${test_dir}/updates"
export MOCK_FLOW_READS="${test_dir}/reads"
export M8FLOW_KEYCLOAK_KCADM_BIN="${test_dir}/kcadm"
cat > "${M8FLOW_KEYCLOAK_KCADM_BIN}" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  get)
    printf '%s\n' get >> "${MOCK_FLOW_READS}"
    [ "${MOCK_READ_FAILURE:-false}" != true ] || exit 1
    [ "$(wc -l < "${MOCK_FLOW_READS}")" -ne "${MOCK_FAIL_READ_NUMBER:-0}" ] || exit 1
    cat "${MOCK_FLOW_STATE}"
    ;;
  update)
    [ "${MOCK_UPDATE_FAILURE:-false}" != true ] || exit 1
    [ "${MOCK_IGNORE_UPDATE:-false}" != true ] || exit 0
    while [ "$1" != '-f' ]; do shift; done
    jq --slurpfile change "$2" 'map(if .id == $change[0].id then .requirement = $change[0].requirement else . end)' \
      "${MOCK_FLOW_STATE}" > "${MOCK_FLOW_STATE}.new"
    mv "${MOCK_FLOW_STATE}.new" "${MOCK_FLOW_STATE}"
    printf '%s\n' updated >> "${MOCK_FLOW_UPDATES}"
    ;;
  *) exit 2 ;;
esac
MOCK
chmod +x "${M8FLOW_KEYCLOAK_KCADM_BIN}"
# Compact JSON deliberately avoids kcadm's whitespace/field order assumptions.
cat > "${MOCK_FLOW_STATE}" <<'JSON'
[{"id":"cookie","providerId":"auth-cookie","requirement":"ALTERNATIVE"},{"id":"org","authenticationFlow":true,"displayName":"Organization","requirement":"ALTERNATIVE"},{"id":"identity","providerId":"organization","requirement":"ALTERNATIVE"},{"id":"username","providerId":"auth-username-form","requirement":"REQUIRED"},{"id":"password","providerId":"auth-username-password-form","requirement":"REQUIRED"},{"id":"otp","providerId":"auth-otp-form","requirement":"REQUIRED"}]
JSON
ensure_realm_single_page_login m8flow
jq -e 'all(.[]; if .id == "cookie" then .requirement == "ALTERNATIVE" elif .id == "password" or .id == "otp" then .requirement == "REQUIRED" else .requirement == "DISABLED" end)' "${MOCK_FLOW_STATE}" > /dev/null
[ "$(wc -l < "${MOCK_FLOW_UPDATES}")" -eq 3 ]
[ "$(wc -l < "${MOCK_FLOW_READS}")" -eq 2 ]
ensure_realm_single_page_login master
[ "$(wc -l < "${MOCK_FLOW_UPDATES}")" -eq 3 ]
[ "$(wc -l < "${MOCK_FLOW_READS}")" -eq 3 ]

export MOCK_READ_FAILURE=true
if ensure_realm_single_page_login m8flow; then exit 1; fi
unset MOCK_READ_FAILURE

cp "${MOCK_FLOW_STATE}" "${test_dir}/valid.json"
jq 'map(select(.id != "password"))' "${test_dir}/valid.json" > "${MOCK_FLOW_STATE}"
if ensure_realm_single_page_login m8flow; then exit 1; fi

jq 'map(if .id == "identity" then .requirement = "ALTERNATIVE" else . end)' \
  "${test_dir}/valid.json" > "${MOCK_FLOW_STATE}"
export MOCK_IGNORE_UPDATE=true
if ensure_realm_single_page_login m8flow; then exit 1; fi
unset MOCK_IGNORE_UPDATE
export MOCK_UPDATE_FAILURE=true
if ensure_realm_single_page_login m8flow; then exit 1; fi
unset MOCK_UPDATE_FAILURE

# A failed read-back must fail readiness even if the update itself succeeded.
export MOCK_FAIL_READ_NUMBER=$(( $(wc -l < "${MOCK_FLOW_READS}") + 2 ))
if ensure_realm_single_page_login m8flow; then exit 1; fi
[ "$(wc -l < "${MOCK_FLOW_READS}")" -eq "${MOCK_FAIL_READ_NUMBER}" ]
unset MOCK_FAIL_READ_NUMBER
printf '%s\n' '7 login-flow regression scenarios passed.'
