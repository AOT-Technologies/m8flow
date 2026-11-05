# ── m8flow-backend image (m8flow-core wheel, no SpiffArena vendor trees) ──
ARG UV_VERSION=0.7.2
ARG PYTHON_BASE=docker.io/m8flow/m8flow-python-base:ubuntu24.04-py3.12

FROM ${PYTHON_BASE} AS builder

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

COPY m8flow-backend /app/m8flow-backend
COPY m8flow-telemetry /app/m8flow-telemetry
# The NATS consumer and notification worker run from this image (python m8flow-nats-consumer/<script>.py).
COPY m8flow-nats-consumer /app/m8flow-nats-consumer
COPY uvicorn-log.yaml /app/uvicorn-log.yaml

RUN uv venv /opt/venv \
  && uv pip install --python /opt/venv/bin/python setuptools wheel \
  && uv pip install --python /opt/venv/bin/python "/app/m8flow-backend" \
  && uv pip install --python /opt/venv/bin/python "/app/m8flow-telemetry[flask,asgi]" \
  && uv pip install --python /opt/venv/bin/python flower "flask>=3.1.3"

# Runtime starts from plain Ubuntu, not PYTHON_BASE: the compilers, -dev
# headers, git and uv only build the venv. Stay on the base's Ubuntu release:
# the venv's interpreter is a symlink to its /usr/bin/python (python-is-python3).
# No curl: nothing runs it inside this container, and it pulls in 14 more libraries.
# Purge util-linux, perl-base and e2fsprogs (with the util-linux libraries they
# alone need), apt itself (with gpgv and libapt-pkg) and libsqlite3-0 (only
# Python's unused sqlite3 module links it): Ubuntu's base ships them, nothing
# here runs them, and they carry Trivy/Grype findings Ubuntu has no fix for.
# libsqlite3-0 goes through dpkg --force-depends because apt would also remove
# python3, which depends on it. The entrypoint drops privileges with Python
# instead of setpriv. No apt or dpkg runs after this, so the missing Essential
# packages and broken dependencies do not matter.
FROM ubuntu:24.04 AS prod

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y -q --no-install-recommends python3 python-is-python3 ca-certificates \
  && apt-get upgrade -y \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && apt-get purge -y --allow-remove-essential util-linux bsdutils mount libmount1 libsmartcols1 \
    libblkid1 libuuid1 e2fsprogs perl-base apt gpgv libapt-pkg6.0t64 \
  && dpkg --purge --force-depends libsqlite3-0

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# libsqlite3-0 is purged above. Fail the build if importing the API or Celery
# entrypoint imports sqlite3 (the import raises ImportError), or if the app's
# own code (tests aside) imports it at module level. Dependency modules the app
# never loads are not checked. The placeholder settings only get past the
# startup config checks; nothing connects. If the app needs sqlite3, take
# libsqlite3-0 off the purge list.
RUN cd /app/m8flow-backend/src \
  && FLASK_SESSION_SECRET_KEY=unused M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET=unused \
    M8FLOW_BACKEND_DATABASE_URI=postgresql+psycopg://unused@127.0.0.1:1/unused \
    /opt/venv/bin/python -c "import pathlib, re, sys, m8flow_backend.app, m8flow_backend.background_processing.celery_worker; \
    pat = re.compile(r'^(from|import)\s+sqlite3\b', re.M); \
    files = [p for p in pathlib.Path('/app').rglob('*.py') if '/tests/' not in str(p)]; \
    bad = sorted(str(p) for p in files if pat.search(p.read_text(encoding='utf-8', errors='replace'))); \
    sys.exit('sqlite3 is imported, but libsqlite3-0 is purged: ' + ', '.join(bad) if bad else None)"

# Fail the build, not the container, if the venv's interpreter or its compiled
# wheels don't match this stage's python3.
RUN /opt/venv/bin/python -c "import psycopg, uvicorn"

RUN userdel -r ubuntu || true; groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

RUN sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/m8flow-backend/bin/run_m8flow_backend.sh /app/m8flow-backend/bin/run_m8flow_celery_worker.sh

COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

USER app
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/m8flow-backend/bin/run_m8flow_backend.sh"]

FROM ${PYTHON_BASE} AS dev

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

COPY . /app

RUN uv pip install --system --break-system-packages "/app/m8flow-backend" \
  && uv pip install --system --break-system-packages flower "flask>=3.1.3" \
  && uv pip install --system --break-system-packages "/app/m8flow-telemetry[flask,asgi]" \
  && uv cache clean

RUN sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/m8flow-backend/bin/run_m8flow_backend.sh /app/m8flow-backend/bin/run_m8flow_celery_worker.sh

COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

RUN userdel -r ubuntu || true; groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app

USER app
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/m8flow-backend/bin/run_m8flow_backend.sh"]
