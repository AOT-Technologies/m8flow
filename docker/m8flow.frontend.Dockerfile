FROM node:24.10.0-trixie-slim AS base

RUN mkdir /app
WORKDIR /app

# curl for debugging
# procps for debugging
# vim ftw
RUN apt-get update \
  && apt-get clean -y \
  && apt-get install -y -q \
  curl \
  procps \
  vim-tiny \
  libkrb5support0 \
  libexpat1 \
  && rm -rf /var/lib/apt/lists/*

# this matches total memory on spiffworkflow-demo
ENV NODE_OPTIONS=--max_old_space_size=4096

######################## - SETUP
# Setup image for installing JS dependencies and building both
# the core spiffworkflow-frontend and the m8flow extension frontend.
FROM base AS setup

# Copy the full repo so that both spiffworkflow-frontend and extensions/m8flow-frontend are available.
WORKDIR /app
COPY . /app

########################
# Build upstream spiffworkflow-frontend
########################
WORKDIR /app/spiffworkflow-frontend

# Install core frontend dependencies and build the app.
# Use npm ci when a lockfile is present (for reproducibility),
# otherwise fall back to npm install.
RUN if [ -f package-lock.json ]; then \
      npm ci; \
    else \
      npm install; \
    fi && \
    npm run build

########################
# Build the m8flow extension frontend
########################
WORKDIR /app/extensions/m8flow-frontend

# Ensure the python worker from the core frontend is available at the
# path expected by the build tooling, without modifying upstream code.
RUN mkdir -p public/src/workers && \
    cp /app/spiffworkflow-frontend/src/workers/python.ts public/src/workers/python.ts

# npm ci because it respects the lock file.
# --ignore-scripts because authors can do bad things in postinstall scripts.
# https://cheatsheetseries.owasp.org/cheatsheets/NPM_Security_Cheat_Sheet.html
# npx can-i-ignore-scripts can check that it's safe to ignore scripts.
RUN npm ci --ignore-scripts && \
    npm run build

######################## - FINAL

# Use nginx as the base image
FROM nginx:1.29.2-alpine

# we sort of love bash too much to use sh
RUN apk add --no-cache bash dos2unix

# to fix security vulnerability:
# remove this line once the base image has the secure version of this lib (10.46)
RUN apk add --upgrade pcre2

# Remove default nginx configuration
RUN rm -rf /etc/nginx/conf.d/*

# Copy the nginx configuration file from the core frontend
COPY spiffworkflow-frontend/docker_build/nginx.conf.template /var/tmp

# Copy the built static files from the extension frontend into the nginx directory
COPY --from=setup /app/extensions/m8flow-frontend/dist /usr/share/nginx/html

# Optionally expose the core frontend dist under a sub-path if needed
# (keeps behavior flexible without changing upstream code).
COPY --from=setup /app/spiffworkflow-frontend/dist /usr/share/nginx/html/spiff

# Reuse core frontend helper scripts (including boot_server_in_docker)
COPY --from=setup /app/spiffworkflow-frontend/bin /app/bin

# Fix line endings (CRLF to LF) for shell scripts using dos2unix
RUN dos2unix /app/bin/boot_server_in_docker && \
    chmod +x /app/bin/boot_server_in_docker

CMD ["/app/bin/boot_server_in_docker"]