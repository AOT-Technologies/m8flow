# Workflows

CI, releases and deployments run on the DevX reusable workflows
([AOT-Technologies/devx-reusable-workflows](https://github.com/AOT-Technologies/devx-reusable-workflows)),
pinned to a release commit (`v1.3.0`). DevX holds the pipeline logic; this
repository holds one small caller per component and that component's
configuration.

## Components

| Component | Caller | CI config | CD config | Image (ECR, us-east-2) |
|---|---|---|---|---|
| Backend (also celery worker, flower, NATS consumer and notification worker) | `backend-cicd.yaml` | `m8flow-backend/devx-ci.yaml` | `m8flow-backend/devx-config.yaml` | `m8flow-backend` |
| Designer (primary UI) | `designer-cicd.yaml` | `m8flow-designer/devx-ci.yaml` | `m8flow-designer/devx-config.yaml` | `m8flow-designer` |
| Keycloak | `keycloak-cicd.yaml` | `keycloak-extensions/devx-ci.yaml` | `keycloak-extensions/devx-config.yaml` | `m8flow-keycloak` |
| Connector proxy (the old Spiff proxy) | `connector-proxy-cicd.yaml` | `m8flow-connector-proxy/devx-ci.yaml` | `m8flow-connector-proxy/devx-config.yaml` | `m8flow-connector-proxy` |
| Node-wire proxy (next-gen's default connector proxy) | `node-wire-proxy-cicd.yaml` | `m8flow-node-wire-proxy/devx-ci.yaml` | `m8flow-node-wire-proxy/devx-config.yaml` | `m8flow-node-wire-proxy` |
| MCP server | `mcp-server-cicd.yaml` | `m8flow-mcp/devx-ci.yaml` | `m8flow-mcp/devx-config.yaml` | `m8flow-mcp` |

Registry: `653405621825.dkr.ecr.us-east-2.amazonaws.com`.

## What runs when

| Event | What happens |
|---|---|
| Pull request to `main` or `refactor/next-gen` | CI for each component whose files changed: build, tests, SAST, image build, image and SBOM scans. Nothing is published. |
| Push or merge to `main` or `refactor/next-gen` | The same CI. Nothing is published. |
| `release.yaml` (manual) | Creates the next `X.Y.Z-rc` tag and builds and pushes the selected components at that tag. It publishes; it does not deploy. |
| A component's caller, run manually | Deploys a released image to an environment (dev today). |

## Releasing

Actions → **Release** → Run workflow, on `main` (or `refactor/next-gen` until it
merges into main; any other branch is refused). It tags the branch it runs on:

- `tag_name`: leave empty to increment the patch of the latest tag, or set
  one (`2.0.0-rc` for the first release).
- `components`: `all`, or a single component.
- `dry_run`: resolves the tag only.

One message goes to Google Chat with every component's result, and each
component's build sends its own.

## Deploying

Actions → the component's workflow → Run workflow, with `environment` and the
released `image_uri`, e.g.
`653405621825.dkr.ecr.us-east-2.amazonaws.com/m8flow-backend:2.0.0-rc`.

The deploy patches the running workload's image (the backend's also patches
the celery worker, flower, NATS consumer and notification worker), then checks it:

| Component | Health check after the deploy |
|---|---|
| Backend | `GET https://sandbox.m8flow.ai/api/v1.0/readyz` |
| Designer | `GET https://sandbox.m8flow.ai/` |
| Keycloak | `GET https://sandbox.m8flow.ai/realms/m8flow/.well-known/openid-configuration` (5 minute window) |
| Connector proxy, node-wire proxy, MCP server | rollout status |

If the rollout or the health check fails, the workload is rolled back to the
image it ran before the deploy, and the result message says so. `dry_run`
validates against the cluster and changes nothing.

The Deployments themselves come from the Helm charts in `m8flow-charts`; CD
only changes their image.

## Security scans

Every CI run reports, per component, Trivy (image), Semgrep (source) and Grype
(SBOM) findings by severity in the run summary, with the critical and high
findings listed, and attaches the full reports as artifacts. Code scanning
only lists alerts for the default branch, so the run summary is where to read
them.

The gate is `security.gate.fail_on` in each `devx-ci.yaml`. It is `none` for
now: everything is reported, nothing blocks, so the current findings can be
fixed first. `critical,high` makes new critical or high findings fail the
build.

Snyk Container scans all six M8Flow application images (`m8flow-backend`,
`m8flow-designer`, `m8flow-keycloak`, `m8flow-node-wire-proxy`,
`m8flow-connector-proxy`, and `m8flow-mcp`) plus every distinct third-party
image referenced by the Docker Compose stacks. The scan matrix
includes PostgreSQL, Redis, MinIO and MinIO Client, NATS, Nginx, Alpine,
Rclone, Loki, Tempo, Prometheus, Grafana Alloy, cAdvisor, Grafana, and the
PostgreSQL exporter. It also scans every literal external image used in
Dockerfile stages, including Ubuntu, Python, Node, Temurin, Keycloak, and the
shared Python base. CI scans locally built app-image artifacts; release scans
the published app images; the third-party image matrix pulls each configured
public image reference. Each scan uploads a JSON report artifact with the result and
scanned image metadata (tag, image ID, and registry digest when available).
Findings are report-only; scanner/setup failures or a missing/invalid report
fail the scan. If `SNYK_TOKEN` is absent, the scan is explicitly skipped.
Fork pull requests skip Snyk because GitHub does not provide the secret to
them; pushes in the repository are scanned.

The current all-branch push triggers are temporary for baseline testing and
should be narrowed after the initial inventory. Google Chat notifications are
also temporarily disabled during this testing.

## Notifications

Google Chat notifications are temporarily disabled during the Snyk baseline
testing. Re-enable them after configuring the required webhook secret.

## Secrets and access

| Name | Kind | Used for |
|---|---|---|
| `GOOGLE_CHAT_WEBHOOK` | secret | notifications |
| `SONAR_TOKEN` | secret | SonarQube (skipped when absent) |
| `SNYK_TOKEN` | secret | Snyk Container scans for all app and Compose images |

AWS access is GitHub OIDC, no stored keys: `GitHubActions-ECS-m8flow` pushes
to ECR, and `m8flow-<env>-cicd-deploy-role` deploys to `m8flow-eks`.

## Other workflows

| Workflow | Purpose |
|---|---|
| `check-migrations.yml` | On every PR and push (about 15 seconds, so it can be a required check): every migration can be read and compiles, and the revision chain has one head (fails the run); destructive operations in a changed migration's `upgrade()` are flagged as warnings on the file and line. The checker's tests (`.github/scripts/test_check_migrations.py`) run first. |
| `build-base-image.yml` | Rebuilds the Python base image the backend builds on (weekly and on change). |
| `codex-pr-review.yml` | Automated pull request review. |
| `pr-notification.yml` | Pull request activity to Google Chat. |

## Known gaps

- The node-wire proxy uses Semgrep only until its SonarCloud project
  (`AOT-Technologies_m8flow-node-wire-proxy`) exists.

## Upgrading DevX

Point every `uses:` line at the new release's commit SHA with the version as a
trailing comment, and read its CHANGELOG entry for any config changes.
