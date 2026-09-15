FROM python:3.12.1-slim-bookworm AS base

ENV VIRTUAL_ENV=/app/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

FROM base AS deployment

RUN apt-get update \
  && apt-get install -y -q git-core curl procps gunicorn3 default-mysql-client vim-tiny libkrb5support0 libexpat1 libsqlite3-0=3.40.1-2+deb12u2 \
  && apt-get clean -y \
  && rm -rf /var/lib/apt/lists/*

RUN /usr/local/bin/pip install poetry==2.2.1


FROM base AS setup

RUN /usr/local/bin/pip install poetry==2.2.1
RUN poetry config virtualenvs.create false
RUN useradd _gunicorn --no-create-home --user-group

RUN apt-get update \
  && apt-get install -y -q gcc git libssl-dev pkg-config libsqlite3-0=3.40.1-2+deb12u2 \
  && rm -rf /var/lib/apt/lists/*

COPY m8flow-telemetry /m8flow-telemetry
COPY m8flow-connector-proxy/pyproject.toml m8flow-connector-proxy/poetry.lock m8flow-connector-proxy/README.md /app/
RUN poetry check --lock \
  && poetry install --no-interaction --no-root --sync

COPY m8flow-connector-proxy/ /app/
RUN chmod +x bin/*
RUN poetry install --no-interaction --no-root


FROM deployment AS final

COPY --from=setup /app /app

CMD ["./bin/boot_server_in_docker"]
