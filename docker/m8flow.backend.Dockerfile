# -----------------------------------------------------------------------------
# Stage: builder (for prod) - install backend non-editable into venv
# -----------------------------------------------------------------------------
FROM python:3.12.1-slim-bookworm AS builder

WORKDIR /app

# Build deps for backend (git/ssl, libpq for psycopg2, etc.)
RUN apt-get update \
  && apt-get install -y -q \
    bash \
    build-essential \
    git \
    ca-certificates \
    openssl \
    libpq-dev \
    default-libmysqlclient-dev \
    pkg-config \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && git config --global http.sslVerify true \
  && git config --global http.sslCAInfo /etc/ssl/certs/ca-certificates.crt

RUN pip install --upgrade pip && pip install uv

# Copy only backend and extension trees + log config (slimmer context; .dockerignore helps)
COPY spiffworkflow-backend /app/spiffworkflow-backend
COPY extensions /app/extensions
COPY uvicorn-log.yaml /app/uvicorn-log.yaml

# Create venv and install backend non-editable (prod)
RUN uv venv /opt/venv \
  && /opt/venv/bin/uv pip install /app/spiffworkflow-backend

# -----------------------------------------------------------------------------
# Stage: prod - minimal runtime image for AWS Linux / production (non-root)
# -----------------------------------------------------------------------------
FROM python:3.12.1-slim-bookworm AS prod

WORKDIR /app

# Runtime deps + gosu for entrypoint to drop to app user
RUN apt-get update \
  && apt-get install -y -q \
    bash \
    ca-certificates \
    libpq5 \
    gosu \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Non-root user (fixed UID/GID for volume permissions)
RUN groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

# In-container startup: migrations, bootstrap, uvicorn (no external script; env from compose)
RUN mkdir -p /app/bin && printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -e' \
  'export PYTHONPATH="/app:/app/spiffworkflow-backend:/app/spiffworkflow-backend/src:/app/extensions/m8flow-backend/src:$PYTHONPATH"' \
  'export SPIFFWORKFLOW_BACKEND_DATABASE_URI="${M8FLOW_BACKEND_DATABASE_URI:-$SPIFFWORKFLOW_BACKEND_DATABASE_URI}"' \
  'export SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR="${M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR:-$SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR}"' \
  'cd /app/spiffworkflow-backend' \
  'if [[ "${M8FLOW_BACKEND_UPGRADE_DB:-}" == "true" || "${M8FLOW_BACKEND_SW_UPGRADE_DB:-}" == "true" ]]; then python -m flask db upgrade; fi' \
  'if [[ "${M8FLOW_BACKEND_RUN_BOOTSTRAP:-}" != "false" ]]; then python bin/bootstrap.py; fi' \
  'cd /app' \
  'export SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP="${SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP:-false}"' \
  'exec python -m uvicorn extensions.app:app --host 0.0.0.0 --port 8000 --app-dir /app --log-config /app/uvicorn-log.yaml' \
  > /app/bin/run_backend_docker.sh && chmod +x /app/bin/run_backend_docker.sh

# Entrypoint: chown volume dirs then run CMD as app user
ENTRYPOINT ["/bin/bash", "-c", "chown -R app:app /app/process_models /app/templates 2>/dev/null || true; exec gosu app \"$@\"", "--"]
CMD ["/app/bin/run_backend_docker.sh"]

# -----------------------------------------------------------------------------
# Stage: dev (default) - full repo, editable install for local development (non-root)
# -----------------------------------------------------------------------------
FROM python:3.12.1-slim-bookworm AS dev

WORKDIR /app

RUN apt-get update \
  && apt-get install -y -q \
    bash \
    build-essential \
    git \
    ca-certificates \
    openssl \
    libpq-dev \
    default-libmysqlclient-dev \
    pkg-config \
    gosu \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && git config --global http.sslVerify true \
  && git config --global http.sslCAInfo /etc/ssl/certs/ca-certificates.crt

RUN pip install --upgrade pip && pip install uv

COPY . /app

RUN cd /app/spiffworkflow-backend && uv pip install --system -e .

# In-container startup (same as prod): migrations, bootstrap, uvicorn
RUN mkdir -p /app/bin && printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -e' \
  'export PYTHONPATH="/app:/app/spiffworkflow-backend:/app/spiffworkflow-backend/src:/app/extensions/m8flow-backend/src:$PYTHONPATH"' \
  'export SPIFFWORKFLOW_BACKEND_DATABASE_URI="${M8FLOW_BACKEND_DATABASE_URI:-$SPIFFWORKFLOW_BACKEND_DATABASE_URI}"' \
  'export SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR="${M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR:-$SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR}"' \
  'cd /app/spiffworkflow-backend' \
  'if [[ "${M8FLOW_BACKEND_UPGRADE_DB:-}" == "true" || "${M8FLOW_BACKEND_SW_UPGRADE_DB:-}" == "true" ]]; then python -m flask db upgrade; fi' \
  'if [[ "${M8FLOW_BACKEND_RUN_BOOTSTRAP:-}" != "false" ]]; then python bin/bootstrap.py; fi' \
  'cd /app' \
  'export SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP="${SPIFFWORKFLOW_BACKEND_RUN_DATA_SETUP:-false}"' \
  'exec python -m uvicorn extensions.app:app --host 0.0.0.0 --port 8000 --app-dir /app --log-config /app/uvicorn-log.yaml' \
  > /app/bin/run_backend_docker.sh && chmod +x /app/bin/run_backend_docker.sh

# Non-root user (same UID/GID as prod for volume permissions)
RUN groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app

# Entrypoint: chown volume dirs then run CMD as app user
ENTRYPOINT ["/bin/bash", "-c", "chown -R app:app /app/process_models /app/templates 2>/dev/null || true; exec gosu app \"$@\"", "--"]
CMD ["/app/bin/run_backend_docker.sh"]
