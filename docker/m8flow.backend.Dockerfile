FROM python:3.12.1-slim-bookworm

WORKDIR /app

RUN apt-get update \
  && apt-get install -y -q \
    bash \
    build-essential \
       git \
    ca-certificates \
    openssl \
    libpq-dev \
    default-libmysqlclient-dev \
    pkg-config \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && git config --global http.sslVerify true \
  && git config --global http.sslCAInfo /etc/ssl/certs/ca-certificates.crt

RUN pip install --upgrade pip \
  && pip install uv flower

COPY . /app

RUN cd /app/spiffworkflow-backend && uv pip install --system -e .

# Fix line endings (CRLF to LF) for shell scripts before running
RUN sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh \
  && sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh \
  && chmod +x /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh /app/extensions/m8flow-backend/bin/run_m8flow_celery_worker.sh

CMD ["./extensions/m8flow-backend/bin/run_m8flow_backend.sh"]
