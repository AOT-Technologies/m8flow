#!/bin/bash

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../.." && pwd)"
cd "$repo_root"

mode="${1:-worker}"
if [[ "$mode" == "worker" || "$mode" == "flower" ]]; then
  shift
fi

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

export M8FLOW_BACKEND_CELERY_ENABLED=true
export SPIFFWORKFLOW_BACKEND_CELERY_ENABLED=true
export M8FLOW_BACKEND_RUN_BACKGROUND_SCHEDULER_IN_CREATE_APP=false
export SPIFFWORKFLOW_BACKEND_RUN_BACKGROUND_SCHEDULER_IN_CREATE_APP=false
# Only the API container should run schema migrations on startup.
export M8FLOW_BACKEND_UPGRADE_DB=false
export M8FLOW_BACKEND_SW_UPGRADE_DB=false
if [[ "$mode" == "worker" ]]; then
  export M8FLOW_BACKEND_RUNNING_IN_CELERY_WORKER=true
  export SPIFFWORKFLOW_BACKEND_RUNNING_IN_CELERY_WORKER=true
else
  export M8FLOW_BACKEND_RUNNING_IN_CELERY_WORKER=false
  export SPIFFWORKFLOW_BACKEND_RUNNING_IN_CELERY_WORKER=false
fi

if [[ "${M8FLOW_BACKEND_SW_UPGRADE_DB:-}" == "true" ]]; then
  cd "$repo_root/spiffworkflow-backend"
  python -m flask db upgrade
  cd "$repo_root"
fi

log_level="${M8FLOW_BACKEND_CELERY_LOG_LEVEL:-info}"
if [[ "$mode" == "worker" ]]; then
  enable_events="${M8FLOW_BACKEND_CELERY_ENABLE_EVENTS:-true}"
  enable_events="${enable_events,,}"

  worker_args=(worker --loglevel "$log_level")

  if [[ "$enable_events" == "1" || "$enable_events" == "true" || "$enable_events" == "yes" || "$enable_events" == "on" ]]; then
    worker_args+=("-E")
  fi

  # --- Concurrency / pool sizing (env-configurable) ---
  # NOTE: Flower autoscale requires Celery worker to start with --autoscale=max,min
  autoscale_min="${M8FLOW_BACKEND_CELERY_AUTOSCALE_MIN:-}"
  autoscale_max="${M8FLOW_BACKEND_CELERY_AUTOSCALE_MAX:-}"
  concurrency="${M8FLOW_BACKEND_CELERY_CONCURRENCY:-}"
  pool="${M8FLOW_BACKEND_CELERY_POOL:-prefork}"

  # Prefer prefork because it's the pool type that supports resizing reliably.
  worker_args+=("--pool=$pool")

  # If autoscale is configured, enable it.
  if [[ -n "$autoscale_min" && -n "$autoscale_max" ]]; then
    worker_args+=("--autoscale=${autoscale_max},${autoscale_min}")
    # Optional: set initial concurrency to min if not explicitly set
    if [[ -z "$concurrency" ]]; then
      concurrency="$autoscale_min"
    fi
  fi

  # If concurrency is explicitly configured (or set from min), apply it
  if [[ -n "$concurrency" ]]; then
    worker_args+=("--concurrency=$concurrency")
  fi

  exec python -m celery -A m8flow_backend.background_processing.celery_worker:celery_app "${worker_args[@]}" "$@"
fi

if [[ "$mode" == "flower" ]]; then
  flower_port="${M8FLOW_BACKEND_CELERY_FLOWER_PORT:-5555}"
  flower_address="${M8FLOW_BACKEND_CELERY_FLOWER_ADDRESS:-0.0.0.0}"
  flower_port="${flower_port//$'\r'/}"
  flower_address="${flower_address//$'\r'/}"
  flower_port="${flower_port#"${flower_port%%[![:space:]]*}"}"
  flower_port="${flower_port%"${flower_port##*[![:space:]]}"}"
  flower_address="${flower_address#"${flower_address%%[![:space:]]*}"}"
  flower_address="${flower_address%"${flower_address##*[![:space:]]}"}"
  if [[ -z "$flower_port" ]]; then
    flower_port="5555"
  fi
  if [[ -z "$flower_address" ]]; then
    flower_address="0.0.0.0"
  fi

  flower_args=(flower)
  if [[ -n "$flower_address" ]]; then
    flower_args+=("--address=$flower_address")
  fi
  if [[ -n "$flower_port" ]]; then
    flower_args+=("--port=$flower_port")
  fi
  if [[ -n "${M8FLOW_BACKEND_CELERY_FLOWER_BASIC_AUTH:-}" ]]; then
    flower_args+=("--basic-auth=${M8FLOW_BACKEND_CELERY_FLOWER_BASIC_AUTH}")
  fi

  exec python -m celery -A m8flow_backend.background_processing.celery_worker:celery_app "${flower_args[@]}" "$@"
fi

echo "Unknown mode '$mode'. Expected 'worker' or 'flower'." >&2
exit 1
