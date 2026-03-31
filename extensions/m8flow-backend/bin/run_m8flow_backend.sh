#!/bin/bash
set -e

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../.." && pwd)"
cd "$repo_root"

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

export PYTHONPATH=./spiffworkflow-backend:$PYTHONPATH
export PYTHONPATH=./spiffworkflow-backend/src:$PYTHONPATH
export PYTHONPATH=./extensions/m8flow-backend/src:$PYTHONPATH

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

export SPIFFWORKFLOW_BACKEND_DATABASE_URI="${M8FLOW_BACKEND_DATABASE_URI}"
export SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR="${M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR}"

if [[ "${M8FLOW_BACKEND_SW_UPGRADE_DB:-true}" != "false" ]]; then
  cd "$repo_root/spiffworkflow-backend"
  python -m flask db upgrade
  cd "$repo_root"
fi

if [[ "${M8FLOW_BACKEND_UPGRADE_DB:-true}" != "false" ]]; then
  python -m alembic -c "$repo_root/extensions/m8flow-backend/migrations/alembic.ini" upgrade head
fi

if [[ "${M8FLOW_BACKEND_RUN_BOOTSTRAP:-}" != "false" ]]; then
  cd "$repo_root/spiffworkflow-backend"
  python bin/bootstrap.py
  cd "$repo_root"
fi

log_config="$repo_root/uvicorn-log.yaml"
backend_port="${port_arg:-${M8FLOW_BACKEND_PORT:-8000}}"

# Only pass --env-file when the file exists (ECS/task definition inject env; no .env in container).
uvicorn_args=(--host 0.0.0.0 --port "$backend_port" --app-dir "$repo_root" --log-config "$log_config")
[[ -f "$env_file" ]] && uvicorn_args+=(--env-file "$env_file")
[[ -n "${UVICORN_LOG_LEVEL:-}" ]] && uvicorn_args+=(--log-level "$UVICORN_LOG_LEVEL")
if [[ "$reload_mode" == "true" ]]; then
  uvicorn_args+=(--reload --workers 1)
  uvicorn_args+=(--reload-exclude "extensions/m8flow-frontend/**")
  uvicorn_args+=(--reload-exclude "**/node_modules/**")
  uvicorn_args+=(--reload-exclude "**/.vite/**")
  uvicorn_args+=(--reload-exclude "**/.vite-temp/**")
  uvicorn_args+=(--reload-exclude ".venv/**")
  uvicorn_args+=(--reload-exclude ".git/**")
fi

exec python -m uvicorn extensions.app:app "${uvicorn_args[@]}"
