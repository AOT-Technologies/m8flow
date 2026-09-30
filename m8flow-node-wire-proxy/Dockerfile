# FastAPI host over node-wire runtime + http_generic + the m8flow connectors
# (no spiffworkflow-proxy).
# Build context: repository root (needs vendor/wheels linux_* staged).
FROM python:3.12.1-slim-bookworm AS base

ENV VIRTUAL_ENV=/app/venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NW_ALLOWED_CONNECTORS=http_generic,m8flow_github,m8flow_n8n,m8flow_smtp,m8flow_slack,m8flow_salesforce,m8flow_stripe,m8flow_postgres \
    PATH="/app/venv/bin:$PATH"

RUN python3 -m venv "$VIRTUAL_ENV"
WORKDIR /app

FROM base AS setup

COPY m8flow-node-wire-proxy/pyproject.toml m8flow-node-wire-proxy/README.md /app/
COPY m8flow-node-wire-proxy/src /app/src
COPY m8flow-node-wire-proxy/vendor/wheels /app/vendor/wheels

# Pick linux wheel tag for the image architecture.
# Use dash-compatible `set -eu` (slim image /bin/sh has no pipefail).
RUN set -eu; \
  arch="$(uname -m)"; \
  case "$arch" in \
    aarch64|arm64) tag=linux_aarch64 ;; \
    x86_64|amd64) tag=linux_x86_64 ;; \
    *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
  esac; \
  runtime="$(echo /app/vendor/wheels/node_wire_runtime-*-${tag}.whl)"; \
  httpg="$(echo /app/vendor/wheels/node_wire_http_generic-*-${tag}.whl)"; \
  test -f "$runtime" && test -f "$httpg"; \
  m8flow=""; \
  for name in github n8n smtp slack salesforce stripe postgres; do \
    wheel="$(echo /app/vendor/wheels/node_wire_m8flow_${name}-*-${tag}.whl)"; \
    test -f "$wheel" || { echo "missing m8flow_${name} wheel for ${tag}" >&2; exit 1; }; \
    m8flow="$m8flow $wheel"; \
  done; \
  pip install --no-cache-dir -e . "$runtime" "$httpg" $m8flow

COPY m8flow-node-wire-proxy/bin /app/bin
RUN chmod +x /app/bin/*

FROM base AS final
USER root
RUN apt-get update \
  && apt-get install -y -q --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/*
COPY --from=setup /app /app
COPY --from=setup /app/venv /app/venv
WORKDIR /app
EXPOSE 6844
CMD ["./bin/boot_server_in_docker"]
