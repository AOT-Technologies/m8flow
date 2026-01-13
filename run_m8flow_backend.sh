#!/bin/bash

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
cd "$repo_root"

export PYTHONPATH=./spiffworkflow-backend:$PYTHONPATH
export PYTHONPATH=./spiffworkflow-backend/src:$PYTHONPATH
export PYTHONPATH=./extensions/m8flow-backend/src:$PYTHONPATH

cd "$repo_root/spiffworkflow-backend"
if [[ "${SPIFFWORKFLOW_BACKEND_UPGRADE_DB:-}" == "true" ]]; then
  python -m flask db upgrade
fi
python bin/bootstrap.py
cd "$repo_root"


python -m uvicorn extensions.app:app --host 0.0.0.0 --port 8000 --env-file "$(pwd)/.env" --app-dir "$(pwd)"
