# ── Fetch upstream m8flow-core ────────────────────────────────────────────────
# Clones backend-required folders from upstream (LGPL-2.1)
# so the build is self-contained. No local copy of upstream code is required.
# Override UPSTREAM_TAG to pin a different tag: --build-arg UPSTREAM_TAG=0.0.2
FROM alpine:3.22 AS fetch-upstream
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
# Using Ubuntu 24.04 (Noble) as it includes Python 3.12 and has significantly
# fewer unresolved OS vulnerabilities than Debian Bookworm.
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install python3.12, venv, uv, and build deps
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.edge.kernel.org/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources \
  && sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.edge.kernel.org/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources \
  && apt-get update \
  && apt-get install -y -q --no-install-recommends \
    tzdata \
    ca-certificates \
    git \
    build-essential \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    libssl-dev \
    libpq-dev \
    libpq5 \
    default-libmysqlclient-dev \
    libmysqlclient21 \
    pkg-config \
    curl \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && git config --global http.sslVerify true \
  && git config --global http.sslCAInfo /etc/ssl/certs/ca-certificates.crt

RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh

# Copy upstream backend from fetch stage and repo files from build context.
COPY --from=fetch-upstream /upstream/spiffworkflow-backend /app/spiffworkflow-backend
COPY --from=fetch-upstream /upstream/spiff-arena-common /app/spiff-arena-common
COPY extensions /app/extensions
COPY uvicorn-log.yaml /app/uvicorn-log.yaml

# Create venv and install backend into it (prod). Use editable install so
# non-code assets like api.yml remain available from the source tree.
RUN uv venv --python 3.12 /opt/venv \
  && uv pip install --python /opt/venv/bin/python -e /app/spiffworkflow-backend \
  && uv pip install --python /opt/venv/bin/python flower "flask>=3.1.3"

# -----------------------------------------------------------------------------
# Stage: prod - minimal runtime image for Linux / production (non-root)
# -----------------------------------------------------------------------------
FROM ubuntu:24.04 AS prod

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Minimal runtime deps + gosu (ubuntu includes python3.12 out of the box)
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.edge.kernel.org/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources \
  && sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.edge.kernel.org/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources \
  && apt-get update \
  && apt-get install -y -q --no-install-recommends \
    tzdata \
    ca-certificates \
    git \
    bash \
    python3.12 \
    python3.12-venv \
    libpq5 \
    gosu \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

# Connexion resolves api.yml relative to the installed package (site-packages), not the source tree.
RUN mkdir -p /opt/venv/lib/python3.12/site-packages/spiffworkflow_backend \
  && cp /app/spiffworkflow-backend/src/spiffworkflow_backend/api.yml \
     /opt/venv/lib/python3.12/site-packages/spiffworkflow_backend/api.yml

# Non-root user (fixed UID/GID for volume permissions)
RUN userdel -r ubuntu || true \
  && groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

# Fix CRLF issues and ensure scripts are executable
RUN sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh

# Entrypoint script: safe for root and non-root
COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

USER app
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/extensions/m8flow-backend/bin/run_m8flow_backend.sh"]

# -----------------------------------------------------------------------------
# Stage: dev (default) - full repo, editable install for local development
# -----------------------------------------------------------------------------
FROM ubuntu:24.04 AS dev

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.edge.kernel.org/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources \
  && sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.edge.kernel.org/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources \
  && apt-get update \
  && apt-get install -y -q --no-install-recommends \
    tzdata \
    ca-certificates \
    git \
    bash \
    build-essential \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    libssl-dev \
    libpq-dev \
    libpq5 \
    default-libmysqlclient-dev \
    libmysqlclient21 \
    pkg-config \
    gosu \
    curl \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && git config --global http.sslVerify true \
  && git config --global http.sslCAInfo /etc/ssl/certs/ca-certificates.crt

RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="/usr/local/bin" sh
ENV PATH="/usr/local/bin:$PATH"

COPY . /app
COPY --from=fetch-upstream /upstream/spiffworkflow-backend /app/spiffworkflow-backend
COPY --from=fetch-upstream /upstream/spiff-arena-common /app/spiff-arena-common

# Clean uv cache after install
RUN cd /app/spiffworkflow-backend && uv venv --python 3.12 /opt/venv \
  && uv pip install --python /opt/venv/bin/python --system -e . --group dev \
  && uv pip install --python /opt/venv/bin/python --system flower nats-py httpx python-dotenv "flask>=3.1.3" \
  && uv cache clean

ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

# Purge unused compiler deps to reduce CVE attack surface
RUN apt-get purge -y --auto-remove \
    build-essential \
    linux-libc-dev \
    libc6-dev \
    python3.12-dev \
    libssl-dev \
    libpq-dev \
    default-libmysqlclient-dev \
    pkg-config \
    python3-pip-whl \
    curl \
  && rm -rf /var/lib/apt/lists/*

RUN sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh

COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

RUN userdel -r ubuntu || true \
  && groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app /opt/venv

USER app
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/extensions/m8flow-backend/bin/run_m8flow_backend.sh"]
