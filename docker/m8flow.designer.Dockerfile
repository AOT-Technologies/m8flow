# m8flow-designer (primary UI) -- Vite SPA built to static files, served by nginx.
#
# Context is the repo root because m8flow-designer depends on ../m8flow-bpmn
# via a `file:` dependency, so both trees must be in the build context.

FROM node:24.10.0-trixie-slim AS build

ENV NODE_OPTIONS=--max_old_space_size=4096
WORKDIR /app

# m8flow-bpmn first: it changes far less often than designer source, so it
# stays cached across ordinary UI edits. It needs its own install, not just
# its source: the `file:` dependency links the tree but installs nothing for
# it, and both its Vite plugin (esbuild) and the modeler libraries the app
# imports through it (bpmn-js, dmn-js) live in its own node_modules.
COPY m8flow-bpmn/package.json m8flow-bpmn/package-lock.json /app/m8flow-bpmn/
RUN --mount=type=cache,target=/root/.npm \
    cd /app/m8flow-bpmn && npm ci --ignore-scripts
COPY m8flow-bpmn /app/m8flow-bpmn

COPY m8flow-designer/package.json m8flow-designer/package-lock.json /app/m8flow-designer/

WORKDIR /app/m8flow-designer

# --ignore-scripts: authors can do bad things in postinstall scripts.
# https://cheatsheetseries.owasp.org/cheatsheets/NPM_Security_Cheat_Sheet.html
RUN --mount=type=cache,target=/root/.npm npm ci --ignore-scripts

COPY m8flow-designer /app/m8flow-designer

# Baked into the bundle at build time: auth.ts uses it for the Keycloak login
# redirect, so it must be a browser-reachable backend origin, not an in-network
# service name. VITE_API_BASE_URL is deliberately left empty so data fetches
# stay same-origin and go through the nginx /v1.0 proxy below -- the same shape
# as the Vite dev server proxy.
ARG VITE_BACKEND_BASE_URL=http://localhost:6840
ENV VITE_BACKEND_BASE_URL=${VITE_BACKEND_BASE_URL}

# `npm run build` is `tsc --noEmit && vite build`; this runs only the bundling
# half. Typechecking is a workstation/CI gate, not an image-build gate -- and
# it cannot pass here anyway, since m8flow-bpmn's own node_modules (bpmn-js,
# diagram-js type declarations) are not installed in this stage.
RUN npx vite build

FROM nginx:1.29.2-alpine

# NGINX_ENTRYPOINT_LOCAL_RESOLVERS makes 15-local-resolvers.envsh export
# NGINX_LOCAL_RESOLVERS from the container's /etc/resolv.conf; without it that
# script returns early and the template's `resolver` directive would be left
# unsubstituted. Both it and the two config values must appear in the envsubst
# filter, or 20-envsubst-on-templates.sh will not substitute them.
ENV M8FLOW_DESIGNER_INTERNAL_PORT=8080 \
    BACKEND_BASE_URL=http://m8flow-backend:6840 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    NGINX_ENVSUBST_FILTER="^(M8FLOW_DESIGNER_INTERNAL_PORT|BACKEND_BASE_URL|NGINX_LOCAL_RESOLVERS)$$"

RUN rm -rf /etc/nginx/conf.d/*

COPY docker/m8flow-designer-nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/m8flow-designer/dist /usr/share/nginx/html

# The stock nginx:alpine entrypoint envsubsts /etc/nginx/templates/*.template
# into /etc/nginx/conf.d/ and then starts nginx, so no custom entrypoint or
# dos2unix step is needed here (unlike the legacy frontend image).
