#!/usr/bin/env bash
# bin/fetch-upstream.sh
# Fetches upstream directories into local working tree.
# These directories are gitignored and must be fetched before running the app.
#
# Usage: ./bin/fetch-upstream.sh [tag]   (default tag from upstream.sources.json)
#   tag: git tag (e.g. 0.0.1-rc)

function error_handler() {
  >&2 echo "Exited with BAD EXIT CODE '${2}' in ${0} script at line: ${1}."
  exit "$2"
}
trap 'error_handler ${LINENO} $?' ERR
set -o errtrace -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
UPSTREAM_CONFIG_FILE="${REPO_ROOT}/upstream.sources.json"

if ! command -v jq >/dev/null 2>&1; then
  >&2 echo "jq is required but not installed. Please install jq and retry."
  exit 1
fi

if [[ ! -f "${UPSTREAM_CONFIG_FILE}" ]]; then
  >&2 echo "Missing upstream config file: ${UPSTREAM_CONFIG_FILE}"
  exit 1
fi

UPSTREAM_URL="$(jq -r '.upstream_url' "${UPSTREAM_CONFIG_FILE}")"
DEFAULT_UPSTREAM_TAG="$(jq -r '.upstream_ref' "${UPSTREAM_CONFIG_FILE}")"
UPSTREAM_TAG="${1:-${DEFAULT_UPSTREAM_TAG}}"

mapfile -t DIRS < <(
  jq -r '
    [
      (.backend // [])[],
      (.frontend // [])[],
      (.others // [])[]
    ]
    | map(select(type == "string" and length > 0))
    | unique
    | .[]
  ' "${UPSTREAM_CONFIG_FILE}"
)

if [[ "${UPSTREAM_URL}" == "null" || -z "${UPSTREAM_URL}" ]]; then
  >&2 echo "Invalid upstream_url in ${UPSTREAM_CONFIG_FILE}"
  exit 1
fi

if [[ "${UPSTREAM_TAG}" == "null" || -z "${UPSTREAM_TAG}" ]]; then
  >&2 echo "upstream_ref is missing or null in ${UPSTREAM_CONFIG_FILE}"
  exit 1
fi

if [[ ${#DIRS[@]} -eq 0 ]]; then
  >&2 echo "No folders configured in backend/frontend/others of ${UPSTREAM_CONFIG_FILE}"
  exit 1
fi

CLONE_DIR=$(mktemp -d)
trap 'rm -rf "$CLONE_DIR"' EXIT

echo "Fetching upstream ${UPSTREAM_URL} @ ${UPSTREAM_TAG} ..."
git clone --no-local --depth 1 --filter=blob:none --sparse \
    --branch "${UPSTREAM_TAG}" "${UPSTREAM_URL}" "${CLONE_DIR}/upstream"

cd "${CLONE_DIR}/upstream"
git sparse-checkout set "${DIRS[@]}"

FETCHED_SHA=$(git rev-parse HEAD)
echo "Fetched SHA: ${FETCHED_SHA}"

cd "${REPO_ROOT}"
for dir in "${DIRS[@]}"; do
    echo "Copying ${dir}/ ..."
    rm -rf "${dir}"
    cp -r "${CLONE_DIR}/upstream/${dir}" "${dir}"
done

echo ""
echo "Done. Upstream SHA: ${FETCHED_SHA}"
echo "Record this SHA to track which upstream version is in use."
echo "Upstream directories are gitignored — do not commit them."
