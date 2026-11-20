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

# Reads kcadm's flattened executions (depth-first, with .level) and prints
# {error} or {changes: [[id, requirement]], warnings}. Executions are matched by
# providerId and tree position only; display names are never trusted.
_keycloak_login_flow_plan() {
  jq -c '
    def plan:
      . as $e
      | [range(0; length) as $i | $e[$i] + {parent: (
          if $e[$i].level == 0 then null
          else [range(0; $i) | select($e[.].level == $e[$i].level - 1)] | last
            | if . == null then null else $e[.].id end
          end)}] as $x
      | (reduce $x[] as $r ({}; .[$r.id] = $r)) as $by
      | if any($x[]; .level > 0 and .parent == null) then {error: "browser flow tree is malformed"}
        else
          def anc($id): $by[$id].parent as $p | if $p == null then [] else [$p] + anc($p) end;
          [$x[] | select(.providerId == "auth-username-password-form")] as $upf
          | if ($upf | length) != 1 then
              {error: "expected exactly one Username Password Form, found \($upf | length)"}
            else
              $upf[0] as $u | anc($u.id) as $ua
              | if any($ua[]; $by[.].requirement == "DISABLED") then
                  {error: "Username Password Form is inside a disabled branch"}
                else
                  # A subflow above the organization step is disabled only when it is not on the
                  # password form path and runs nothing but organization identity-first/conditions.
                  def only_org($s): all($x[] | select(.authenticationFlow != true)
                      | select(. as $r | any(anc($r.id)[]; . == $s));
                    .providerId == "organization" or ((.providerId // "") | startswith("conditional-")));
                  [$x[] | select(.providerId == "organization") | .id] as $org
                  | ([$org[] | anc(.)[]] | unique
                      | map(select(. as $a | (any($ua[]; . == $a) | not) and only_org($a)))) as $orgBranches
                  | ([[$u.id, "REQUIRED"]]
                      + [$x[] | select(.providerId == "auth-username-form" and .parent == $u.parent) | [.id, "DISABLED"]]
                      + [($org + $orgBranches)[] | [., "DISABLED"]]) as $want
                  | {changes: [$want[] | select($by[.[0]].requirement != .[1])],
                     warnings: [$x[] | select(.providerId == "auth-username-form" and .parent != $u.parent)
                       | "Username Form \(.id) is outside the password form branch; left unchanged"]}
                end
            end
        end;
    if type != "array" then {error: "browser flow executions are not a list"}
    elif any(.[]; (.level | type) != "number" or (.id | type) != "string") then
      {error: "browser flow executions lack id/level; cannot resolve branches"}
    else plan end
  '
}

ensure_realm_single_page_login() {
  local realm_name="$1"
  local executions plan error changes execution_id requirement payload

  if ! executions="$(_keycloak_get_browser_executions "${realm_name}")"; then
    echo "[keycloak-login] Cannot read browser flow for realm ${realm_name}." >&2
    return 1
  fi
  plan="$(printf '%s' "${executions}" | _keycloak_login_flow_plan)" || return 1
  # Unknown structures are refused rather than rewritten into a broken flow.
  error="$(printf '%s' "${plan}" | jq -r '.error // empty')"
  if [ -n "${error}" ]; then
    echo "[keycloak-login] Realm ${realm_name}: ${error}." >&2
    return 1
  fi
  printf '%s' "${plan}" | jq -r '.warnings[]' | while IFS= read -r warning; do
    echo "[keycloak-login] Realm ${realm_name}: ${warning}." >&2
  done

  changes="$(printf '%s' "${plan}" | jq -r '.changes[] | @tsv')" || return 1
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
    if ! executions="$(_keycloak_get_browser_executions "${realm_name}")" \
      || ! printf '%s' "${executions}" | _keycloak_login_flow_plan \
        | jq -e '.error == null and (.changes | length) == 0' >/dev/null; then
      echo "[keycloak-login] Realm ${realm_name} did not retain the combined login flow." >&2
      return 1
    fi
  fi
  echo "[keycloak-login] Realm ${realm_name}: Username Password Form verified; identity-first login disabled."
}
