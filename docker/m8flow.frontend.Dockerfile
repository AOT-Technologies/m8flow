# -----------------------------------------------------------------------------
# Base: node + build deps
# -----------------------------------------------------------------------------
FROM node:24.10.0-trixie-slim AS base

RUN mkdir /app
WORKDIR /app

RUN apt-get update \
  && apt-get clean -y \
  && apt-get install -y -q \
    curl \
    procps \
    vim-tiny \
    libkrb5support0 \
    libexpat1 \
  && rm -rf /var/lib/apt/lists/*

ENV NODE_OPTIONS=--max_old_space_size=4096

# -----------------------------------------------------------------------------
# Deps: core frontend (lockfile layer for better cache)
# -----------------------------------------------------------------------------
FROM base AS deps-core
WORKDIR /app/spiffworkflow-frontend
COPY spiffworkflow-frontend/package.json spiffworkflow-frontend/package-lock.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# -----------------------------------------------------------------------------
# Deps: extension frontend
# -----------------------------------------------------------------------------
FROM base AS deps-ext
WORKDIR /app/extensions/frontend
COPY extensions/frontend/package.json extensions/frontend/package-lock.json ./
RUN npm ci --ignore-scripts

# -----------------------------------------------------------------------------
# Build: core frontend (slimmer copy: only spiffworkflow-frontend)
# -----------------------------------------------------------------------------
FROM base AS build-core
WORKDIR /app
COPY spiffworkflow-frontend /app/spiffworkflow-frontend
COPY --from=deps-core /app/spiffworkflow-frontend/node_modules /app/spiffworkflow-frontend/node_modules
WORKDIR /app/spiffworkflow-frontend
RUN npm run build

# -----------------------------------------------------------------------------
# Build: extension frontend (needs core python worker)
# -----------------------------------------------------------------------------
FROM base AS build-ext
WORKDIR /app
COPY extensions/frontend /app/extensions/frontend
COPY --from=deps-ext /app/extensions/frontend/node_modules /app/extensions/frontend/node_modules
RUN mkdir -p /app/extensions/frontend/public/src/workers
COPY --from=build-core /app/spiffworkflow-frontend/src/workers/python.ts /app/extensions/frontend/public/src/workers/python.ts
WORKDIR /app/extensions/frontend
RUN npm run build

# -----------------------------------------------------------------------------
# Final: nginx serving static assets
# -----------------------------------------------------------------------------
FROM nginx:1.29.2-alpine

RUN apk add --no-cache bash && apk add --upgrade pcre2
RUN rm -rf /etc/nginx/conf.d/*

COPY spiffworkflow-frontend/docker_build/nginx.conf.template /var/tmp
COPY --from=build-ext /app/extensions/frontend/dist /usr/share/nginx/html
COPY --from=build-core /app/spiffworkflow-frontend/dist /usr/share/nginx/html/spiff

RUN mkdir -p /app/bin && printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -e' \
  'port="${SPIFFWORKFLOW_FRONTEND_INTERNAL_PORT:-80}"' \
  'sed "s/{{SPIFFWORKFLOW_FRONTEND_INTERNAL_PORT}}/$port/g" /var/tmp/nginx.conf.template > /etc/nginx/conf.d/default.conf' \
  'exec nginx -g "daemon off;"' \
  > /app/bin/nginx-frontend-start.sh && chmod +x /app/bin/nginx-frontend-start.sh

CMD ["/app/bin/nginx-frontend-start.sh"]
