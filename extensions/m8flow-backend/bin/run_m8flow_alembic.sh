#!/bin/bash
# Usage:
#   ./run_m8flow_alembic.sh upgrade head
#   ./run_m8flow_alembic.sh current
#   ./run_m8flow_alembic.sh history
#   ./run_m8flow_alembic.sh stamp head
#   ./run_m8flow_alembic.sh downgrade -1
# Notes:
#   downgrade -1 steps back one revision; downgrade base resets to the first revision.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/../../.." && pwd)"
cd "$repo_root"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PYTHONPATH="$repo_root/spiffworkflow-backend:$repo_root/spiffworkflow-backend/src:$repo_root/extensions/m8flow-backend/src:${PYTHONPATH:-}"

alembic_ini="$repo_root/extensions/m8flow-backend/migrations/alembic.ini"

if [[ "$#" -eq 0 ]]; then
  echo "Usage: ./run_m8flow_alembic.sh <alembic args>"
  echo "Example: ./run_m8flow_alembic.sh upgrade head"
  exit 1
fi

python -m alembic -c "$alembic_ini" "$@"
