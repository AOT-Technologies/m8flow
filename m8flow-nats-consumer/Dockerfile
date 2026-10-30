FROM python:3.15.0-slim-trixie

# Keep the package source immutable. Update this timestamp with the package pins.
ARG DEBIAN_SNAPSHOT=20261027T000000Z

# Use the Debian fixed releases for ACL, attr, and zlib. Trixie currently
# inherits affected package versions from the upstream Python image.
RUN printf '%s\n' "deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ sid main" \
      > /etc/apt/sources.list.d/sid.list \
  && printf '%s\n' 'Package: libacl1 libattr1 zlib1g' 'Pin: release a=unstable' 'Pin-Priority: 1001' '' 'Package: *' 'Pin: release a=unstable' 'Pin-Priority: -1' \
      > /etc/apt/preferences.d/sid \
  && apt-get update \
  && apt-get install -y --no-install-recommends \
      libacl1=2.4.0-1 \
      libattr1=1:2.6.0-1 \
      zlib1g=1:1.3.dfsg+really1.3.2-4 \
  && rm -rf /var/lib/apt/lists/* \
  && rm -f /etc/apt/sources.list.d/sid.list /etc/apt/preferences.d/sid

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependencies list
COPY pyproject.toml .
COPY README.md .

# Install dependencies into system site-packages so python can find them directly
RUN uv pip install --system .

# Create a non-root user and switch to it
RUN useradd -m -s /bin/bash m8flow
USER m8flow

# Copy source without changing ownership to the non-root user
# This prevents the m8flow user from modifying the executable source code
COPY trigger_event_consumer.py .

# Run consumer
CMD ["python", "trigger_event_consumer.py"]
