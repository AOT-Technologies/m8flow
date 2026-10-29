# Vendor wheels (node-wire)

Binary-only wheels for **node-wire-runtime** and **node-wire-http-generic**, staged from the sibling `node-wire` checkout. Not published to PyPI for this POC.

## Stage

From the m8flow repo root:

```bash
m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
# optional rebuild first:
STAGE_REBUILD=1 m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
# override sibling path / version:
NODE_WIRE_ROOT=/path/to/node-wire NODE_WIRE_VERSION=1.1.0 m8flow-node-wire-proxy/bin/stage-node-wire-wheels.sh
```

## Current committed set

All committed wheels are version `1.1.0`, CPython 3.12, `linux_x86_64`:

- `node-wire-runtime`
- `node-wire-http-generic`
- `node-wire-m8flow-github`
- `node-wire-m8flow-n8n`
- `node-wire-m8flow-smtp`
- `node-wire-m8flow-slack`
- `node-wire-m8flow-salesforce`
- `node-wire-m8flow-stripe`
- `node-wire-m8flow-postgres`

- **Local macOS venv:** stage the matching macOS wheels before running `bin/install_local_deps`.
- **Docker on Apple Silicon / linux/arm64:** native ARM64 builds are unsupported because this repository does not contain the complete `linux_aarch64` wheel set. Build the image with `--platform linux/amd64`.
- **linux/amd64 images:** use the committed `linux_x86_64` wheels and frozen `uv.lock`.

## Install (local smoke)

```bash
python3 -m venv .venv && source .venv/bin/activate
bin/install_local_deps
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
