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

ARG TARGETARCH
RUN arch="${TARGETARCH:-$(uname -m)}"; \
  case "$arch" in \
    amd64|x86_64) ;; \
    *) echo "ERROR: m8flow-node-wire-proxy supports linux/amd64 only. The committed node-wire wheels and uv.lock target CPython 3.12 linux_x86_64; linux/arm64 wheels are not available. Build with --platform linux/amd64. Native ARM64 support requires the complete v1.1.0 linux_aarch64 wheel set and corresponding uv.lock sources." >&2; exit 1 ;; \
  esac

COPY m8flow-node-wire-proxy/pyproject.toml m8flow-node-wire-proxy/README.md /app/
COPY m8flow-node-wire-proxy/uv.lock /app/uv.lock
COPY m8flow-node-wire-proxy/src /app/src
COPY m8flow-node-wire-proxy/vendor/wheels /app/vendor/wheels

# Resolve and install the frozen host dependencies and committed x86_64 wheels.
# uv is a build-only tool; it is installed in this stage, not the final image.
ENV UV_PROJECT_ENVIRONMENT=/app/venv
RUN /usr/local/bin/pip install --no-cache-dir uv==0.11.1 \
  && uv sync --frozen --no-dev

COPY m8flow-node-wire-proxy/bin /app/bin
RUN chmod +x /app/bin/*

FROM base AS final
USER root
# No curl: the compose healthcheck probes /liveness with Python.
# Purge util-linux (with the libraries it alone needs), perl-base, the ncurses
# packages bash does not need and libsqlite3-0 (only Python's unused sqlite3
# module links it): the base ships them, nothing here runs them, and they carry
# Trivy findings Debian has no fix for. No apt or dpkg runs after this, so the
# missing Essential packages do not matter.
RUN apt-get update \
  && apt-get upgrade -y -q \
  && apt-get purge -y --allow-remove-essential util-linux bsdutils mount login libmount1 \
    libsmartcols1 libblkid1 libuuid1 liblastlog2-2 perl-base ncurses-bin ncurses-base libncursesw6 \
    libsqlite3-0 \
  && rm -rf /var/lib/apt/lists/*
COPY --from=setup /app /app
COPY --from=setup /app/venv /app/venv
WORKDIR /app
# root was only needed for apt-get; run the server unprivileged (port 6844).
RUN useradd --system --create-home --user-group m8flow
# libsqlite3-0 is purged above. Load what startup loads (the app, http_generic
# and every m8flow connector) and fail the build if that raises ImportError, or
# if any loaded module under /app imports sqlite3 anywhere, including inside
# functions. If it needs sqlite3, take libsqlite3-0 off the purge list.
RUN M8FLOW_CONNECTOR_PROXY_API_KEY=build-check python -c "import ast, pathlib, sys; \
    import m8flow_node_wire_proxy.app; from m8flow_node_wire_proxy import node_wire_gateway as g; \
    from m8flow_node_wire_proxy.catalog import M8FLOW_CONNECTOR_IDS as ids; \
    g.get_http_generic_connector(); [g.get_m8flow_connector(c) for c in set(ids.values())]; \
    sq = lambda m: m in ('sqlite3', 'dbm.sqlite3') or str(m).startswith(('sqlite3.', 'dbm.sqlite3.')); \
    hit = lambda n: isinstance(n, ast.Import) and any(sq(a.name) for a in n.names) \
      or isinstance(n, ast.ImportFrom) and not n.level \
      and (sq(n.module) or n.module == 'dbm' and any(a.name == 'sqlite3' for a in n.names)); \
    loaded = {getattr(m, '__file__', None) or '' for m in list(sys.modules.values())}; \
    files = {f for f in loaded if f.startswith('/app/') and f.endswith('.py')}; \
    bad = sorted(f for f in files if any(map(hit, ast.walk(ast.parse(pathlib.Path(f).read_bytes()))))); \
    sys.exit('sqlite3 is imported, but libsqlite3-0 is purged: ' + ', '.join(bad) if bad else None)"
USER m8flow
EXPOSE 6844
CMD ["./bin/boot_server_in_docker"]
