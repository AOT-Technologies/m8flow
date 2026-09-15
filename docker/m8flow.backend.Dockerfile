# ── m8flow-backend image (m8flow-bpmn-core wheel, no SpiffArena vendor trees) ──
ARG UV_VERSION=0.7.2
ARG PYTHON_BASE=docker.io/m8flow/m8flow-python-base:ubuntu24.04-py3.12

FROM ${PYTHON_BASE} AS builder

WORKDIR /app
ENV DEBIAN_FRONTEND=noninteractive

COPY m8flow-backend /app/m8flow-backend
COPY m8flow-telemetry /app/m8flow-telemetry
COPY uvicorn-log.yaml /app/uvicorn-log.yaml

RUN uv venv /opt/venv \
  && uv pip install --python /opt/venv/bin/python setuptools wheel \
  && uv pip install --python /opt/venv/bin/python "/app/m8flow-backend" \
  && uv pip install --python /opt/venv/bin/python "/app/m8flow-telemetry[flask,asgi]" \
  && uv pip install --python /opt/venv/bin/python flower "flask>=3.1.3"

FROM ${PYTHON_BASE} AS prod

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

FROM ${PYTHON_BASE} AS dev

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
