#!/usr/bin/env bash
# Adds the m8flow SPDX copyright and license header to the given files, in the
# comment style of each file type. Files that already have one are left alone.
#
# Usage: bin/compliance/add-license-headers.sh <file>...
#   e.g. bin/compliance/add-license-headers.sh $(git diff --name-only --diff-filter=A main)

set -euo pipefail

REUSE_VERSION="5.0.2"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <file>..." >&2
  exit 2
fi

files=()
for file in "$@"; do
  [[ -f "${file}" ]] || continue
  # No comment syntax: REUSE.toml declares their license instead of a
  # .license sidecar file.
  case "${file}" in
    *.json|*.lock|*.png|*.jpg|*.jpeg|*.gif|*.webp|*.ico|*.svg|*.woff|*.woff2|*.ttf|*.eot|*.zip|*.whl|*.bpmn|*.dmn|*.xml) continue ;;
  esac
  grep -q 'SPDX-License-Identifier' "${file}" && continue
  files+=("${file}")
done
[[ ${#files[@]} -eq 0 ]] && { echo "Every file already has a header."; exit 0; }

annotate() {
  uvx "reuse==${REUSE_VERSION}" annotate --copyright "AOT Technologies Inc." --year "$(date +%Y)" \
    --license Apache-2.0 --copyright-prefix spdx "$@"
}

# reuse doesn't recognize the `*.Dockerfile` naming, so give those `#` comments.
dockerfiles=() others=()
for file in "${files[@]}"; do
  case "${file}" in
    *.Dockerfile) dockerfiles+=("${file}") ;;
    *) others+=("${file}") ;;
  esac
done
[[ ${#dockerfiles[@]} -gt 0 ]] && annotate --style python "${dockerfiles[@]}"
[[ ${#others[@]} -gt 0 ]] && annotate --skip-unrecognised "${others[@]}"
exit 0
