# -----------------------------------------------------------------------------
# Stage: builder (for prod) - install backend non-editable into venv
# -----------------------------------------------------------------------------
FROM python:3.12.1-slim-bookworm AS builder

WORKDIR /app

# Build deps for backend (git/ssl, libpq for psycopg2, etc.)
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

RUN pip install --upgrade pip && pip install uv

# Copy only backend and extension trees (slimmer context; .dockerignore helps)
COPY spiffworkflow-backend /app/spiffworkflow-backend
COPY extensions /app/extensions

# Create venv and install backend non-editable (prod)
RUN uv venv /opt/venv \
  && /opt/venv/bin/uv pip install /app/spiffworkflow-backend

# Fix CRLF and make run script executable
RUN sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh \
  && chmod +x /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh

# -----------------------------------------------------------------------------
# Stage: prod - minimal runtime image for AWS Linux / production
# -----------------------------------------------------------------------------
FROM python:3.12.1-slim-bookworm AS prod

WORKDIR /app

# Runtime deps only (no build-essential, no git)
RUN apt-get update \
  && apt-get install -y -q \
    bash \
    ca-certificates \
    libpq5 \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

CMD ["./extensions/m8flow-backend/bin/run_m8flow_backend.sh"]

# -----------------------------------------------------------------------------
# Stage: dev (default) - full repo, editable install for local development
# -----------------------------------------------------------------------------
FROM python:3.12.1-slim-bookworm AS dev

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

RUN pip install --upgrade pip && pip install uv

COPY . /app

RUN cd /app/spiffworkflow-backend && uv pip install --system -e .

RUN sed -i 's/\r$//' /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh \
  && chmod +x /app/extensions/m8flow-backend/bin/run_m8flow_backend.sh

CMD ["./extensions/m8flow-backend/bin/run_m8flow_backend.sh"]
