FROM python:3.11.6-slim-bookworm AS base

ENV VIRTUAL_ENV=/app/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

FROM base AS deployment

RUN apt-get update \
  && apt-get clean -y \
  && apt-get install -y -q git-core curl procps gunicorn3 default-mysql-client vim-tiny libkrb5support0 libexpat1 libsqlite3-0=3.40.1-2+deb12u2 \
  && rm -rf /var/lib/apt/lists/*

RUN pip install poetry==1.6.1


FROM base AS setup

RUN pip install poetry==1.6.1
RUN useradd _gunicorn --no-create-home --user-group

RUN apt-get update \
  && apt-get install -y -q gcc libssl-dev pkg-config libsqlite3-0=3.40.1-2+deb12u2

COPY pyproject.toml poetry.lock /app/

COPY . /app
RUN chmod +x bin/*
RUN poetry lock --no-update && poetry install


FROM deployment AS final

COPY --from=setup /app /app

CMD ["./bin/boot_server_in_docker"]
