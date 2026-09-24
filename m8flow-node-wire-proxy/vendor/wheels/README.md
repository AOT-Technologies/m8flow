# Vendor wheels (node-wire)

Binary-only wheels for **node-wire-runtime** and **node-wire-http-generic**, staged from the sibling `node-wire` checkout. Not published to PyPI for this POC.

## Stage

From the m8flow repo root:

```bash
m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
# optional rebuild first:
STAGE_REBUILD=1 m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
# override sibling path / version:
NODE_WIRE_ROOT=/path/to/node-wire NODE_WIRE_VERSION=1.0.0 m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
```

## Current staged set (this machine)

| Package | Version | Platform tags produced here |
|---|---|---|
| `node-wire-runtime` | `1.0.0` | `cp312-cp312-macosx_10_9_universal2`, `cp312-cp312-linux_aarch64` |
| `node-wire-http-generic` | `1.0.0` | same |

- **Local macOS venv:** install the `macosx_*` wheels.
- **Docker on Apple Silicon / linux/arm64:** install the `linux_aarch64` wheels (`python:3.12-slim` matching host arch).
- **linux/amd64 images:** not produced on this arm64 host — rebuild on amd64 or use node-wire `scripts/build-packages.sh --all` / CI. See map fog.

## Install (local smoke)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install 'PyJWT[crypto]>=2.8.0' \
  vendor/wheels/node_wire_runtime-1.0.0-cp312-cp312-macosx_10_9_universal2.whl \
  vendor/wheels/node_wire_http_generic-1.0.0-cp312-cp312-macosx_10_9_universal2.whl
NW_ALLOWED_CONNECTORS=http_generic python -c "import node_wire_runtime, node_wire_http_generic; print('ok')"
```

**Host deps note:** the runtime wheel imports `jwt` but does not declare `PyJWT` in its package metadata. The FastAPI host must depend on `PyJWT[crypto]>=2.8.0` (and pulls `httpx` via http_generic).

## Build notes

Sibling command:

```bash
cd ../node-wire   # or /Users/aot/Development/AOT/node-wire
./scripts/build-packages.sh packages/runtime packages/connectors/http_generic
```

If the **Linux** runtime build fails with `Cython.Compiler.Errors.CompileError: …/base_connector.py` under Cython 3.3, rebuild that package in Docker with `"cython>=3.0,<3.2"` (host macOS wheels still build with the default script). The stage script’s `STAGE_REBUILD=1` path includes this fallback.
