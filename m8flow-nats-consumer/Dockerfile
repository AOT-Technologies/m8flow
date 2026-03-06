FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependencies list
COPY pyproject.toml .
COPY README.md .

# Install dependencies into system site-packages so python can find them directly
RUN uv pip install --system .

# Create a non-root user and switch to it
RUN useradd -m -s /bin/bash m8flow
USER m8flow

# Copy source
COPY --chown=m8flow:m8flow consumer.py .

# Run consumer
CMD ["python", "consumer.py"]
