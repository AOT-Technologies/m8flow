# m8flow MCP Server — Production Multi-Stage Build
# syntax=docker/dockerfile:1.4
#
# Build context is the repo root: m8flow-telemetry is a uv path dependency
# (../m8flow-telemetry) that pip cannot resolve from inside m8flow-mcp/.
#   docker build -f m8flow-mcp/Dockerfile .

# Pin the multi-platform image index. Dependabot checks Docker bases weekly;
# merge its updates to pick up Python and Debian security fixes deterministically.
ARG PYTHON_IMAGE=python:3.13.18-slim-trixie@sha256:76baad6037690d6e8c4397fbcaef17bca6f19eecef822b708fe8fa3417d30bb5

# =============================================================================
# Stage 1: Builder - Install dependencies in isolated venv
# =============================================================================
FROM ${PYTHON_IMAGE} AS builder

LABEL stage=builder

WORKDIR /build

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# m8flow-telemetry first, so pip finds the m8flow-telemetry[asgi] requirement
# already satisfied (pip ignores [tool.uv.sources]).
COPY m8flow-telemetry /build/m8flow-telemetry
RUN pip install --no-cache-dir "/build/m8flow-telemetry[asgi]"

# Copy dependency files
COPY m8flow-mcp/pyproject.toml m8flow-mcp/README.md ./

# Install Python dependencies (production only, no dev deps)
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# =============================================================================
# Stage 2: Runtime - Slim production image
# =============================================================================
FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="m8flow-mcp" \
      org.opencontainers.image.description="Model Context Protocol server for m8flow workflow management (PRODUCTION)" \
      org.opencontainers.image.vendor="AOT Technologies" \
      org.opencontainers.image.source="https://github.com/AOT-Technologies/m8flow-mcp" \
      org.opencontainers.image.licenses="Apache-2.0" \
      environment="production"

WORKDIR /app

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOME=/app \
    XDG_DATA_HOME=/tmp/.local/share \
    XDG_CACHE_HOME=/tmp/.cache \
    PORT=8000 \
    SERVER_TYPE=remote \
    LOG_LEVEL=WARNING \
    ENVIRONMENT=production

# The base image also ships global setuptools; upgrade it with pip so the
# runtime layer does not retain the vulnerable base version.
RUN /usr/local/bin/pip install --no-cache-dir --root-user-action=ignore --upgrade pip setuptools

# Purge util-linux (with the libraries it alone needs), perl-base, the ncurses
# packages bash does not need and libsqlite3-0 (only Python's unused sqlite3
# module links it): the base ships them, nothing here runs them, and they carry
# Trivy/Grype findings Debian has no fix for. No apt or dpkg runs after this, so
# the missing Essential packages do not matter.
RUN apt-get purge -y --allow-remove-essential util-linux bsdutils mount login libmount1 \
    libsmartcols1 libblkid1 libuuid1 liblastlog2-2 perl-base ncurses-bin ncurses-base libncursesw6 \
    libsqlite3-0

# Create non-root user and directories
RUN groupadd --gid 10001 mcp && \
    useradd --uid 10001 --gid mcp --home-dir /app --shell /usr/sbin/nologin mcp && \
    mkdir -p /app /app/.local /tmp/.local/share /tmp/.cache && \
    chown -R mcp:mcp /app /tmp/.local /tmp/.cache

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=mcp:mcp m8flow-mcp/src/ ./src/
COPY --chown=mcp:mcp m8flow-mcp/pyproject.toml ./

# libsqlite3-0 is purged above. Fail the build if startup imports sqlite3 (the
# import raises ImportError), or if any module loaded at startup or under src/
# imports it anywhere, including inside functions. Dependency modules the app
# never loads are not checked. If it needs sqlite3, take libsqlite3-0 off the
# purge list.
RUN LOG_LEVEL=ERROR python -c "import pathlib, re, sys, src.main; \
    pat = re.compile(r'^\s*(from|import)\s+(dbm\.)?sqlite3\b', re.M); \
    loaded = {getattr(m, '__file__', None) or '' for m in list(sys.modules.values())}; \
    files = {f for f in loaded if f.startswith(('/app/', '/opt/venv/')) and f.endswith('.py')} | {str(p) for p in pathlib.Path('/app/src').rglob('*.py')}; \
    bad = sorted(f for f in files if pat.search(pathlib.Path(f).read_text(encoding='utf-8', errors='replace'))); \
    sys.exit('sqlite3 is imported, but libsqlite3-0 is purged: ' + ', '.join(bad) if bad else None)"

# Switch to non-root user
USER mcp

# Expose port for HTTP mode (Cursor / streamable-http)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD python -c "import os,urllib.request; p=os.environ.get('PORT','8000'); urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=5)" || exit 1

# Default command - runs in HTTP mode
# For stdio mode (Claude Desktop), override CMD with: ["python", "-m", "src.main"]
CMD ["python", "-m", "src.main"]
