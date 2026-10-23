#!/usr/bin/env bash
set -e

uid="$(id -u)"

if [ "$uid" -eq 0 ]; then
  # Best-effort: ensure shared volume mounts are writable by app user.
  chown -R app:app /app/data/process_models /app/data/templates 2>/dev/null || true

  # The Celery worker's revoke state file lives on its own volume, created root-owned.
  if [ -n "${M8FLOW_BACKEND_CELERY_WORKER_STATE_DB:-}" ]; then
    state_dir="$(dirname "$M8FLOW_BACKEND_CELERY_WORKER_STATE_DB")"
    mkdir -p "$state_dir" && chown -R app:app "$state_dir" 2>/dev/null || true
  fi

  # Drop privileges to app user for the main process.
  exec gosu app "$@"
fi

# Already non-root; can't chown or switch users.
exec "$@"

