# m8flow MCP Server

A **Model Context Protocol (MCP)** server that exposes **m8flow** workflow capabilities to AI
assistants such as **Claude Desktop**, **Cursor**, and other MCP-compatible clients.

The server runs in one of **two transport modes**, selected by the `SERVER_TYPE` environment
variable:

- **`remote`** — HTTP transport (`streamable-http`) for Cursor and other HTTP clients, with
  browser-based **OIDC** login via Keycloak.
- **`stdio`** — stdio transport for Claude Desktop, authenticated with a bearer token or
  Keycloak username/password (ROPC).

The same entry point (`python -m src.main`) serves both modes — you do not run a different
script per mode.

---

## Architecture

```text
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│   MCP Client     │──────▶│    m8flow-mcp    │──────▶│   m8flow Backend │
│ (Claude/Cursor)  │  MCP  │ (FastMCP+uvicorn)│ HTTP  │      API         │
└──────────────────┘       └──────────────────┘       └──────────────────┘
                                    │
                                    ▼
                              Keycloak Authentication
```

---

## Quick Start

```bash
cd m8flow-mcp

# 1. Install dependencies
uv venv
uv sync

# 2. Create your environment file
cp sample.env .env        # Windows: copy sample.env .env
# then edit .env (auth, backend URL, Keycloak) — see Configuration below

# 3. Run the server (mode is chosen by SERVER_TYPE in .env; default is stdio)
uv run python -m src.main
```

Prefer `make`? The [Makefile](Makefile) wraps the common commands:

```bash
make run        # stdio mode
make run-http   # HTTP mode (sets SERVER_TYPE=remote)
make docker-run # docker compose up -d
```

---

## Prerequisites

- Python 3.12 or newer
- Running **m8flow backend**
- Running **Keycloak**
- A configured Keycloak client for MCP authentication
- **uv** package manager (`pip install uv`)

---

## Configuration

Copy the sample environment file and edit it:

```bash
cp sample.env .env         # Windows: copy sample.env .env
```

### Environment Variables

| Variable | Default | Description |
|-----------|----------|-------------|
| SERVER_TYPE | stdio | `stdio` (Claude Desktop) or `remote` (Cursor / HTTP) |
| HOST | 0.0.0.0 | MCP server host (remote mode) |
| PORT | 8000 | MCP server port (remote mode) |
| M8FLOW_API_URL | http://localhost:6840 | m8flow backend base URL |
| M8FLOW_API_TIMEOUT | 30 | Backend API timeout (seconds) |
| KEYCLOAK_URL | http://localhost:6842 | Keycloak base URL |
| KEYCLOAK_REALM | m8flow | Keycloak realm |
| CLIENT_ID | m8flow-backend | Keycloak client used by the MCP server |
| CLIENT_SECRET | | Client secret (required for browser/OIDC login) |
| M8FLOW_BEARER_TOKEN | | Static bearer token |
| KEYCLOAK_USERNAME | | Username for ROPC authentication |
| KEYCLOAK_PASSWORD | | Password for ROPC authentication |
| OIDC_CONFIG_URL | | OpenID configuration endpoint (defaults to the realm's well-known URL) |
| REQUIRED_SCOPES | openid,profile,email | Required OAuth scopes |
| VERIFY_ID_TOKEN | true | Validate the ID token instead of the access token |
| MCP_OIDC_BASE_URL | | Public base URL of this MCP server (remote mode) |
| MCP_OIDC_ISSUER_URL | | Public issuer URL (defaults to base URL) |
| MCP_OIDC_REDIRECT_PATH | /oauth/callback | OAuth callback path |
| MCP_OIDC_REQUIRE_CONSENT | false | Require the OAuth consent screen |
| ALLOW_SECRET_VALUE_READ | false | Allow the `get_secret_value` tool to reveal decrypted secrets |
| LOG_LEVEL | INFO | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| LOG_FORMAT | json | `json` or `text` |

---

## Authentication

Authentication is resolved in the following order.

### 1. Browser Login (remote mode)

Used by Cursor. Requires:

- `CLIENT_SECRET`
- `MCP_OIDC_BASE_URL`
- `MCP_OIDC_ISSUER_URL`

The user authenticates through Keycloak in the browser.

### 2. Static Bearer Token

```env
M8FLOW_BEARER_TOKEN=<ACCESS_TOKEN>
```

Ideal for Claude Desktop (stdio mode).

### 3. Username / Password (ROPC)

```env
KEYCLOAK_USERNAME=<USERNAME>
KEYCLOAK_PASSWORD=<PASSWORD>
```

The server automatically obtains and refreshes access tokens. Requires **Direct Access
Grants** to be enabled on the Keycloak client.

---

## Running the Server

The transport mode is controlled entirely by `SERVER_TYPE` in your `.env` — the command is the
same for both modes.

### Cursor (HTTP / OIDC)

Set `SERVER_TYPE=remote` in `.env`, then:

```bash
uv run python -m src.main        # or: make run-http
```

Available endpoints:

| Endpoint | Description |
|-----------|-------------|
| GET /health | Health check |
| /mcp | MCP streamable-HTTP endpoint |

### Claude Desktop (stdio)

Set `SERVER_TYPE=stdio` in `.env` (the default), then:

```bash
uv run python -m src.main        # or: make run
```

stdio mode supports bearer-token and ROPC authentication (browser login does not apply).

---

## Getting a Keycloak Access Token

```bash
curl -X POST \
  "http://localhost:6842/realms/m8flow/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=m8flow-backend" \
  -d "grant_type=password" \
  -d "username=<USERNAME>" \
  -d "password=<PASSWORD>"
```

Copy the returned `access_token` into your `.env`:

```env
M8FLOW_BEARER_TOKEN=<ACCESS_TOKEN>
```

---

## MCP Client Configuration

### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "m8flow": {
      "url": "http://localhost:8000/mcp",
      "transport": "streamable-http"
    }
  }
}
```

### Claude Desktop

Point the command at this project directory; `uv` runs the server without a pre-activated
virtualenv:

```json
{
  "mcpServers": {
    "m8flow": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/m8flow-mcp", "run", "python", "-m", "src.main"],
      "env": {
        "M8FLOW_BEARER_TOKEN": "<ACCESS_TOKEN>"
      }
    }
  }
}
```

---

## Running with Docker

```bash
docker compose up -d --build
curl http://localhost:8000/health
```

The bundled [docker-compose.yml](docker-compose.yml) runs the server in `remote` (HTTP) mode
and reads secrets from your `.env`.

---

## Cursor Authentication Troubleshooting

If Cursor reports **"Authorization with the MCP server failed"**, check the following.

1. **Base URLs** — `MCP_OIDC_BASE_URL` and `MCP_OIDC_ISSUER_URL` must match the URL configured
   in Cursor exactly.
2. **Redirect URI** — register `${MCP_OIDC_BASE_URL}/oauth/callback` as a valid redirect URI in
   Keycloak.
3. **Keycloak client** — Standard Flow enabled, confidential client, correct client secret.
4. **OpenID discovery** — `OIDC_CONFIG_URL` must be reachable by the MCP server.
5. **Token validation** — if tokens are rejected for missing scopes, keep `VERIFY_ID_TOKEN=true`.

> In Docker, `localhost` refers to the container, not your host. Use
> `http://host.docker.internal:6842` (or the Keycloak service name) so the container can reach
> Keycloak.

