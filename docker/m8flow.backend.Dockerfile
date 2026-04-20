# ── Fetch upstream m8flow-core ────────────────────────────────────────────────
# Clones backend-required folders from upstream (LGPL-2.1)
# so the build is self-contained. No local copy of upstream code is required.
# Override UPSTREAM_TAG to pin a different tag: --build-arg UPSTREAM_TAG=0.0.2

# Pin uv version globally so all stages use the same audited release.
# Update this to the latest release periodically: https://github.com/astral-sh/uv/releases
ARG UV_VERSION=0.7.2

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
FROM ubuntu:24.04 AS builder

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

# Re-declare global build arg in this stage
ARG UV_VERSION

# Build deps for backend (git/ssl, libpq for psycopg2, etc.)
RUN apt-get update \
  && apt-get install -y -q --no-install-recommends \
    bash \
    build-essential \
    curl \
    git \
    ca-certificates \
    openssl \
    libpq-dev \
    default-libmysqlclient-dev \
    pkg-config \
    python3 \
    python3-venv \
    python3-dev \
    python-is-python3 \
  && apt-get upgrade -y \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && git config --global http.sslVerify true \
  && git config --global http.sslCAInfo /etc/ssl/certs/ca-certificates.crt

# Install pinned uv via official binary installer (avoids pip-installed tool attack surface)
RUN curl -fsSL https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin UV_VERSION=${UV_VERSION} sh \
  && uv --version

# Copy upstream backend from fetch stage and repo files from build context.
COPY --from=fetch-upstream /upstream/spiffworkflow-backend /app/spiffworkflow-backend
COPY --from=fetch-upstream /upstream/spiff-arena-common /app/spiff-arena-common
COPY extensions /app/extensions
COPY uvicorn-log.yaml /app/uvicorn-log.yaml

# Create venv and install backend into it (prod). Use editable install so
# non-code assets like api.yml remain available from the source tree.
# Pin flask>=3.1.3 to fix CVE-2026-27205 (info disclosure via improper session cache)
RUN uv venv /opt/venv \
  && uv pip install --python /opt/venv/bin/python -e /app/spiffworkflow-backend \
  && uv pip install --python /opt/venv/bin/python flower "flask>=3.1.3"

# -----------------------------------------------------------------------------
# Stage: prod - minimal runtime image for Linux / production (non-root)
# -----------------------------------------------------------------------------
FROM ubuntu:24.04 AS prod

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

# Runtime deps + gosu for entrypoint to drop to app user
RUN apt-get update \
  && apt-get install -y -q --no-install-recommends \
    bash \
    ca-certificates \
    git \
    libpq5 \
    libmariadb3 \
    gosu \
    python3 \
    python3-venv \
    python-is-python3 \
  && apt-get upgrade -y \
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
RUN userdel -r ubuntu || true; groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

# Fix CRLF issues for Windows users and ensure scripts are executable
RUN sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh

# Entrypoint script: safe for root and non-root
COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

# Default to non-root user (SonarQube S6481); compose overrides with user: "0" so entrypoint can chown then gosu
USER app

# Entrypoint: if root, chown volume dirs then drop to app; else exec directly
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/extensions/m8flow-backend/bin/run_m8flow_backend.sh"]

# -----------------------------------------------------------------------------
# Stage: dev (default) - full repo, editable install for local development (non-root)
# -----------------------------------------------------------------------------
FROM ubuntu:24.04 AS dev

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

# Re-declare global build arg in this stage
ARG UV_VERSION

RUN apt-get update \
  && apt-get install -y -q --no-install-recommends \
    bash \
    build-essential \
    curl \
    git \
    ca-certificates \
    openssl \
    libpq-dev \
    default-libmysqlclient-dev \
    pkg-config \
    gosu \
    python3 \
    python3-venv \
    python3-dev \
    python-is-python3 \
  && apt-get upgrade -y \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && git config --global http.sslVerify true \
  && git config --global http.sslCAInfo /etc/ssl/certs/ca-certificates.crt

# Install pinned uv via official binary installer (avoids pip-installed tool attack surface)
RUN curl -fsSL https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin UV_VERSION=${UV_VERSION} sh \
  && uv --version

# Copy repo files from build context, then overlay upstream from fetch stage.
# The fetch-stage copy ensures spiffworkflow-backend is always present even
# when the developer has not run bin/fetch-upstream.sh locally.
COPY . /app
COPY --from=fetch-upstream /upstream/spiffworkflow-backend /app/spiffworkflow-backend
COPY --from=fetch-upstream /upstream/spiff-arena-common /app/spiff-arena-common

# Pin flask>=3.1.3 (CVE-2026-27205); purge build deps + vulnerable packages:
#   - build-essential: brings in patch (CVE-2018-6952, CVE-2021-45261)
#   - python3-pip-whl: bundles outdated requests/urllib3 (CVE-2024-35195,
#     CVE-2025-66418, CVE-2025-66471, CVE-2026-21441) - not needed since we use uv
RUN cd /app/spiffworkflow-backend && uv pip install --system --break-system-packages -e . --group dev \
  && uv pip install --system --break-system-packages flower nats-py httpx python-dotenv "flask>=3.1.3" \
  && uv cache clean \
  && apt-get purge -y build-essential python3-dev default-libmysqlclient-dev patch python3-pip-whl \
  && apt-get autoremove -y \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Fix CRLF issues for Windows users and ensure scripts are executable
RUN sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh

# Entrypoint script: safe for root and non-root
COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

# Non-root user (same UID/GID as prod for volume permissions)
RUN userdel -r ubuntu || true; groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app

# Default to non-root user (SonarQube S6481); compose overrides with user: "0" so entrypoint can chown then gosu
USER app

# Entrypoint: if root, chown volume dirs then drop to app; else exec directly
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/extensions/m8flow-backend/bin/run_m8flow_backend.sh"]
