#!/bin/bash
set -e

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../.." && pwd)"
cd "$repo_root"

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

if [[ "${M8FLOW_BACKEND_UPGRADE_DB:-true}" != "false" ]]; then
  cd "$repo_root/spiffworkflow-backend"
  if [[ "${M8FLOW_BACKEND_SW_UPGRADE_DB:-true}" != "false" ]]; then
    python -m flask db upgrade
  fi
  cd "$repo_root"
  python -m alembic -c "$repo_root/extensions/m8flow-backend/migrations/alembic.ini" upgrade head
fi

if [[ "${M8FLOW_BACKEND_RUN_BOOTSTRAP:-}" != "false" ]]; then
  cd "$repo_root/spiffworkflow-backend"
  python bin/bootstrap.py
  cd "$repo_root"
fi

log_config="$repo_root/uvicorn-log.yaml"

# Only pass --env-file when the file exists (ECS/task definition inject env; no .env in container).
uvicorn_args=(--host 0.0.0.0 --port 8000 --app-dir "$repo_root" --log-config "$log_config")
[[ -f "$env_file" ]] && uvicorn_args+=(--env-file "$env_file")

exec python -m uvicorn extensions.app:app "${uvicorn_args[@]}"