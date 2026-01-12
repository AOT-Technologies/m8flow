FROM python:3.12.1-slim-bookworm

WORKDIR /app

RUN apt-get update \
  && apt-get install -y -q \
    bash \
    build-essential \
    git-core \
    libpq-dev \
    default-libmysqlclient-dev \
    pkg-config \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip \
  && pip install uv

COPY . /app

RUN cd /app/spiffworkflow-backend && uv pip install --system -e .

RUN chmod +x /app/bin/run_m8flow_backend.sh

CMD ["./bin/run_m8flow_backend.sh"]
