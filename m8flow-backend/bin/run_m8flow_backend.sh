#!/bin/bash
set -eo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../.." && pwd)"
cd "$repo_root"
launcher_started_at=${SECONDS:-0}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

format_duration() {
  local total_seconds="$1"
  printf '%02dm%02ds' "$((total_seconds / 60))" "$((total_seconds % 60))"
}

log_launcher_status() {
  local elapsed
  elapsed="$(format_duration "$((SECONDS - launcher_started_at))")"
  printf 'm8flow-backend: [%s] %s\n' "$elapsed" "$*"
}

run_timed_step() {
  local label="$1"
  shift

  local started_at=$SECONDS
  log_launcher_status "$label..."
  "$@"
  log_launcher_status "$label complete in $(format_duration "$((SECONDS - started_at))")"
}

is_running_in_container() {
  [[ -f /.dockerenv ]] && return 0
  [[ -r /proc/1/cgroup ]] && grep -qaE '(docker|containerd|kubepods)' /proc/1/cgroup
}

resolve_repo_relative_path() {
  local path_value="$1"

  if [[ -z "$path_value" ]]; then
    printf '%s' "$path_value"
    return
  fi

  if [[ "$path_value" == /* || "$path_value" =~ ^[A-Za-z]:[\\/].* || "$path_value" == \\\\* ]]; then
    printf '%s' "$path_value"
    return
  fi

  printf '%s/%s' "$repo_root" "${path_value#./}"
}

normalize_bpmn_spec_dir() {
  local path_value="$1"

  if [[ -z "$path_value" ]]; then
    printf '%s' "$path_value"
    return
  fi

  if is_running_in_container && [[ "$path_value" =~ ^[A-Za-z]:[\\/] || "$path_value" == \\\\* ]]; then
    printf '/app/process_models'
    return
  fi

  resolve_repo_relative_path "$path_value"
}

uv_has_active_environment() {
  [[ -n "${VIRTUAL_ENV:-}" ]]
}

run_uv_python() {
  if uv_has_active_environment; then
    uv run --active python "$@"
    return
  fi

  uv run python "$@"
}

exec_uv_python() {
  if uv_has_active_environment; then
    exec uv run --active python "$@"
  fi

  exec uv run python "$@"
}

sync_uv_environment() {
  if uv_has_active_environment; then
    uv sync --all-groups --inexact --active
    return
  fi

  uv sync --all-groups --inexact
}

has_m8flow_backend_runtime_dependencies() {
  run_uv_python -c "import nats" >/dev/null 2>&1
}

sync_m8flow_backend_runtime_dependencies() {
  local packages=(
    "nats-py>=2.6.0"
  )

  if has_m8flow_backend_runtime_dependencies; then
    return
  fi

  uv pip install "${packages[@]}"
}

sync_local_backend_environment() {
  cd "$repo_root/spiffworkflow-backend"
  sync_uv_environment
  sync_m8flow_backend_runtime_dependencies
  cd "$repo_root"
}

run_spiff_db_upgrade() {
  run_python_module_in_backend_dir flask db upgrade
}

run_m8flow_db_upgrade() {
  run_python_module alembic -c "$repo_root/m8flow-backend/migrations/alembic.ini" upgrade head
}

run_backend_bootstrap() {
  if [[ "$use_uv_runner" == "true" ]]; then
    (
      cd "$repo_root/spiffworkflow-backend"
      run_uv_python bin/bootstrap.py
    )
    return
  fi

  (
    cd "$repo_root/spiffworkflow-backend"
    python bin/bootstrap.py
  )
}

run_python_module() {
  local module="$1"
  shift

  if [[ "$use_uv_runner" == "true" ]]; then
    (
      cd "$repo_root/spiffworkflow-backend"
      exec_uv_python -m "$module" "$@"
    )
    return
  fi

  python -m "$module" "$@"
}

run_python_module_in_backend_dir() {
  local module="$1"
  shift

  (
    cd "$repo_root/spiffworkflow-backend"
    run_python_module "$module" "$@"
  )
}

exec_python_module() {
  local module="$1"
  shift

  if [[ "$use_uv_runner" == "true" ]]; then
    cd "$repo_root/spiffworkflow-backend"
    exec_uv_python -m "$module" "$@"
  fi

  exec python -m "$module" "$@"
}

port_arg=""
reload_mode="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reload)
      reload_mode="true"
      shift
      ;;
    *)
      if [[ -z "$port_arg" ]]; then
        port_arg="$1"
        shift
      else
        echo >&2 "Unexpected argument: $1"
        exit 1
      fi
      ;;
  esac
done

use_uv_runner="false"
if ! is_running_in_container && command_exists uv && [[ "${M8FLOW_BACKEND_USE_UV:-auto}" != "false" ]]; then
  use_uv_runner="true"
fi
if [[ "${M8FLOW_BACKEND_USE_UV:-auto}" == "true" && "$use_uv_runner" != "true" ]]; then
  echo >&2 "M8FLOW_BACKEND_USE_UV=true was requested but 'uv' is not available."
  exit 1
fi

export PYTHONPATH="$repo_root:${PYTHONPATH:-}"
export PYTHONPATH="$repo_root/spiffworkflow-backend:$PYTHONPATH"
export PYTHONPATH="$repo_root/spiffworkflow-backend/src:$PYTHONPATH"
export PYTHONPATH="$repo_root/m8flow-backend/src:$PYTHONPATH"

env_file="$repo_root/.env"
if [[ -f "$env_file" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue
    [[ "$line" == export\ * ]] && line="${line#export }"
    [[ "$line" != *"="* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    else
      value="${value%% \#*}"
      value="${value%%$'\t'#*}"
      value="${value%"${value##*[![:space:]]}"}"
    fi
    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  done < "$env_file"
fi

resolved_bpmn_spec_dir="$(normalize_bpmn_spec_dir "${M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR:-}")"
if [[ -n "$resolved_bpmn_spec_dir" ]]; then
  export M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR="$resolved_bpmn_spec_dir"
fi

# Bridge: upstream spiffworkflow-backend reads SPIFFWORKFLOW_BACKEND_* env vars — map from M8FLOW_ names.
export SPIFFWORKFLOW_BACKEND_DATABASE_URI="${M8FLOW_BACKEND_DATABASE_URI}"
export SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR="${M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR}"

if [[ -z "${UVICORN_LOG_LEVEL:-}" && ! is_running_in_container ]]; then
  export UVICORN_LOG_LEVEL=debug
fi

log_launcher_status "Preparing backend startup (port=${port_arg:-${M8FLOW_BACKEND_PORT:-6840}}, reload=${reload_mode}, uv_runner=${use_uv_runner})"
if [[ "$reload_mode" == "true" ]]; then
  log_launcher_status "Reload mode starts a reloader first, then a worker. A short quiet pause after 'Uvicorn running' is normal on first startup."
fi

if [[ "$use_uv_runner" == "true" && "${M8FLOW_BACKEND_SYNC_DEPS:-true}" != "false" ]]; then
  run_timed_step "Syncing local Python environment" sync_local_backend_environment
fi

if [[ "${M8FLOW_BACKEND_SW_UPGRADE_DB:-true}" != "false" ]]; then
  run_timed_step "Running upstream backend migrations" run_spiff_db_upgrade
fi

if [[ "${M8FLOW_BACKEND_UPGRADE_DB:-true}" != "false" ]]; then
  run_timed_step "Running M8Flow migrations" run_m8flow_db_upgrade
fi

if [[ "${M8FLOW_BACKEND_RUN_BOOTSTRAP:-}" != "false" ]]; then
  run_timed_step "Running backend bootstrap" run_backend_bootstrap
fi

log_config="$repo_root/uvicorn-log.yaml"
default_backend_port="6840"
backend_port="${port_arg:-${M8FLOW_BACKEND_PORT:-$default_backend_port}}"

# Only pass --env-file when the file exists (ECS/task definition inject env; no .env in container).
uvicorn_args=(--host 0.0.0.0 --port "$backend_port" --app-dir "$repo_root" --log-config "$log_config")
[[ -f "$env_file" ]] && uvicorn_args+=(--env-file "$env_file")
[[ -n "${UVICORN_LOG_LEVEL:-}" ]] && uvicorn_args+=(--log-level "$UVICORN_LOG_LEVEL")
if [[ "$reload_mode" == "true" ]]; then
  uvicorn_args+=(--reload)
  uvicorn_args+=(--reload-dir "$repo_root/m8flow-backend/src")
  uvicorn_args+=(--reload-dir "$repo_root/m8flow-backend/migrations")
  uvicorn_args+=(--reload-exclude "m8flow-frontend/**")
  uvicorn_args+=(--reload-exclude "**/node_modules/**")
  uvicorn_args+=(--reload-exclude "**/.vite/**")
  uvicorn_args+=(--reload-exclude "**/.vite-temp/**")
  uvicorn_args+=(--reload-exclude ".venv/**")
  uvicorn_args+=(--reload-exclude ".git/**")
fi

log_launcher_status "Starting Uvicorn. The backend is ready once '/v1.0/status' returns 200."
exec_python_module uvicorn m8flow_backend.app:app "${uvicorn_args[@]}"
