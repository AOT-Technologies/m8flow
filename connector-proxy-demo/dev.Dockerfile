FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install --upgrade pip
RUN pip install poetry==1.8.1 pytest-xdist==3.5.0

# Configure poetry to create virtualenvs in the project directory
ENV POETRY_VIRTUALENVS_IN_PROJECT=true

# Copy dependency files
COPY pyproject.toml poetry.lock ./
COPY connector-example ./connector-example

# Install dependencies
RUN poetry install --no-root --no-interaction

# Add virtualenv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy the rest of the application
COPY . .

CMD ["./bin/run_server_locally"]
