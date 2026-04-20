# ── Fetch upstream m8flow-core ────────────────────────────────────────────────
# Clones frontend-required folders from upstream (LGPL-2.1) so the build is
# self-contained. No local copy of upstream code is required.
# Override UPSTREAM_TAG to pin a different tag: --build-arg UPSTREAM_TAG=0.0.2
FROM alpine:3.22 AS fetch-upstream

ARG UPSTREAM_TAG=

RUN apk update && apk upgrade && \
    apk add --no-cache git jq

COPY upstream.sources.json /tmp/upstream.sources.json

RUN set -eu; \
    UPSTREAM_URL="$(jq -r '.upstream_url' /tmp/upstream.sources.json)"; \
    DEFAULT_UPSTREAM_TAG="$(jq -r '.upstream_ref' /tmp/upstream.sources.json)"; \
    RESOLVED_UPSTREAM_TAG="${UPSTREAM_TAG:-${DEFAULT_UPSTREAM_TAG}}"; \
    FRONTEND_FOLDERS="$(jq -r '(.frontend // []) | map(select(type == "string" and length > 0)) | join(" ")' /tmp/upstream.sources.json)"; \
    if [ -z "${UPSTREAM_URL}" ] || [ "${UPSTREAM_URL}" = "null" ]; then \
      echo "Invalid upstream_url in upstream.sources.json" >&2; exit 1; \
    fi; \
    if [ -z "${RESOLVED_UPSTREAM_TAG}" ] || [ "${RESOLVED_UPSTREAM_TAG}" = "null" ]; then \
      echo "upstream_ref is missing or null in upstream.sources.json" >&2; exit 1; \
    fi; \
    if [ -z "${FRONTEND_FOLDERS}" ]; then \
      echo "No frontend folders configured in upstream.sources.json" >&2; exit 1; \
    fi; \
    git clone --no-local --depth 1 --filter=blob:none --sparse \
      --branch "${RESOLVED_UPSTREAM_TAG}" \
      "${UPSTREAM_URL}" /upstream; \
    cd /upstream; \
    # word splitting is intentional to pass folders as separate args
    git sparse-checkout set ${FRONTEND_FOLDERS}

# ── Base: Node runtime ────────────────────────────────────────────────────────
FROM node:24.10.0-trixie-slim AS base

RUN mkdir /app
WORKDIR /app

RUN apt-get update \
  && apt-get install -y -q \
  curl \
  procps \
  vim-tiny \
  libkrb5support0 \
  libexpat1 \
  && apt-get upgrade -y \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

ENV NODE_OPTIONS=--max_old_space_size=4096

# ── Setup: build both frontends ───────────────────────────────────────────────
FROM base AS setup

WORKDIR /app

# Copy repo files from build context (m8flow-frontend, docker scripts, etc.)
COPY . /app

# Overlay upstream frontend from the fetch stage.
# This takes precedence over any local copy in the build context.
COPY --from=fetch-upstream /upstream/spiffworkflow-frontend /app/spiffworkflow-frontend

########################
# Build upstream spiffworkflow-frontend
########################
WORKDIR /app/spiffworkflow-frontend

# Install core frontend dependencies and build the app.
# Use npm ci when a lockfile is present (for reproducibility),
# otherwise fall back to npm install.
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then \
      npm ci; \
    else \
      npm install; \
    fi && \
    npm run build

########################
# Build the m8flow extension frontend
########################
WORKDIR /app/m8flow-frontend

# Ensure the python worker from the core frontend is available at the
# path expected by the build tooling, without modifying upstream code.
RUN mkdir -p public/src/workers && \
    cp /app/spiffworkflow-frontend/src/workers/python.ts public/src/workers/python.ts

# npm ci because it respects the lock file.
# --ignore-scripts because authors can do bad things in postinstall scripts.
# https://cheatsheetseries.owasp.org/cheatsheets/NPM_Security_Cheat_Sheet.html
# npx can-i-ignore-scripts can check that it's safe to ignore scripts.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --ignore-scripts && \
    node scripts/patch-bpmn-labels.cjs && \
    npm run build

# ── Final: nginx serving image ────────────────────────────────────────────────
# Alpine-based image eliminates all Debian-specific CVEs (libde265, libheif,
# libexpat1, libnghttp2, libsystemd, ncurses) that have no upstream fix yet.
FROM nginx:1.29.2-alpine

# Install only required utilities
RUN apk update && \
    apk upgrade && \
    apk add --no-cache bash dos2unix && \
    rm -rf /var/cache/apk/*

# Remove default nginx configuration
RUN rm -rf /etc/nginx/conf.d/*

# Copy the nginx configuration file from the core frontend
COPY m8flow-frontend/docker_build/nginx.conf.template /var/tmp

# Default internal port for nginx inside the container.
# Orchestrators and docker compose both route traffic to containerPort 8080,
# so make the image listen on 8080 by default. Can be overridden
# by setting SPIFFWORKFLOW_FRONTEND_INTERNAL_PORT explicitly.
ENV SPIFFWORKFLOW_FRONTEND_INTERNAL_PORT=8080

# Copy the built static files from the extension frontend into the nginx directory
COPY --from=setup /app/m8flow-frontend/dist /usr/share/nginx/html

# Optionally expose the core frontend dist under a sub-path if needed
# (keeps behavior flexible without changing upstream code).
COPY --from=setup /app/spiffworkflow-frontend/dist /usr/share/nginx/html/spiff

# Reuse core frontend helper scripts (including boot_server_in_docker)
COPY --from=fetch-upstream /upstream/spiffworkflow-frontend/bin /app/bin

# m8flow wrapper: maps BACKEND_BASE_URL / MULTI_TENANT_ON into SPIFFWORKFLOW_FRONTEND_RUNTIME_CONFIG_* then runs boot_server_in_docker
COPY docker/scripts/m8flow_frontend_entrypoint.sh /app/bin/

# Fix line endings (CRLF to LF) for shell scripts using dos2unix
RUN dos2unix /app/bin/boot_server_in_docker /app/bin/m8flow_frontend_entrypoint.sh && \
    chmod +x /app/bin/boot_server_in_docker /app/bin/m8flow_frontend_entrypoint.sh

CMD ["/app/bin/m8flow_frontend_entrypoint.sh"]
