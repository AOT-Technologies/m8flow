# ── m8flow-backend image (m8flow-bpmn-core wheel, no SpiffArena vendor trees) ──
ARG UV_VERSION=0.7.2
ARG PYTHON_BASE=docker.io/m8flow/m8flow-python-base:ubuntu24.04-py3.12

FROM ubuntu:24.04 AS gosu-downloader

# Override the gosu inherited from older shared-base tags until they are rebuilt.
ARG GOSU_VERSION=1.19
ARG TARGETARCH
RUN apt-get update \
  && apt-get install -y -q --no-install-recommends ca-certificates curl gnupg \
  && mkdir -p /usr/local/bin /tmp/gosu-keyring \
  && curl -fsSL "https://keys.openpgp.org/vks/v1/by-fingerprint/B42F6819007F00F88E364FD4036A9C25BF357DD4" \
    | gpg --batch --homedir /tmp/gosu-keyring --import \
  && gpg --batch --homedir /tmp/gosu-keyring --with-colons --list-keys \
    | awk -F: '$1 == "fpr" { print $10; exit }' \
    | grep -Fx "B42F6819007F00F88E364FD4036A9C25BF357DD4" \
  && curl -fsSL "https://github.com/tianon/gosu/releases/download/${GOSU_VERSION}/gosu-${TARGETARCH}" -o /usr/local/bin/gosu \
  && curl -fsSL "https://github.com/tianon/gosu/releases/download/${GOSU_VERSION}/gosu-${TARGETARCH}.asc" -o /tmp/gosu.asc \
  && gpg --batch --homedir /tmp/gosu-keyring --verify /tmp/gosu.asc /usr/local/bin/gosu \
  && chmod 0755 /usr/local/bin/gosu \
  && /usr/local/bin/gosu --version \
  && rm -rf /tmp/gosu-keyring /tmp/gosu.asc /var/lib/apt/lists/*

FROM ${PYTHON_BASE} AS patched-base

COPY --from=gosu-downloader /usr/local/bin/gosu /usr/local/bin/gosu

ENV DEBIAN_FRONTEND=noninteractive

# Refresh Ubuntu packages at the service-image build boundary as well as in
# the scheduled shared-base build. This prevents stale cached base tags from
# carrying vulnerable runtime packages into Backend images.
RUN apt-get update \
  && apt-get upgrade -y \
  && if dpkg -s gosu >/dev/null 2>&1; then apt-get purge -y gosu; fi \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

FROM patched-base AS builder

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

COPY m8flow-backend /app/m8flow-backend
COPY m8flow-telemetry /app/m8flow-telemetry
# The NATS consumer and notification worker run from this image (python m8flow-nats-consumer/<script>.py).
COPY m8flow-nats-consumer /app/m8flow-nats-consumer
COPY uvicorn-log.yaml /app/uvicorn-log.yaml

RUN uv venv /opt/venv \
  && uv pip install --python /opt/venv/bin/python setuptools wheel \
  && uv pip install --python /opt/venv/bin/python "/app/m8flow-backend" \
  && uv pip install --python /opt/venv/bin/python "/app/m8flow-telemetry[flask,asgi]" \
  && uv pip install --python /opt/venv/bin/python flower "flask>=3.1.3"

FROM patched-base AS prod

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

RUN userdel -r ubuntu || true; groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app /opt/venv

ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

RUN sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/m8flow-backend/bin/run_m8flow_backend.sh /app/m8flow-backend/bin/run_m8flow_celery_worker.sh

COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

USER app
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/m8flow-backend/bin/run_m8flow_backend.sh"]

FROM patched-base AS dev

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

COPY . /app

RUN uv pip install --system --break-system-packages "/app/m8flow-backend" \
  && uv pip install --system --break-system-packages flower "flask>=3.1.3" \
  && uv pip install --system --break-system-packages "/app/m8flow-telemetry[flask,asgi]" \
  && uv cache clean

RUN sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/m8flow-backend/bin/run_m8flow_backend.sh /app/m8flow-backend/bin/run_m8flow_celery_worker.sh

COPY docker/scripts/m8flow_backend_entrypoint.sh /opt/m8flow-backend-entrypoint.sh
RUN sed -i 's/\r$//' /opt/m8flow-backend-entrypoint.sh \
  && chmod +x /opt/m8flow-backend-entrypoint.sh

RUN userdel -r ubuntu || true; groupadd -r app -g 1000 && useradd -r -u 1000 -g app -d /app -s /bin/bash app \
  && chown -R app:app /app

USER app
ENTRYPOINT ["/opt/m8flow-backend-entrypoint.sh"]
CMD ["/app/m8flow-backend/bin/run_m8flow_backend.sh"]
