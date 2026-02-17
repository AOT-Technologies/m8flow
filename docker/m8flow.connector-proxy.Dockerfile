FROM python:3.11-slim AS base

WORKDIR /app

RUN pip install --upgrade pip
RUN pip install poetry==1.8.1

# Configure poetry to create virtualenvs in the project directory
ENV POETRY_VIRTUALENVS_IN_PROJECT=true

# Copy dependency files and local packages first
COPY pyproject.toml poetry.lock ./
COPY connector-example ./connector-example

# Install dependencies
RUN poetry install --no-root --no-interaction

# Add virtualenv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy the rest of the application
COPY . .

# Default port
ENV CONNECTOR_PROXY_PORT=8004

EXPOSE ${CONNECTOR_PROXY_PORT}

CMD ["./bin/boot_server_in_docker"]
