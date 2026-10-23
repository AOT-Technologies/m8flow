#!/usr/bin/env bash
set -e

uid="$(id -u)"

if [ "$uid" -eq 0 ]; then
  # Best-effort: ensure shared volume mounts are writable by app user.
  chown -R app:app /app/data/process_models /app/data/templates 2>/dev/null || true

  # Drop privileges to app user for the main process. setpriv (util-linux)
  # does not set HOME the way gosu did, so set it to app's home.
  export HOME=/app
  exec setpriv --reuid=app --regid=app --init-groups "$@"
fi

# Already non-root; can't chown or switch users.
exec "$@"

