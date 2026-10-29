# m8flow-node-wire-proxy

FastAPI connector proxy for **HTTP V2 Service Tasks**, backed by sibling-built **node-wire** wheels (`runtime` + `http_generic`). No `spiffworkflow-proxy`, no Spiff connector packages.

## Status (POC)

- `/liveness` → `{"ok": true}` (compose healthcheck shape)
- `GET /v1/commands` — HTTP V2 catalog (`http/*RequestV2`)
- `POST /v1/do/{connector}/{command}` — maps to `http_generic.request` (HEAD via adapter httpx)

## Setup (local)

```bash
# 1. Stage wheels from sibling node-wire (if not already present)
m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh

# 2. Create a venv and install host + matching platform wheels
cd m8flow-node-wire-proxy
python3 -m venv .venv && source .venv/bin/activate
./bin/install_local_deps

# 3. Run
./bin/run_server_locally
# or: CONNECTOR_PROXY_PORT=6844 M8FLOW_CONNECTOR_PROXY_API_KEY=local-dev-connector-proxy-key ./bin/run_server_locally
curl -fsS http://127.0.0.1:7004/liveness
curl -fsS -H "X-M8FLOW-Connector-Proxy-Key: local-dev-connector-proxy-key" \
  http://127.0.0.1:7004/v1/commands
```

On Windows PowerShell, use:

```powershell
.\m8flow-node-wire-proxy\bin\stage-node-wire-wheels.ps1
```

Env:

| Variable | Default | Purpose |
|---|---|---|
| `M8FLOW_CONNECTOR_PROXY_API_KEY` | _(required)_ | Shared secret; send as `X-M8FLOW-Connector-Proxy-Key` on `/v1/*` |
| `NW_ALLOWED_CONNECTORS` | `http_generic` | node-wire fail-closed allowlist |
| `CONNECTOR_PROXY_PORT` | `7004` (local) / compose uses `6844` | listen port |
| `CONNECTOR_PROXY_HOST` | `127.0.0.1` (local) / `0.0.0.0` (docker) | bind address |
| `NW_ALLOW_UNAUTHENTICATED` | unset | Test-only; allows boot without an API key |

## Docker

Build from the **repo root**. The committed node-wire wheels support `linux/amd64` only. On Apple Silicon, build the amd64 image with emulation:

```bash
# Stage the committed linux_x86_64 wheels first if needed:
m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
docker build --platform linux/amd64 -f m8flow-node-wire-proxy/Dockerfile -t m8flow/m8flow-node-wire-proxy .
```

Compose (`docker/m8flow-docker-compose.yml`) starts **`m8flow-node-wire-proxy`** on `${CONNECTOR_PROXY_PORT:-6844}` by default and points `M8FLOW_BACKEND_CONNECTOR_PROXY_URL` at it.

## Dependencies

- PyPI: FastAPI, uvicorn, `PyJWT[crypto]` (required to import `node_wire_runtime`)
- `httpx` is held to the `0.27.x` series because the committed node-wire `1.1.0` wheel metadata requires `httpx[http2]>=0.27,<0.28`.
- Vendor wheels only for `node-wire-runtime` / `node-wire-http-generic` — see `vendor/wheels/README.md`
- `uv.lock` pins the Python dependency graph and committed Linux x86_64 node-wire wheels. Docker and DevX CI install with `uv sync --frozen`; regenerate the lock when updating `pyproject.toml` or those wheels.
