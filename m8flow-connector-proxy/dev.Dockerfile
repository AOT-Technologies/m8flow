FROM python:3.12.1-slim-bookworm AS base

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

# Non-root by default; dev compose may still override with `user: ${RUN_AS}`.
RUN useradd --system --create-home --user-group m8flow
USER m8flow

CMD ["./bin/run_server_locally"]
