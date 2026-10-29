# FastAPI host over node-wire runtime + http_generic + the m8flow connectors
# (no spiffworkflow-proxy).
# Build context: repository root (needs vendor/wheels linux_* staged).
FROM python:3.12-slim-trixie AS base

ENV VIRTUAL_ENV=/app/venv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NW_ALLOWED_CONNECTORS=http_generic,m8flow_github,m8flow_n8n,m8flow_smtp,m8flow_slack,m8flow_salesforce,m8flow_stripe,m8flow_postgres \
    PATH="/app/venv/bin:$PATH"

# Upgrade both environments' packaging tools and the base image's setuptools.
RUN python3 -m venv "$VIRTUAL_ENV" \
  && "$VIRTUAL_ENV/bin/pip" install --no-cache-dir --upgrade pip setuptools \
  && /usr/local/bin/pip install --no-cache-dir --upgrade pip setuptools
WORKDIR /app

FROM base AS setup

COPY m8flow-node-wire-proxy/pyproject.toml m8flow-node-wire-proxy/README.md /app/
COPY m8flow-node-wire-proxy/uv.lock /app/uv.lock
COPY m8flow-node-wire-proxy/src /app/src
COPY m8flow-node-wire-proxy/vendor/wheels /app/vendor/wheels

# Resolve and install the frozen host dependencies and committed x86_64 wheels.
# uv is a build-only tool; it is installed in this stage, not the final image.
ENV UV_PROJECT_ENVIRONMENT=/app/venv
RUN /usr/local/bin/pip install --no-cache-dir uv==0.11.1 \
  && uv sync --frozen --no-dev

# The lock includes the committed linux_x86_64 wheels. For staged arm64 wheels,
# keep the same pinned package version and use the locked public dependencies.
RUN set -eu; \
  arch="$(uname -m)"; \
  case "$arch" in \
    x86_64|amd64) exit 0 ;; \
    aarch64|arm64) tag=linux_aarch64 ;; \
    *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
  esac; \
  choose_wheel() { \
    package="$1"; \
    wheel="$(find /app/vendor/wheels -maxdepth 1 -type f -name "${package}-1.1.0-*-${tag}.whl" -print)"; \
    test -n "$wheel" || { echo "missing locked wheel for ${package} (${tag})" >&2; exit 1; }; \
    printf '%s\n' "$wheel"; \
  }; \
  wheels="$(choose_wheel node_wire_runtime) $(choose_wheel node_wire_http_generic)"; \
  for name in github n8n smtp slack salesforce stripe postgres; do \
    wheels="$wheels $(choose_wheel node_wire_m8flow_${name})"; \
  done; \
  /app/venv/bin/pip install --no-cache-dir --no-deps $wheels

COPY m8flow-node-wire-proxy/bin /app/bin
RUN chmod +x /app/bin/*

FROM base AS final
USER root
# No curl: the compose healthcheck probes /liveness with Python.
RUN apt-get update \
  && apt-get upgrade -y -q \
  && rm -rf /var/lib/apt/lists/*
COPY --from=setup /app /app
COPY --from=setup /app/venv /app/venv
WORKDIR /app
# root was only needed for apt-get; run the server unprivileged (port 6844).
RUN useradd --system --create-home --user-group m8flow
USER m8flow
EXPOSE 6844
CMD ["./bin/boot_server_in_docker"]
