# M8flow Connector Setup Guide

Complete guide for setting up, configuring, and adding new connectors to M8flow.

---

## Overview

M8flow uses **connector-proxy** services to extend functionality by connecting to external systems like databases, APIs, cloud services, and more. All connectors are auto-discovered Python packages prefixed with `connector-*`.

---

## Architecture

```
M8flow Backend (Port 8000)
    ↓ (calls via CONNECTOR_PROXY_URL)
Connector Proxy Demo (Port 7004)
    ↓ (auto-discovers)
connector-aws
connector-http
connector-postgres-v2
connector-slack
connector-smtp
connector-example
```

---

## Prerequisites

- Python 3.11+
- Poetry (for dependency management)
- Docker & Docker Compose
- Running M8flow instance

---

## Step 1: Initial Setup

### 1.1 Navigate to connector-proxy-demo

```bash
cd /path/to/m8flow-sonal/connector-proxy-demo
```

### 1.2 Check existing configuration

View current connectors in [`pyproject.toml`](file:///home/sonal-aot/Documents/GitHub/m8flow-sonal/connector-proxy-demo/pyproject.toml):

```toml
[tool.poetry.dependencies]
python = "^3.11"
Flask = "^2.2.2"

spiffworkflow-proxy = {git = "https://github.com/sartography/spiffworkflow-proxy"}

connector-aws = {git = "https://github.com/sartography/connector-aws.git"}
connector-http = {git = "https://github.com/sartography/connector-http.git"}
connector-postgres-v2 = {git = "https://github.com/sartography/connector-postgres.git"}
connector-slack = {git = "https://github.com/sartography/connector-slack.git"}
connector-smtp = {git = "https://github.com/sartography/connector-smtp.git"}
connector-example = {develop = true, path = "./connector-example" }
```

---

## Step 2: Add a New Connector

### 2.1 Add to pyproject.toml

Add the connector Git URL to dependencies:

```toml
connector-your-service = {git = "https://github.com/sartography/connector-your-service.git"}
```

**Example:** Adding PostgreSQL connector:

```toml
connector-postgres-v2 = {git = "https://github.com/sartography/connector-postgres.git"}
```

### 2.2 Add missing dependencies (if needed)

Some connectors may have unlisted dependencies. Check the connector's source code and add them manually:

```toml
# Additional dependencies required by connectors
psycopg2-binary = "^2.9.9"  # Required by postgres connector
```

### 2.3 Regenerate lock file

```bash
poetry lock --no-update
```

This updates `poetry.lock` with new dependencies without upgrading existing ones.

---

## Step 3: Build and Deploy

### 3.1 Stop existing container

```bash
docker compose -f dev.docker-compose.yml down
```

### 3.2 Clean local venv (optional but recommended)

```bash
rm -rf .venv
```

### 3.3 Rebuild and start

```bash
docker compose -f dev.docker-compose.yml up --build -d
```

### 3.4 Check logs

```bash
docker compose -f dev.docker-compose.yml logs -f
```

Expected output:

```
spiffworkflow-connector-1  | * Running on http://0.0.0.0:7004
spiffworkflow-connector-1  | * Debug mode: on
```

---

## Step 4: Verify Connector

### 4.1 Test API endpoint

```bash
curl http://192.168.1.89:7004/v1/commands | python3 -m json.tool
```

Look for your connector in the JSON output:

```json
{
  "id": "postgres_v2/CreateTableV2",
  "parameters": [...]
}
```

### 4.2 Check in M8flow UI

1. Open M8flow in browser: `http://192.168.1.89:8000`
2. Create/edit a BPMN process
3. Add a **Service Task**
4. Click **Operator ID** dropdown
5. Your connector commands should appear in the list

### 4.3 Restart M8flow backend (if connectors don't appear)

```bash
# In main m8flow directory
docker compose -f docker/m8flow-docker-compose.yml restart spiffworkflow-backend
```

---

## Step 5: Configure M8flow Backend

### 5.1 Update .env file

Ensure connector proxy URL is set in [`.env`](file:///home/sonal-aot/Documents/GitHub/m8flow-sonal/.env):

```bash
M8FLOW_BACKEND_CONNECTOR_PROXY_URL=http://192.168.1.89:7004
```

### 5.2 Restart backend to pick up changes

```bash
docker compose -f docker/m8flow-docker-compose.yml restart spiffworkflow-backend
```

---

## Available Connectors

| Connector                 | Repository                                                                          | Purpose                         |
| ------------------------- | ----------------------------------------------------------------------------------- | ------------------------------- |
| **connector-aws**         | [sartography/connector-aws](https://github.com/sartography/connector-aws)           | DynamoDB, S3 operations         |
| **connector-http**        | [sartography/connector-http](https://github.com/sartography/connector-http)         | HTTP requests (GET, POST, etc.) |
| **connector-postgres-v2** | [sartography/connector-postgres](https://github.com/sartography/connector-postgres) | PostgreSQL database operations  |
| **connector-slack**       | [sartography/connector-slack](https://github.com/sartography/connector-slack)       | Slack messaging                 |
| **connector-smtp**        | [sartography/connector-smtp](https://github.com/sartography/connector-smtp)         | Email via SMTP                  |

---

## Troubleshooting

### Container fails to start

**Issue:** `Command not found: flask`

**Solution:** Add PATH to Dockerfile:

```dockerfile
ENV PATH="/app/.venv/bin:$PATH"
```

### Module not found errors

**Issue:** `ModuleNotFoundError: No module named 'psycopg2'`

**Solution:** Add missing dependency to `pyproject.toml` and rebuild.

### Connector not appearing in M8flow

1. Verify connector is running: `curl http://192.168.1.89:7004/v1/commands`
2. Check M8flow backend logs for connection errors
3. Restart M8flow backend to refresh connector list
4. Verify `M8FLOW_BACKEND_CONNECTOR_PROXY_URL` is set correctly

### Poetry lock errors

**Issue:** `pyproject.toml changed significantly since poetry.lock was last generated`

**Solution:**

```bash
poetry lock --no-update
```

---

## Creating Custom Connectors

### Example Structure

See [`connector-example`](file:///home/sonal-aot/Documents/GitHub/m8flow-sonal/connector-proxy-demo/connector-example) for reference:

```
connector-example/
├── src/
│   └── connector_example/
│       ├── __init__.py
│       └── commands/
│           ├── __init__.py
│           └── example.py
├── pyproject.toml
└── README.md
```

### Command Template

```python
from spiffworkflow_connector_command.command_interface import ConnectorCommand
from spiffworkflow_connector_command.command_interface import ConnectorProxyResponseDict

class MyCommand(ConnectorCommand):
    def __init__(self, param1: str, param2: str):
        self.param1 = param1
        self.param2 = param2

    def execute(self, _config, _task_data) -> ConnectorProxyResponseDict:
        # Your logic here
        result = {"output": f"{self.param1} - {self.param2}"}

        return {
            "command_response": {
                "body": result,
                "mimetype": "application/json",
            },
            "error": None,
            "command_response_version": 2,
            "spiff__logs": [],
        }
```

---

## File Locations

- **Connector Proxy:** `/home/sonal-aot/Documents/GitHub/m8flow-sonal/connector-proxy-demo`
- **Dependencies:** `pyproject.toml`
- **Dockerfile:** `dev.Dockerfile`
- **Docker Compose:** `dev.docker-compose.yml`
- **Main App:** `app.py`
- **M8flow Config:** `.env`

---

## Quick Reference Commands

```bash
# Add new connector
poetry add git+https://github.com/sartography/connector-name.git

# Update lock file
poetry lock --no-update

# Rebuild container
docker compose -f dev.docker-compose.yml up --build -d

# View logs
docker compose -f dev.docker-compose.yml logs -f

# Test API
curl http://192.168.1.89:7004/v1/commands

# Restart M8flow backend
docker compose -f docker/m8flow-docker-compose.yml restart spiffworkflow-backend
```
