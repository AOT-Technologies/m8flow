#!/usr/bin/env bash
# Run with bash/jq, or inside the Keycloak image with the repo mounted read-only.
set -euo pipefail
source "${1:-$(dirname "$0")/../keycloak-login-flow.sh}"
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

# Asserts every id in the given object has that requirement in the mock state.
expect() {
  jq -e --argjson want "$1" 'INDEX(.id) as $by | all($want | to_entries[]; $by[.key].requirement == .value)' \
    "${MOCK_FLOW_STATE}" > /dev/null || { echo "unexpected flow state for: $1" >&2; cat "${MOCK_FLOW_STATE}" >&2; exit 1; }
}
count() { [ -f "$1" ] && wc -l < "$1" || echo 0; }
reset_counters() { rm -f "${MOCK_FLOW_UPDATES}" "${MOCK_FLOW_READS}"; }

# Keycloak 26 default browser flow plus a username-first step, in kcadm's
# depth-first order. Compact JSON avoids kcadm whitespace/field order assumptions.
cat > "${test_dir}/default.json" <<'JSON'
[{"id":"cookie","providerId":"auth-cookie","requirement":"ALTERNATIVE","level":0},
 {"id":"idp","providerId":"identity-provider-redirector","requirement":"ALTERNATIVE","level":0},
 {"id":"org","authenticationFlow":true,"displayName":"Organization","requirement":"ALTERNATIVE","level":0},
 {"id":"org-cond","authenticationFlow":true,"displayName":"Browser - Conditional Organization","requirement":"CONDITIONAL","level":1},
 {"id":"org-cond-user","providerId":"conditional-user-configured","requirement":"REQUIRED","level":2},
 {"id":"identity","providerId":"organization","requirement":"REQUIRED","level":2},
 {"id":"forms","authenticationFlow":true,"displayName":"forms","requirement":"ALTERNATIVE","level":0},
 {"id":"username","providerId":"auth-username-form","requirement":"REQUIRED","level":1},
 {"id":"password","providerId":"auth-username-password-form","requirement":"ALTERNATIVE","level":1},
 {"id":"otp-flow","authenticationFlow":true,"displayName":"Browser - Conditional OTP","requirement":"CONDITIONAL","level":1},
 {"id":"otp-cond","providerId":"conditional-user-configured","requirement":"REQUIRED","level":2},
 {"id":"otp","providerId":"auth-otp-form","requirement":"REQUIRED","level":2}]
JSON
cp "${test_dir}/default.json" "${MOCK_FLOW_STATE}"
ensure_realm_single_page_login m8flow
expect '{"cookie":"ALTERNATIVE","idp":"ALTERNATIVE","org":"DISABLED","org-cond":"DISABLED","org-cond-user":"REQUIRED",
  "identity":"DISABLED","forms":"ALTERNATIVE","username":"DISABLED","password":"REQUIRED","otp-flow":"CONDITIONAL","otp":"REQUIRED"}'
[ "$(count "${MOCK_FLOW_UPDATES}")" -eq 5 ]
[ "$(count "${MOCK_FLOW_READS}")" -eq 2 ]
# Already configured: verified from a single read, no writes.
ensure_realm_single_page_login master
[ "$(count "${MOCK_FLOW_UPDATES}")" -eq 5 ]
[ "$(count "${MOCK_FLOW_READS}")" -eq 3 ]

# A custom subflow merely named "Organization" (no organization authenticator) is untouched,
# and a Username Form in another branch is left alone instead of being rewired.
reset_counters
cat > "${MOCK_FLOW_STATE}" <<'JSON'
[{"id":"custom","authenticationFlow":true,"displayName":"Organization","requirement":"ALTERNATIVE","level":0},
 {"id":"custom-user","providerId":"auth-username-form","requirement":"REQUIRED","level":1},
 {"id":"custom-otp","providerId":"auth-otp-form","requirement":"REQUIRED","level":1},
 {"id":"forms","authenticationFlow":true,"requirement":"ALTERNATIVE","level":0},
 {"id":"password","providerId":"auth-username-password-form","requirement":"REQUIRED","level":1}]
