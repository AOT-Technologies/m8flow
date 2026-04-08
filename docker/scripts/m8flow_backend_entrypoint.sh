#!/usr/bin/env bash
set -e

uid="$(id -u)"

if [ "$uid" -eq 0 ]; then
  # Best-effort: ensure shared volume mounts are writable by app user.
  chown -R app:app /app/data/process_models /app/data/templates 2>/dev/null || true

  # Drop privileges to app user for the main process.
  exec gosu app "$@"
fi

# Already non-root; can't chown or switch users.
exec "$@"

