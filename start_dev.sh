#!/usr/bin/env bash
# Start backend and frontend for local development.
# Loads .env from repo root. Backend runs in background (skips cache refresh).
# When extensions/app.py exists, backend runs with the extensions app (tenant-login-url, etc.).
# Press Ctrl+C to stop the frontend; the script will also stop the backend.

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
  echo "Loaded .env"
fi

BACKEND_PID=""
cleanup() {
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Stopping backend (PID $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

BACKEND_PORT="${M8FLOW_BACKEND_PORT:-7000}"
export SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP="${SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP:-false}"

# Kill any existing process on backend port so we can bind to it
if command -v lsof >/dev/null 2>&1; then
  EXISTING_BACKEND_PIDS=$(lsof -ti :"$BACKEND_PORT" 2>/dev/null || true)
  if [[ -n "$EXISTING_BACKEND_PIDS" ]]; then
    echo "Killing existing process(es) on port $BACKEND_PORT: $EXISTING_BACKEND_PIDS"
    echo "$EXISTING_BACKEND_PIDS" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
fi

if [[ -f "$ROOT/extensions/app.py" ]]; then
  # Run SpiffWorkflow base migrations if UPGRADE_DB is enabled
  if [[ "${M8FLOW_BACKEND_UPGRADE_DB:-}" == "true" ]]; then
    echo "Running SpiffWorkflow database migrations..."
    (
      export PYTHONPATH="$ROOT:$ROOT/extensions/m8flow-backend/src:$ROOT/spiffworkflow-backend/src"
      cd "$ROOT/spiffworkflow-backend"
      uv run flask db upgrade
    )
    echo "SpiffWorkflow migrations complete."
  fi

  echo "Starting backend (extensions app) on port $BACKEND_PORT in background..."
  (
    # Include repo root, extensions source, and spiffworkflow_backend source in PYTHONPATH
    export PYTHONPATH="$ROOT:$ROOT/extensions/m8flow-backend/src:$ROOT/spiffworkflow-backend/src"
    cd "$ROOT/spiffworkflow-backend"
    export UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-debug}"
    uv run uvicorn extensions.app:app \
      --reload \
      --host "0.0.0.0" \
      --port "$BACKEND_PORT" \
      --workers 1 \
      --log-level "$UVICORN_LOG_LEVEL"
  ) &
else
  echo "Starting backend (Keycloak mode) on port $BACKEND_PORT in background..."
  (
    cd "$ROOT/spiffworkflow-backend"
    ./bin/run_server_locally keycloak
  ) &
fi
BACKEND_PID=$!

echo "Waiting a few seconds for backend to start..."
sleep 5

# Free port 7001 so the frontend can bind to it
FRONTEND_PORT=7001
if command -v lsof >/dev/null 2>&1; then
  PIDS=$(lsof -ti :"$FRONTEND_PORT" 2>/dev/null || true)
  if [[ -n "$PIDS" ]]; then
    echo "Killing existing process(es) on port $FRONTEND_PORT: $PIDS"
    echo "$PIDS" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
fi

echo "Starting frontend (Ctrl+C to stop both)..."
if [[ -f "$ROOT/extensions/app.py" ]]; then
  cd "$ROOT/extensions/frontend"
  echo "Using extensions frontend (tenant gate, MULTI_TENANT_ON from .env)"
  export PORT="${FRONTEND_PORT:-7001}"
  export BACKEND_PORT
else
  cd "$ROOT/spiffworkflow-frontend"
fi
exec npm start
