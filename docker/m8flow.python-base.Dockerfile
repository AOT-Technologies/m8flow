# ── m8flow shared Python/Ubuntu base image ───────────────────────────────────
# Reusable base for m8flow backend-related images (API, Celery worker, flower).
# It carries the OS toolchain + Python + uv so service builds don't reinstall them
# from scratch on every build.
#
# Published as: docker.io/m8flow/m8flow-python-base:ubuntu24.04-py3.12
# Rebuilt + pushed via .github/workflows/build-base-image.yml.
# Consumed by docker/m8flow.backend.Dockerfile via the PYTHON_BASE build arg.
# See docs/docker-base-image.md for the rebuild process and dependency ownership.
#
# Scope: OS/toolchain dependencies ONLY. Application dependencies stay in the
# service images so the base stays lean and broadly reusable.

FROM ubuntu:24.04

# Pin uv globally so every consumer uses the same audited release.
# Update periodically: https://github.com/astral-sh/uv/releases
ARG UV_VERSION=0.7.2
ENV DEBIAN_FRONTEND=noninteractive

# Common OS toolchain + build deps for backend services:
#   build-essential / python3-dev / pkg-config  - compile native wheels
#   libpq-dev                                    - psycopg2 (pulls in libpq5 runtime)
#   default-libmysqlclient-dev                   - mysqlclient (pulls in libmariadb3 runtime)
#   gosu                                         - entrypoint drops root -> app user
#   git / curl / ca-certificates / openssl       - fetch deps over TLS
RUN apt-get update \
  && apt-get install -y -q --no-install-recommends \
    bash \
    build-essential \
    curl \
    git \
    ca-certificates \
    openssl \
    libpq-dev \
    default-libmysqlclient-dev \
    pkg-config \
    gosu \
    python3 \
    python3-venv \
    python3-dev \
    python-is-python3 \
  && apt-get upgrade -y \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && git config --global http.sslVerify true \
  && git config --global http.sslCAInfo /etc/ssl/certs/ca-certificates.crt

# Install pinned uv via official binary installer (avoids pip-installed tool attack surface)
RUN curl -fsSL https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin UV_VERSION=${UV_VERSION} sh \
  && uv --version
