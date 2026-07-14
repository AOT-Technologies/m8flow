# m8flow MCP Server — Production Multi-Stage Build
# syntax=docker/dockerfile:1.4

ARG PYTHON_VERSION=3.12-slim-bookworm

# =============================================================================
# Stage 1: Builder - Install dependencies in isolated venv
# =============================================================================
FROM python:${PYTHON_VERSION} AS builder

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

# Copy dependency files
COPY pyproject.toml README.md ./

# Install Python dependencies (production only, no dev deps)
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# =============================================================================
# Stage 2: Runtime - Slim production image
# =============================================================================
FROM python:${PYTHON_VERSION} AS runtime

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

# Create non-root user and directories
RUN groupadd --gid 10001 mcp && \
    useradd --uid 10001 --gid mcp --home-dir /app --shell /usr/sbin/nologin mcp && \
    mkdir -p /app /app/.local /tmp/.local/share /tmp/.cache && \
    chown -R mcp:mcp /app /tmp/.local /tmp/.cache

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=mcp:mcp src/ ./src/
COPY --chown=mcp:mcp pyproject.toml ./

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
