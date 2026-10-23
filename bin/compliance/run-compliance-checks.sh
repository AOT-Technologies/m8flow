#!/usr/bin/env bash
# Runs the licensing, secret, SAST, and vulnerability checks that CI runs in
# .github/workflows/compliance.yml and secret-scan.yml, from the repository root.
#
# Needs uv, Node.js with npm, and gitleaks on PATH. The license inventory reads
# installed node_modules, so the script runs `npm ci` in m8flow-bpmn and
# m8flow-designer first unless SKIP_NPM_INSTALL=1.
#
# Usage: bin/compliance/run-compliance-checks.sh [--write-dependencies]
#   --write-dependencies  also regenerate DEPENDENCIES.md

set -euo pipefail

cd "$(dirname "$0")/../.."

REUSE_VERSION="5.0.2"
BANDIT_VERSION="1.8.6"
PIP_AUDIT_VERSION="2.7.3"

# Python source shipped in images; tests are excluded.
BANDIT_PATHS=(
  m8flow-backend/src
  m8flow-mcp/src
  m8flow-nats-consumer
  m8flow-node-wire-proxy/src
  m8flow-connector-proxy
  m8flow-telemetry/src
)

write_dependencies=false
[[ "${1:-}" == "--write-dependencies" ]] && write_dependencies=true

status=0
step() { printf '\n==> %s\n' "$1"; }
fail() { echo "FAILED: $1"; status=1; }

step "REUSE lint (every file has a copyright and license)"
uvx "reuse==${REUSE_VERSION}" lint || fail "reuse lint"

step "Files with licenses that block an open-source release"
if grep -nE 'LicenseRef-(FontAwesome-Pro|NeedsReview)' REUSE.toml; then
  echo "WARNING: REUSE.toml still declares files that are not redistributable or not yet reviewed."
fi

step "Bandit SAST (fails on high severity)"
uvx "bandit==${BANDIT_VERSION}" -q -r "${BANDIT_PATHS[@]}" \
  -x '*/tests/*,*/.venv/*' --severity-level high || fail "bandit"

step "Gitleaks (full history)"
if command -v gitleaks >/dev/null; then
  gitleaks git . --redact --no-banner || fail "gitleaks"
else
  echo "gitleaks not installed; skipping (CI runs it in secret-scan.yml)."
fi

step "pip-audit (runtime dependencies of each Python service)"
requirements="$(mktemp)"
trap 'rm -f "${requirements}"' EXIT
for project in m8flow-backend m8flow-mcp m8flow-nats-consumer m8flow-node-wire-proxy; do
  echo "--- ${project}"
  (cd "${project}" && uv export --frozen --no-dev --no-hashes --no-emit-project \
    --no-emit-package m8flow-bpmn-core --no-emit-package m8flow-telemetry) \
    | grep -vE '^(-e |\.|/)' > "${requirements}"
  uvx --python 3.12 "pip-audit==${PIP_AUDIT_VERSION}" -r "${requirements}" \
    --no-deps --disable-pip --progress-spinner off || fail "pip-audit (${project})"
done

step "npm audit (m8flow-designer production dependencies, high and critical)"
(cd m8flow-designer && npm audit --omit=dev --audit-level=high) || fail "npm audit"

step "Dependency licenses"
if [[ "${SKIP_NPM_INSTALL:-0}" != "1" ]]; then
  (cd m8flow-bpmn && npm ci --ignore-scripts --no-audit --no-fund)
  (cd m8flow-designer && npm ci --ignore-scripts --no-audit --no-fund)
fi
license_args=(--check)
${write_dependencies} && license_args+=(--write)
python3 bin/compliance/dependency_licenses.py "${license_args[@]}" || fail "dependency licenses"

echo
if [[ "${status}" -ne 0 ]]; then
  echo "Compliance checks failed."
else
  echo "Compliance checks passed."
fi
exit "${status}"
