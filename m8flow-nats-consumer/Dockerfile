FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy dependencies list
COPY pyproject.toml .
COPY README.md .

# Install dependencies into system site-packages so python can find them directly
RUN uv pip install --system .

# Copy source
COPY consumer.py .

# Run consumer
CMD ["python", "consumer.py"]
