FROM python:3.12.1-slim-bookworm

WORKDIR /app

# Build and runtime deps; git/ssl for backend.
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

# pip + uv for install.
RUN pip install --upgrade pip \
  && pip install uv

# Install backend in editable mode.
COPY . /app

RUN cd /app/spiffworkflow-backend && uv pip install --system -e .

# Fix CRLF and make run script executable.
RUN sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh && chmod +x /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh

CMD ["./extensions/m8flow-backend/bin/run_m8flow_backend.sh"]
