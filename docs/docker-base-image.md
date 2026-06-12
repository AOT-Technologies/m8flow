# Docker base image: `m8flow-python-base`

A reusable, prebuilt Ubuntu/Python image that m8flow's backend-related service images
build on top of, so the common OS toolchain and Python tooling are installed **once** in
the base instead of being reinstalled from raw Ubuntu on every service build.

- **Image:** `docker.io/m8flow/m8flow-python-base`
- **Primary tag:** `ubuntu24.04-py3.12`
- **Dockerfile:** [docker/m8flow.python-base.Dockerfile](../docker/m8flow.python-base.Dockerfile)
- **Build workflow:** [.github/workflows/build-base-image.yml](../.github/workflows/build-base-image.yml)
- **Consumed by:** [docker/m8flow.backend.Dockerfile](../docker/m8flow.backend.Dockerfile) (the `builder`, `prod`, and `dev` stages, via the `PYTHON_BASE` build arg). The backend image is in turn reused by the Celery worker, flower, and (optionally) the NATS consumer in Compose.

## Purpose

Before this base existed, the backend Dockerfile installed the identical apt + `uv`
toolchain in both its `builder` and `dev` stages, and a runtime subset again in `prod`.
Every PR dry-run and every deploy rebuilt all of it from `ubuntu:24.04`. The base image
collapses that into a single cached layer pulled from the registry, cutting build time and
removing the duplication.

## Included dependencies

OS/toolchain **only** — see "Dependency ownership" below.

| Dependency | Why |
|------------|-----|
| `build-essential`, `python3-dev`, `pkg-config` | Compile native Python wheels |
| `libpq-dev` | psycopg2 build (pulls in the `libpq5` runtime lib) |
| `default-libmysqlclient-dev` | mysqlclient build (pulls in the `libmariadb3` runtime lib) |
| `gosu` | Entrypoint drops from root to the `app` user |
| `git`, `curl`, `ca-certificates`, `openssl` | Fetch dependencies over TLS; git SSL is preconfigured |
| `python3`, `python3-venv`, `python-is-python3` | Python 3.12 runtime + `venv` |
| `uv` (pinned via `UV_VERSION`, default `0.7.2`) | Dependency/venv manager, installed from the official binary |

## Tag naming convention

`ubuntu<os-version>-py<python-version>` — currently **`ubuntu24.04-py3.12`**.

- The build workflow also pushes a build-numbered tag (`ubuntu24.04-py3.12-<run_number>`) so a
  specific build is reproducible/debuggable.
- **Do not rely on a moving `latest` tag.** Consumers and CI reference the explicit
  versioned tag. When the OS or Python version changes, introduce a new tag (e.g.
  `ubuntu26.04-py3.13`) rather than mutating the existing one.

## Rebuild process

The base is rebuilt and pushed by `build-base-image.yml`, which triggers on:

1. **Dockerfile change** — any push to `main` touching `docker/m8flow.python-base.Dockerfile`
   (or the workflow itself).
2. **Manual** — `workflow_dispatch` from the Actions tab (use when bumping `UV_VERSION` or
   forcing a security refresh).
3. **Weekly schedule** — `cron: 0 6 * * 1` (Mon 06:00 UTC) to pick up Ubuntu security updates.

Build it locally (tag it as the published name so backend builds resolve it):

```bash
docker build -f docker/m8flow.python-base.Dockerfile \
  -t docker.io/m8flow/m8flow-python-base:ubuntu24.04-py3.12 .
```

To build the backend against a different/local base, override the arg:

```bash
docker buildx build --file docker/m8flow.backend.Dockerfile --target dev \
  --build-arg PYTHON_BASE=docker.io/m8flow/m8flow-python-base:ubuntu24.04-py3.12 \
  --tag backend:dev --load .
```

Compose reads the same default and honors a `PYTHON_BASE` environment override.

## Security update expectations

- The base **must be rebuilt regularly** to receive Ubuntu security patches — that is what
  the weekly cron is for. After a base rebuild, rebuild/redeploy the backend so it inherits
  the patched layer.
- Keep the base **lean**: only OS/toolchain dependencies belong here. Adding application
  dependencies bloats every consumer and blurs ownership.

## Dependency ownership

- **OS / toolchain dependencies** → the base image (`m8flow.python-base.Dockerfile`).
- **Application (Python) dependencies** → the service image (the backend Dockerfile's
  `uv pip install` steps), driven by the project's lock/pyproject files.

> Note: because the `prod` and `dev` stages both build from this single base, the base
> carries the full build toolchain. The `dev` stage still purges build-essential and
> CVE-prone packages from its *final* image; the production image accepts the toolchain as a
> deliberate tradeoff for a uniform, fast-building base.
