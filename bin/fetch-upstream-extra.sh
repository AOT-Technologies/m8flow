#!/usr/bin/env bash
# bin/fetch-upstream-extra.sh
# Fetches ADDITIONAL upstream directories (beyond what bin/fetch-upstream.sh pulls)
# into the local working tree. Used by the upstream-copy license gate to compare
# against trees the default pull deliberately omits (e.g. connector-proxy-demo).
#
# This does NOT change bin/fetch-upstream.sh or the default upstream pull. It reuses
# the same upstream URL/ref from upstream.sources.json so the version stays pinned.
# The fetched dirs are gitignored (same as the other upstream trees) — do not commit.
#
# Usage: ./bin/fetch-upstream-extra.sh <dir> [<dir> ...]
#   e.g. ./bin/fetch-upstream-extra.sh connector-proxy-demo connector-proxies

function error_handler() {
  >&2 echo "Exited with BAD EXIT CODE '${2}' in ${0} script at line: ${1}."
  exit "$2"
}
trap 'error_handler ${LINENO} $?' ERR
set -o errtrace -o errexit -o nounset -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
UPSTREAM_CONFIG_FILE="${REPO_ROOT}/upstream.sources.json"

if [[ $# -eq 0 ]]; then
  >&2 echo "Usage: $0 <dir> [<dir> ...]"
  exit 1
fi

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
UPSTREAM_TAG="${UPSTREAM_REF_OVERRIDE:-${DEFAULT_UPSTREAM_TAG}}"

if [[ "${UPSTREAM_URL}" == "null" || -z "${UPSTREAM_URL}" ]]; then
  >&2 echo "Invalid upstream_url in ${UPSTREAM_CONFIG_FILE}"
  exit 1
fi
if [[ "${UPSTREAM_TAG}" == "null" || -z "${UPSTREAM_TAG}" ]]; then
  >&2 echo "upstream_ref is missing or null in ${UPSTREAM_CONFIG_FILE}"
  exit 1
fi

DIRS=("$@")

CLONE_DIR=$(mktemp -d)
trap 'rm -rf "$CLONE_DIR"' EXIT

echo "Fetching extra upstream dirs from ${UPSTREAM_URL} @ ${UPSTREAM_TAG}: ${DIRS[*]}"
git clone --no-local --depth 1 --filter=blob:none --sparse \
    --branch "${UPSTREAM_TAG}" "${UPSTREAM_URL}" "${CLONE_DIR}/upstream"

cd "${CLONE_DIR}/upstream"
git sparse-checkout set "${DIRS[@]}"

cd "${REPO_ROOT}"
for dir in "${DIRS[@]}"; do
    if [[ -d "${CLONE_DIR}/upstream/${dir}" ]]; then
        echo "Copying ${dir}/ ..."
        rm -rf "${dir}"
        cp -r "${CLONE_DIR}/upstream/${dir}" "${dir}"
    else
        echo "Note: ${dir}/ not present upstream — skipping."
    fi
done

echo "Done. Extra upstream dirs are gitignored — do not commit them."
