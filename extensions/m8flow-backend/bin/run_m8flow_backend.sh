#!/bin/bash

# Navigate to the root of the repository
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../.." && pwd)"
cd "$repo_root"

# Setup virtual environment
python -m venv .venv
source .venv/bin/activate
python -m pip install uv

# Export PYTHONPATH
export PYTHONPATH=./spiffworkflow-backend:$PYTHONPATH
export PYTHONPATH=./spiffworkflow-backend/src:$PYTHONPATH
export PYTHONPATH=./extensions/m8flow-backend/src:$PYTHONPATH

# Sync dependencies using uv
cd spiffworkflow-backend
uv sync --all-groups --active
cd "$repo_root"

# Load .env vars for bootstrap
set -a
source .env
set +a

# Run bootstrap
cd spiffworkflow-backend
if [[ "${SPIFFWORKFLOW_BACKEND_UPGRADE_DB:-}" == "true" ]]; then
  python -m flask db upgrade
fi
python bin/bootstrap.py
cd "$repo_root"

# Run backend
python -m uvicorn extensions.app:app --host 0.0.0.0 --port 8000 --env-file "$(pwd)/.env" --app-dir "$(pwd)"