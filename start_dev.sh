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

assert_frontend_dependencies() {
  local frontend_dir="$1"
  local vite_script="$frontend_dir/node_modules/vite/bin/vite.js"

  if [[ ! -f "$vite_script" ]]; then
    echo "Vite entrypoint was not found at '$vite_script'. Run 'npm install' in extensions/m8flow-frontend." >&2
    exit 1
  fi

  local detail=""
  if ! detail="$(cd "$frontend_dir" && node -e "try { require('./node_modules/rollup/dist/native.js'); } catch (error) { const detail = error && error.message ? error.message.split('\n')[0] : String(error); console.error(detail); process.exit(1); }" 2>&1)"; then
    echo "Frontend dependencies in 'extensions/m8flow-frontend' are incomplete for this platform. ${detail}" >&2
    echo "Reinstall them on this machine with 'npm install' in extensions/m8flow-frontend. If the problem persists, remove 'extensions/m8flow-frontend/node_modules' and install again." >&2
    exit 1
  fi
}

normalize_redis_url_for_local_dev() {
  local value="$1"

  if [[ "$value" =~ ^(redis(s)?://([^/@]+@)?)redis([:/]|$)(.*)$ ]]; then
    printf '%slocalhost%s%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[4]}" "${BASH_REMATCH[5]}"
    return
  fi

  printf '%s' "$value"
}

use_local_dev_host_services() {
  export M8FLOW_LOCAL_DEV_USE_HOST_SERVICES=true

  local key value normalized
  for key in \
    M8FLOW_BACKEND_CELERY_BROKER_URL \
    SPIFFWORKFLOW_BACKEND_CELERY_BROKER_URL \
    M8FLOW_BACKEND_CELERY_RESULT_BACKEND \
    SPIFFWORKFLOW_BACKEND_CELERY_RESULT_BACKEND
  do
    value="${!key-}"
    [[ -z "$value" ]] && continue
    normalized="$(normalize_redis_url_for_local_dev "$value")"
    if [[ "$normalized" != "$value" ]]; then
      export "$key=$normalized"
      echo "Using host-reachable $key=$normalized for local dev."
    fi
  done
}

describe_pid() {
  local pid="$1"
  ps -p "$pid" -o comm= -o args= 2>/dev/null || true
}

is_docker_managed_pid() {
  local pid="$1"
  local details
  details="$(describe_pid "$pid")"
  [[ "$details" =~ [Dd]ocker|com\.docker|docker-proxy|vpnkit ]]
}

stop_processes_on_port() {
  local port="$1"
  local service_hint="$2"

  if ! command -v lsof >/dev/null 2>&1; then
    return
  fi

  local pids
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return
  fi

  local docker_pids=()
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    if is_docker_managed_pid "$pid"; then
      docker_pids+=("$pid")
    fi
  done <<< "$pids"

  if (( ${#docker_pids[@]} > 0 )); then
    local described=()
    local pid details
    for pid in "${docker_pids[@]}"; do
      details="$(describe_pid "$pid")"
      if [[ -n "$details" ]]; then
        described+=("$details")
      else
        described+=("PID $pid")
      fi
    done
    echo "Port $port is currently owned by Docker-managed process(es): ${described[*]}" >&2
    echo "Refusing to kill Docker listeners because that can disconnect the Docker engine." >&2
    echo "Stop the Docker service using this port first, for example: docker compose -f docker/m8flow-docker-compose.yml stop $service_hint" >&2
    exit 1
  fi

  echo "Killing existing process(es) on port $port: $pids"
  echo "$pids" | xargs kill -9 2>/dev/null || true
  sleep 1
}

BACKEND_PORT="${M8FLOW_BACKEND_PORT:-7000}"
export SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP="${SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP:-false}"

assert_frontend_dependencies "$ROOT/extensions/m8flow-frontend"
use_local_dev_host_services

stop_processes_on_port "$BACKEND_PORT" "m8flow-backend"

if [[ -f "$ROOT/extensions/app.py" ]]; then
  echo "Starting backend (extensions app) on port $BACKEND_PORT in background..."
  (
    export M8FLOW_BACKEND_RUN_BOOTSTRAP="${M8FLOW_BACKEND_RUN_BOOTSTRAP:-false}"
    export UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-debug}"
    exec "$ROOT/extensions/m8flow-backend/bin/run_m8flow_backend.sh" "$BACKEND_PORT" --reload
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
stop_processes_on_port "$FRONTEND_PORT" "m8flow-frontend"

echo "Starting frontend (Ctrl+C to stop both)..."
if [[ -f "$ROOT/extensions/app.py" ]]; then
  cd "$ROOT/extensions/m8flow-frontend"
  echo "Using extensions frontend (tenant gate, MULTI_TENANT_ON from .env)"
  export PORT="${FRONTEND_PORT:-7001}"
  export BACKEND_PORT
else
  cd "$ROOT/spiffworkflow-frontend"
fi
exec npm start
