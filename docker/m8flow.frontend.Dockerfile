FROM node:24.10.0-trixie-slim AS base

RUN mkdir /app
WORKDIR /app

# Build deps and debug tools (curl, procps, vim-tiny).
RUN apt-get update \
  && apt-get clean -y \
  && apt-get install -y -q \
  curl \
  procps \
  vim-tiny \
  libkrb5support0 \
  libexpat1 \
  && rm -rf /var/lib/apt/lists/*

# Node heap for build (matches demo).
ENV NODE_OPTIONS=--max_old_space_size=4096

# --- Setup: build core + extension frontends
FROM base AS setup

# Copy repo for spiffworkflow-frontend and extensions/frontend.
WORKDIR /app
COPY . /app

# Build upstream spiffworkflow-frontend.
WORKDIR /app/spiffworkflow-frontend

# npm ci when lockfile present, else npm install; then build.
RUN if [ -f package-lock.json ]; then \
      npm ci; \
    else \
      npm install; \
    fi && \
    npm run build

# Build m8flow extension frontend.
WORKDIR /app/extensions/frontend

# Copy core python worker for extension build (no upstream change).
RUN mkdir -p public/src/workers && \
    cp /app/spiffworkflow-frontend/src/workers/python.ts public/src/workers/python.ts

# npm ci --ignore-scripts then build (OWASP NPM Security Cheat Sheet).
RUN npm ci --ignore-scripts && \
    npm run build

# --- Final: nginx serving static assets
FROM nginx:1.29.2-alpine

# bash for entry script; pcre2 upgrade for CVE (remove when base has 10.46).
RUN apk add --no-cache bash && apk add --upgrade pcre2

# Remove default nginx configuration
RUN rm -rf /etc/nginx/conf.d/*

# Nginx template (port substituted at runtime).
COPY spiffworkflow-frontend/docker_build/nginx.conf.template /var/tmp

# Extension frontend static files.
COPY --from=setup /app/extensions/frontend/dist /usr/share/nginx/html

# Core frontend at /spiff.
COPY --from=setup /app/spiffworkflow-frontend/dist /usr/share/nginx/html/spiff

# Entry script inlined for same behavior on Mac and Windows.
RUN mkdir -p /app/bin && printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -e' \
  'port="${SPIFFWORKFLOW_FRONTEND_INTERNAL_PORT:-80}"' \
  'sed "s/{{SPIFFWORKFLOW_FRONTEND_INTERNAL_PORT}}/$port/g" /var/tmp/nginx.conf.template > /etc/nginx/conf.d/default.conf' \
  'exec nginx -g "daemon off;"' \
  > /app/bin/nginx-frontend-start.sh && chmod +x /app/bin/nginx-frontend-start.sh

CMD ["/app/bin/nginx-frontend-start.sh"]
