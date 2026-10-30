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

  # Drop privileges to app user for the main process, as setpriv --reuid=app
  # --regid=app --init-groups did. The prod image has no util-linux, so Python
  # does it. Nothing sets HOME for us, so set it to app's home.
  export HOME=/app
  exec python -c 'import os, pwd, sys
pw = pwd.getpwnam("app")
os.initgroups(pw.pw_name, pw.pw_gid)
os.setgid(pw.pw_gid)
os.setuid(pw.pw_uid)
os.execvp(sys.argv[1], sys.argv[1:])' "$@"
fi

# Already non-root; can't chown or switch users.
exec "$@"

