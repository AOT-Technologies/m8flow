FROM python:3.12.15-slim-trixie AS base

# Use the Debian fixed releases for ACL, attr, and zlib. Trixie currently
# inherits affected package versions from the upstream Python image.
RUN printf '%s\n' 'deb http://deb.debian.org/debian sid main' \
      > /etc/apt/sources.list.d/sid.list \
  && printf '%s\n' 'Package: *' 'Pin: release a=unstable' 'Pin-Priority: 100' \
      > /etc/apt/preferences.d/sid \
  && apt-get update \
  && apt-get install -y --no-install-recommends \
      libacl1=2.4.0-1 \
      libattr1=1:2.6.0-1 \
      zlib1g=1:1.3.dfsg+really1.3.2-4 \
  && rm -rf /var/lib/apt/lists/* \
  && rm -f /etc/apt/sources.list.d/sid.list /etc/apt/preferences.d/sid

WORKDIR /app

RUN pip install --upgrade pip \
  && pip install poetry==1.8.1 pytest-xdist==3.5.0

# Dev compose bind-mounts the project at /app. Install deps + ensure bin scripts
# are executable even when the host checkout lost the +x bit.
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi --no-root || true

COPY . .
RUN chmod +x bin/* || true

CMD ["./bin/run_server_locally"]
