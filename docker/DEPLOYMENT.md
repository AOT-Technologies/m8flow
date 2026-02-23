# Deploying M8Flow images to Docker Hub

This document describes how to build and push the **backend**, **frontend**, and **Keycloak** images to Docker Hub for use by ECS or other deployments (e.g. `m8flow-deployment` with `use_docker_hub = true`).

---

## Prerequisites

- **Docker** (with Buildx if you use `--platform linux/amd64` on non-amd64 hosts).
- **Docker Hub account** and a namespace (e.g. your username or org like `m8flow`).
- **Login** to Docker Hub:
  ```bash
  docker login
  ```
- Run all commands from the **repository root** (parent of `docker/`), e.g.:
  ```bash
  cd /path/to/vinaayakh-m8flow
  ```

---

## Variables

Set these before building and pushing. They should match the Terraform variables used in deployment (`docker_hub_namespace`, `docker_image_tag`).

```bash
# Your Docker Hub namespace (e.g. m8flow or your username)
export DOCKER_NAMESPACE="m8flow"

# Image tag (e.g. latest, 1.0.0, or a git/sprint tag)
export TAG="latest"
```

---

## 1. Backend

Ensure the image is built from the repo that includes the m8flow-backend extension (tenancy, Keycloak realm APIs, and support for `SPIFFWORKFLOW_BACKEND_WSGI_PATH_PREFIX` and `M8FLOW_KEYCLOAK_ADMIN_PASSWORD`). ECS expects the API under `/api/v1.0/*`.

The backend uses the Keycloak **superadmin** user by default (username `superadmin`, created by the Keycloak image entrypoint). Set `KEYCLOAK_ADMIN_PASSWORD` or `M8FLOW_KEYCLOAK_ADMIN_PASSWORD` to the superadmin password (same as `KEYCLOAK_SUPERADMIN_PASSWORD` when using the Keycloak image entrypoint) so the backend can create realms and run partial import.

Build the production backend image (target `prod`, `linux/amd64` for ECS):

```bash
docker build \
  --platform linux/amd64 \
  -f docker/m8flow.backend.Dockerfile \
  --target prod \
  -t "${DOCKER_NAMESPACE}/m8flow-backend:${TAG}" \
  .
```

Push:

```bash
docker push "${DOCKER_NAMESPACE}/m8flow-backend:${TAG}"
```

---

## 2. Frontend

The frontend image bakes in build-time env (e.g. from `.env`: `MULTI_TENANT_ON`, `VITE_BACKEND_BASE_URL`). Ensure `.env` exists in the repo root with the values you want for this build.

Build:

```bash
docker build \
  --platform linux/amd64 \
  -f docker/m8flow.frontend.Dockerfile \
  -t "${DOCKER_NAMESPACE}/m8flow-frontend:${TAG}" \
  .
```

Push:

```bash
docker push "${DOCKER_NAMESPACE}/m8flow-frontend:${TAG}"
```

---

## 3. Keycloak

Build the Keycloak image (realm-info-mapper provider and realm imports):

```bash
docker build \
  --platform linux/amd64 \
  -f docker/m8flow.keycloak.Dockerfile \
  -t "${DOCKER_NAMESPACE}/m8flow-keycloak:${TAG}" \
  .
```

Push:

```bash
docker push "${DOCKER_NAMESPACE}/m8flow-keycloak:${TAG}"
```

---

## All-in-one: build and push

From the repo root, with `DOCKER_NAMESPACE` and `TAG` set:

```bash
# Backend
docker build --platform linux/amd64 -f docker/m8flow.backend.Dockerfile --target prod -t "${DOCKER_NAMESPACE}/m8flow-backend:${TAG}" .
docker push "${DOCKER_NAMESPACE}/m8flow-backend:${TAG}"

# Frontend (ensure .env is present for build-time vars)
docker build --platform linux/amd64 -f docker/m8flow.frontend.Dockerfile -t "${DOCKER_NAMESPACE}/m8flow-frontend:${TAG}" .
docker push "${DOCKER_NAMESPACE}/m8flow-frontend:${TAG}"

# Keycloak
docker build --platform linux/amd64 -f docker/m8flow.keycloak.Dockerfile -t "${DOCKER_NAMESPACE}/m8flow-keycloak:${TAG}" .
docker push "${DOCKER_NAMESPACE}/m8flow-keycloak:${TAG}"
```

---

## Image names used by deployment

When `use_docker_hub = true`, Terraform/ECS expects:

| Service   | Image pattern                          |
|----------|----------------------------------------|
| Backend  | `{docker_hub_namespace}/m8flow-backend:{docker_image_tag}`   |
| Frontend | `{docker_hub_namespace}/m8flow-frontend:{docker_image_tag}`  |
| Keycloak | `{docker_hub_namespace}/m8flow-keycloak:{docker_image_tag}`   |

Use the same `DOCKER_NAMESPACE` and `TAG` (or equivalent) in Terraform (e.g. `terraform.tfvars`) when deploying.

---

## Optional: build without platform

If you are on `linux/amd64` and do not need a specific platform, you can omit `--platform linux/amd64` from the `docker build` commands above.
