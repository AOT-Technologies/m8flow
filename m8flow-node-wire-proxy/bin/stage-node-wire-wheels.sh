#!/usr/bin/env bash
## Stage node-wire runtime + http_generic wheels into this proxy tree (no PyPI).
##
## Usage (from repo root or this script's location):
##   m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
##   NODE_WIRE_ROOT=/path/to/node-wire m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
##
## Optional: rebuild before staging:
##   STAGE_REBUILD=1 m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
##
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PROXY_ROOT/.." && pwd)"
NODE_WIRE_ROOT="${NODE_WIRE_ROOT:-$REPO_ROOT/../node-wire}"
STAGE_DIR="$PROXY_ROOT/vendor/wheels"
VERSION="${NODE_WIRE_VERSION:-1.0.0}"

if [[ ! -d "$NODE_WIRE_ROOT" ]]; then
  echo "ERROR: node-wire checkout not found at $NODE_WIRE_ROOT" >&2
  echo "Set NODE_WIRE_ROOT to the sibling checkout." >&2
  exit 1
fi

if [[ "${STAGE_REBUILD:-0}" == "1" ]]; then
  echo "=== Rebuilding packages/runtime + packages/connectors/http_generic ==="
  # Default build-packages.sh installs latest Cython in the Linux container;
  # Cython 3.3 currently fails compiling node_wire_runtime/base_connector.py.
  # Prefer the scripted path first; if Linux runtime fails, rebuild runtime with cython<3.2.
  if ! (
    cd "$NODE_WIRE_ROOT"
    ./scripts/build-packages.sh packages/runtime packages/connectors/http_generic
  ); then
    echo "WARN: build-packages.sh failed; retrying Linux runtime with Cython pin <3.2" >&2
    (
      cd "$NODE_WIRE_ROOT"
      # Host wheel (always needed for local macOS)
      (cd packages/runtime && python3 -m build --wheel --no-isolation)
      docker run --rm \
        -v "$NODE_WIRE_ROOT:/work" \
        -w /work/packages/runtime \
        python:3.12-slim \
        bash -lc 'apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential >/dev/null \
          && python -m pip install -q --no-cache-dir "setuptools>=69" "cython>=3.0,<3.2" wheel build \
          && python -m build --wheel --no-isolation'
      ./scripts/build-packages.sh packages/connectors/http_generic || {
        (cd packages/connectors/http_generic && python3 -m build --wheel --no-isolation)
        docker run --rm \
          -v "$NODE_WIRE_ROOT:/work" \
          -w /work/packages/connectors/http_generic \
          python:3.12-slim \
          bash -lc 'apt-get update -qq && apt-get install -y -qq --no-install-recommends build-essential >/dev/null \
            && python -m pip install -q --no-cache-dir "setuptools>=69" "cython>=3.0,<3.2" wheel build \
            && python -m build --wheel --no-isolation'
      }
    )
  fi
fi

mkdir -p "$STAGE_DIR"
shopt -s nullglob
RUNTIME_WHEELS=(
  "$NODE_WIRE_ROOT/packages/runtime/dist/node_wire_runtime-${VERSION}"-*.whl
)
HTTP_WHEELS=(
  "$NODE_WIRE_ROOT/packages/connectors/http_generic/dist/node_wire_http_generic-${VERSION}"-*.whl
)
shopt -u nullglob

if [[ ${#RUNTIME_WHEELS[@]} -eq 0 || ${#HTTP_WHEELS[@]} -eq 0 ]]; then
  echo "ERROR: missing ${VERSION} wheels under $NODE_WIRE_ROOT packages/*/dist" >&2
  echo "Build with: (cd $NODE_WIRE_ROOT && ./scripts/build-packages.sh packages/runtime packages/connectors/http_generic)" >&2
  echo "If Linux runtime fails on Cython 3.3, pin cython<3.2 in the Docker build (see vendor/wheels/README.md)." >&2
  exit 1
fi

# Drop previous staged wheels so pip/Docker do not pick stale 0.1.0 tags.
rm -f "$STAGE_DIR"/*.whl
cp -f "${RUNTIME_WHEELS[@]}" "${HTTP_WHEELS[@]}" "$STAGE_DIR/"

echo "Staged into $STAGE_DIR:"
ls -lh "$STAGE_DIR"/*.whl