---

## Available Tools

Tools are grouped by module under [src/mcp_tools/](src/mcp_tools/) and registered through
`register_tools()`. The main groups are:

| Group | Examples |
|-------|----------|
| Process groups | `list_process_groups`, `create_process_group`, `get_process_group` |
| Process models | `list_process_models`, `create_process_model`, `create_process_model_from_template` |
| Process instances | `start_process_instance`, `get_process_instance`, `cancel_process_instance` |
| Tasks | `list_tasks`, `get_task`, `claim_task`, `complete_task` |
| Templates | `list_templates`, `get_template`, `create_template` |
| BPMN files | `get_bpmn_file`, `upload_bpmn_file`, `update_bpmn_file` |
| Connectors | `list_connectors`, `get_connector`, `get_connector_operation` |
| Secrets | `list_secrets`, `create_secret`, `get_secret`, `get_secret_value` |
| Error management | `list_process_errors`, `get_error_details`, `diagnose_workflow` |
| Counts | `count_process_models`, `count_process_instances`, `count_tasks` |
| Visualization | `view_workflow`, `view_process_instance` |
| Documentation | `tools_documentation` |

Use the `tools_documentation` tool from any client to get the authoritative, up-to-date list.

---

## Adding New Tools

1. Create a module under [src/mcp_tools/](src/mcp_tools/) (e.g. `my_tools.py`) that exposes a
   `register_*_tools(mcp)` function. Define each tool with the FastMCP `@mcp.tool` decorator:

   ```python
   from __future__ import annotations

   from typing import TYPE_CHECKING

   from src.api_client import M8flowAPIClient
   from src.utils.context import get_auth_token

   if TYPE_CHECKING:
       from fastmcp import FastMCP

   client = M8flowAPIClient()


   def register_my_tools(mcp: "FastMCP") -> None:
       @mcp.tool(name="list_projects", description="List projects")
       async def list_projects() -> str:
           token = get_auth_token()
           return await client.get("/v1.0/projects", token)
   ```

2. Import and call your `register_my_tools(mcp)` from
   [src/mcp_tools/__init__.py](src/mcp_tools/__init__.py) inside `register_tools()`.

3. Restart the server.

---

## Error Responses

| Status | Meaning |
|---------|---------|
| 401 | Invalid, expired, or missing token |
| 403 | User lacks required permissions |
| 404 | Resource not found |
| 502 | Backend API unavailable |
| 504 | Backend API timeout |

---

## Project Structure

```text
m8flow-mcp/
├── src/
│   ├── main.py              # Entry point (python -m src.main)
│   ├── api_client.py        # m8flow backend HTTP client
│   ├── config/              # Settings (pydantic-settings)
│   ├── auth/                # Keycloak / JWT / token services
│   ├── client/              # Shared HTTP client
│   ├── errors/              # Exception types
│   ├── middleware/          # Context, tenant, observability middleware
│   ├── mcp_tools/           # MCP tool modules + register_tools()
│   └── utils/               # Logging, request context
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── uv.lock
├── sample.env
└── README.md
```