JSON
ensure_realm_single_page_login m8flow 2> "${test_dir}/stderr"
expect '{"custom":"ALTERNATIVE","custom-user":"REQUIRED","custom-otp":"REQUIRED","password":"REQUIRED"}'
grep -q 'custom-user is outside the password form branch' "${test_dir}/stderr"
[ "$(count "${MOCK_FLOW_UPDATES}")" -eq 0 ]

# An organization step sharing a subflow with another authenticator disables only itself.
cat > "${MOCK_FLOW_STATE}" <<'JSON'
[{"id":"mixed","authenticationFlow":true,"requirement":"ALTERNATIVE","level":0},
 {"id":"identity","providerId":"organization","requirement":"REQUIRED","level":1},
 {"id":"webauthn","providerId":"webauthn-authenticator-passwordless","requirement":"REQUIRED","level":1},
 {"id":"forms","authenticationFlow":true,"requirement":"ALTERNATIVE","level":0},
 {"id":"password","providerId":"auth-username-password-form","requirement":"REQUIRED","level":1}]
JSON
ensure_realm_single_page_login m8flow
expect '{"mixed":"ALTERNATIVE","identity":"DISABLED","webauthn":"REQUIRED","forms":"ALTERNATIVE"}'

# The password form's own branch is never disabled, even if it holds the organization step.
cat > "${MOCK_FLOW_STATE}" <<'JSON'
[{"id":"forms","authenticationFlow":true,"requirement":"ALTERNATIVE","level":0},
 {"id":"identity","providerId":"organization","requirement":"ALTERNATIVE","level":1},
 {"id":"password","providerId":"auth-username-password-form","requirement":"REQUIRED","level":1}]
JSON
ensure_realm_single_page_login m8flow
expect '{"forms":"ALTERNATIVE","identity":"DISABLED","password":"REQUIRED"}'

# Structures that cannot be configured safely fail without any write.
reset_counters
refuse() {
  jq -c "$1" "${test_dir}/default.json" > "${MOCK_FLOW_STATE}"
  if ensure_realm_single_page_login m8flow 2>/dev/null; then echo "accepted: $1" >&2; exit 1; fi
  [ "$(count "${MOCK_FLOW_UPDATES}")" -eq 0 ]
}
refuse 'map(select(.id != "password"))'
refuse '. + [{"id":"password2","providerId":"auth-username-password-form","requirement":"REQUIRED","level":0}]'
refuse 'map(if .id == "forms" then .requirement = "DISABLED" else . end)'
refuse 'map(del(.level))'
refuse 'map(if .id == "org-cond" then .level = 3 else . end)'

export MOCK_READ_FAILURE=true
cp "${test_dir}/default.json" "${MOCK_FLOW_STATE}"
if ensure_realm_single_page_login m8flow; then exit 1; fi
unset MOCK_READ_FAILURE

export MOCK_IGNORE_UPDATE=true
if ensure_realm_single_page_login m8flow; then exit 1; fi
unset MOCK_IGNORE_UPDATE
export MOCK_UPDATE_FAILURE=true
if ensure_realm_single_page_login m8flow; then exit 1; fi
unset MOCK_UPDATE_FAILURE

# A failed read-back must fail readiness even if the update itself succeeded.
export MOCK_FAIL_READ_NUMBER=$(( $(count "${MOCK_FLOW_READS}") + 2 ))
if ensure_realm_single_page_login m8flow; then exit 1; fi
[ "$(count "${MOCK_FLOW_READS}")" -eq "${MOCK_FAIL_READ_NUMBER}" ]
unset MOCK_FAIL_READ_NUMBER
printf '%s\n' '13 login-flow regression scenarios passed.'
