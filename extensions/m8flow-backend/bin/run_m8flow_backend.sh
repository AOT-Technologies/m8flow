#!/bin/bash

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../.." && pwd)"
cd "$repo_root"

export PYTHONPATH="$repo_root:$repo_root/spiffworkflow-backend:$repo_root/spiffworkflow-backend/src:$repo_root/extensions/m8flow-backend/src:$PYTHONPATH"

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
cd "$repo_root/spiffworkflow-backend"
# Run SpiffWorkflow + tenant migrations when either UPGRADE_DB env is true
if [[ "${M8FLOW_BACKEND_UPGRADE_DB:-}" == "true" || "${M8FLOW_BACKEND_SW_UPGRADE_DB:-}" == "true" ]]; then
  python -m flask db upgrade
  echo "Resetting M8Flow migration version to re-apply tenant columns if needed..."
  python "$repo_root/extensions/m8flow-backend/bin/reset_m8flow_tenant_migration.py"
fi
# Bootstrap optional: set M8FLOW_BACKEND_RUN_BOOTSTRAP=false to skip
if [[ "${M8FLOW_BACKEND_RUN_BOOTSTRAP:-}" != "false" ]]; then
  python bin/bootstrap.py
fi
cd "$repo_root"

# SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP from .env (default false = no cache refresh)
export SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP="${SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP:-false}"

log_config="$repo_root/uvicorn-log.yaml"

python -m uvicorn extensions.app:app \
  --host 0.0.0.0 --port 8000 \
  --env-file "$repo_root/.env" \
  --app-dir "$repo_root" \
  --log-config "$log_config"
