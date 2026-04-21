# ── Fetch upstream m8flow-core ────────────────────────────────────────────────
# Clones backend-required folders from upstream (LGPL-2.1)
# so the build is self-contained. No local copy of upstream code is required.
# Override UPSTREAM_TAG to pin a different tag: --build-arg UPSTREAM_TAG=0.0.2
FROM alpine:3.20 AS fetch-upstream
ARG UPSTREAM_TAG=
RUN apk add --no-cache git jq
COPY upstream.sources.json /tmp/upstream.sources.json
RUN set -eu; \
    UPSTREAM_URL="$(jq -r '.upstream_url' /tmp/upstream.sources.json)"; \
    DEFAULT_UPSTREAM_TAG="$(jq -r '.upstream_ref' /tmp/upstream.sources.json)"; \
    RESOLVED_UPSTREAM_TAG="${UPSTREAM_TAG:-${DEFAULT_UPSTREAM_TAG}}"; \
    BACKEND_FOLDERS="$(jq -r '(.backend // []) | map(select(type == "string" and length > 0)) | join(" ")' /tmp/upstream.sources.json)"; \
    if [ -z "${UPSTREAM_URL}" ] || [ "${UPSTREAM_URL}" = "null" ]; then \
      echo "Invalid upstream_url in upstream.sources.json" >&2; exit 1; \
    fi; \
    if [ -z "${RESOLVED_UPSTREAM_TAG}" ] || [ "${RESOLVED_UPSTREAM_TAG}" = "null" ]; then \
      echo "upstream_ref is missing or null in upstream.sources.json" >&2; exit 1; \
    fi; \
    if [ -z "${BACKEND_FOLDERS}" ]; then \
      echo "No backend folders configured in upstream.sources.json" >&2; exit 1; \
    fi; \
    git clone --no-local --depth 1 --filter=blob:none --sparse \
      --branch "${RESOLVED_UPSTREAM_TAG}" \
      "${UPSTREAM_URL}" /upstream; \
    cd /upstream; \
    # word splitting is intentional to pass folders as separate args
    git sparse-checkout set ${BACKEND_FOLDERS}

# -----------------------------------------------------------------------------
# Stage: builder (for prod) - install backend into venv
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

# Copy upstream backend from fetch stage and repo files from build context.
COPY --from=fetch-upstream /upstream/spiffworkflow-backend /app/spiffworkflow-backend
COPY --from=fetch-upstream /upstream/spiff-arena-common /app/spiff-arena-common
COPY m8flow-backend /app/m8flow-backend
COPY uvicorn-log.yaml /app/uvicorn-log.yaml

# Create venv and install backend into it (prod). Use editable install so
# non-code assets like api.yml remain available from the source tree.
RUN uv venv /opt/venv \
  && uv pip install --python /opt/venv/bin/python -e /app/spiffworkflow-backend \
  && uv pip install --python /opt/venv/bin/python flower

# -----------------------------------------------------------------------------
# Stage: prod - minimal runtime image for Linux / production (non-root)
# -----------------------------------------------------------------------------
FROM python:3.12.1-slim-bookworm AS prod

WORKDIR /app

# Runtime deps + gosu for entrypoint to drop to app user
RUN apt-get update \
  && apt-get install -y -q \
    bash \
    ca-certificates \
    git \
    libpq5 \
    gosu \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Connexion resolves api.yml relative to the installed package (site-packages), not the source tree.
# With editable install, uv may not create a physical spiffworkflow_backend dir in site-packages;
# create it and copy the OpenAPI spec so add_api("api.yml") finds it.
RUN mkdir -p /opt/venv/lib/python3.12/site-packages/spiffworkflow_backend \
  && cp /app/spiffworkflow-backend/src/spiffworkflow_backend/api.yml \
     /opt/venv/lib/python3.12/site-packages/spiffworkflow_backend/api.yml

# Non-root user (fixed UID/GID for volume permissions)
RUN groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

# Fix CRLF issues for Windows users and ensure scripts are executable
RUN sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/m8flow-backend/bin/run_m8flow_backend.sh /app/m8flow-backend/bin/run_m8flow_celery_worker.sh

# Entrypoint script: safe for root and non-root
COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

# Default to non-root user (SonarQube S6481); compose overrides with user: "0" so entrypoint can chown then gosu
USER app

# Entrypoint: if root, chown volume dirs then drop to app; else exec directly
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/m8flow-backend/bin/run_m8flow_backend.sh"]

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

# Copy repo files from build context, then overlay upstream from fetch stage.
# The fetch-stage copy ensures spiffworkflow-backend is always present even
# when the developer has not run bin/fetch-upstream.sh locally.
COPY . /app
COPY --from=fetch-upstream /upstream/spiffworkflow-backend /app/spiffworkflow-backend
COPY --from=fetch-upstream /upstream/spiff-arena-common /app/spiff-arena-common

RUN cd /app/spiffworkflow-backend && uv pip install --system -e . --group dev \
  && uv pip install --system flower nats-py httpx python-dotenv

# Fix CRLF issues for Windows users and ensure scripts are executable
RUN sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/m8flow-backend/bin/run_m8flow_backend.sh /app/m8flow-backend/bin/run_m8flow_celery_worker.sh

# Entrypoint script: safe for root and non-root
COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

# Non-root user (same UID/GID as prod for volume permissions)
RUN groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app

# Default to non-root user (SonarQube S6481); compose overrides with user: "0" so entrypoint can chown then gosu
USER app

# Entrypoint: if root, chown volume dirs then drop to app; else exec directly
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/m8flow-backend/bin/run_m8flow_backend.sh"]
