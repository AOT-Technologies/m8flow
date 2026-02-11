#!/usr/bin/env bash
# Equivalent of: cd spiffworkflow-backend && uv sync && ./bin/recreate_db clean && ./bin/run_server_locally
# but for the m8flow extensions app: sync deps, run DB migrations, then start the backend.
# Run from repo root, or from anywhere (script will cd to repo root).
# Requires: .env at repo root with M8FLOW_BACKEND_DATABASE_URI (and optionally M8FLOW_BACKEND_UPGRADE_DB=true).

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../.." && pwd)"
cd "$repo_root"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  echo "Loaded .env"
fi

echo ":: Syncing backend dependencies (spiffworkflow-backend)..."
cd "$repo_root/spiffworkflow-backend"
uv sync
cd "$repo_root"

# Run SpiffWorkflow schema migrations (creates/updates their tables)
if [[ "${M8FLOW_BACKEND_UPGRADE_DB:-}" == "true" ]]; then
  echo ":: Running SpiffWorkflow DB migrations (flask db upgrade)..."
  cd "$repo_root/spiffworkflow-backend"
  uv run flask db upgrade
  cd "$repo_root"
  echo ":: M8Flow migrations run automatically when the app starts (extensions/app.py)."
fi

export PYTHONPATH="$repo_root:$repo_root/extensions/m8flow-backend/src:$repo_root/spiffworkflow-backend/src"
BACKEND_PORT="${M8FLOW_BACKEND_PORT:-7000}"
export UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-debug}"

echo ":: Starting backend (extensions app) on port $BACKEND_PORT..."
cd "$repo_root/spiffworkflow-backend"
exec uv run uvicorn extensions.app:app \
  --reload \
  --host "0.0.0.0" \
  --port "$BACKEND_PORT" \
  --workers 1 \
  --log-level "$UVICORN_LOG_LEVEL"
