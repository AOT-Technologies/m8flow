# Workflows

CI, releases and deployments run on the DevX reusable workflows
([AOT-Technologies/devx-reusable-workflows](https://github.com/AOT-Technologies/devx-reusable-workflows)),
pinned to a release commit (`v1.4.0`). DevX holds the pipeline logic; this
repository holds one small caller per component and that component's
configuration.

## Components

| Component | Caller | CI config | CD config | Image (Docker Hub) |
|---|---|---|---|---|
| Backend (also celery worker, flower, NATS consumer and notification worker) | `backend-cicd.yaml` | `m8flow-backend/devx-ci.yaml` | `m8flow-backend/devx-config.yaml` | `m8flow/m8flow-backend` |
| Designer (primary UI) | `designer-cicd.yaml` | `m8flow-designer/devx-ci.yaml` | `m8flow-designer/devx-config.yaml` | `m8flow/m8flow-designer` |
| Keycloak | `keycloak-cicd.yaml` | `keycloak-extensions/devx-ci.yaml` | `keycloak-extensions/devx-config.yaml` | `m8flow/m8flow-keycloak` |
| Node-wire proxy (next-gen's default connector proxy) | `node-wire-proxy-cicd.yaml` | `m8flow-node-wire-proxy/devx-ci.yaml` | `m8flow-node-wire-proxy/devx-config.yaml` | `m8flow/m8flow-node-wire-proxy` |
| MCP server | `mcp-server-cicd.yaml` | `m8flow-mcp/devx-ci.yaml` | `m8flow-mcp/devx-config.yaml` | `m8flow/m8flow-mcp` |

Registry: Docker Hub, public repositories under `m8flow/` (`docker.io/m8flow/<image>`).

## What runs when

| Event | What happens |
|---|---|
| Pull request to `main` or `refactor/next-gen` | CI for each component whose files changed: build, tests, SAST, image build, image and SBOM scans. Nothing is published. |
| Push or merge to `main` or `refactor/next-gen` | The same CI. Nothing is published. |
| `release.yaml` (manual) | Channel `rc`: creates the next `X.Y.Z-rc` tag. Channel `ga`: verifies the maintainer-signed `X.Y.Z` tag. Either way it builds and pushes the selected components at that tag. It publishes; it does not deploy. |
| `github-release.yml` (manual, GA only) | Creates the draft GitHub Release for a signed `X.Y.Z` tag, with notes from `CHANGELOG.md`, SBOMs, checksums, a Sigstore signature, and provenance attestations. |
| A component's caller, run manually | Deploys a released image to an environment (dev today). |

## Releasing

Actions → **Release** → Run workflow, on `main` (any other branch is refused:
the Docker Hub OIDC connection trusts `main` only). It tags `main`:

- `tag_name`: leave empty to increment the patch of the latest tag, or set
  one (`2.0.0-rc` for the first release).
- `components`: `all`, or a single component.
- `dry_run`: resolves the tag only and creates or builds nothing. Channel `rc`
  computes the next `-rc` tag; channel `ga` runs the full signed-tag check, so
  a GA dry run is a pre-flight for the tag you pushed.

A final (GA) release uses channel `ga` with a tag you signed and pushed, then
the **GitHub Release** workflow. [Release and roll back
m8flow](../../docs/how-to/release-and-roll-back.md) has the full procedure.

One message goes to Google Chat with every component's result, and each
component's build sends its own.

## Deploying

Actions → the component's workflow → Run workflow, with `environment` and the
released `image_uri`, e.g.
`docker.io/m8flow/m8flow-backend:2.0.1-rc`.

The deploy patches the running workload's image (the backend's also patches
the celery worker, flower, NATS consumer and notification worker), then checks it:

| Component | Health check after the deploy |
|---|---|
| Backend | `GET https://dev.m8flow.ai/api/v1.0/readyz` |
| Designer | `GET https://dev.m8flow.ai/` |
| Keycloak | `GET https://dev.m8flow.ai/realms/m8flow/.well-known/openid-configuration` (5 minute window) |
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

Snyk Container scans third-party and supplementary images from the Compose
stacks and Dockerfiles. It scans the published M8Flow application images
(`m8flow-backend`, `m8flow-designer`, `m8flow-keycloak`,
`m8flow-node-wire-proxy`, and `m8flow-mcp`) after a GitHub release or on manual
dispatch from Docker Hub. A manual run can select one application image or all
five and is independent of component CI; its run summary and per-image JSON
artifacts are managed in that Snyk workflow run. Select `all` to also run the
third-party and supplementary image matrix in the same run; selecting one app
scans only that application image. The connector proxy is retired. The third-party
baseline includes PostgreSQL, Redis, MinIO and MinIO Client, NATS, Nginx,
Alpine, Rclone, Loki, Tempo, Prometheus, Grafana Alloy, cAdvisor, Grafana, and
the PostgreSQL exporter. Supplementary scans cover Dockerfile-only/base images
(Ubuntu, Python, Node, Temurin, Keycloak, and the shared Python base).

Compose and supplementary Snyk scans run when relevant Dockerfiles or Compose
files change and on release. Manual dispatch scans only the selected published
M8Flow application image(s), or the complete image set when `all` is selected.
Each scan uploads a JSON report with the scan result and
image metadata. Vulnerability findings are report-only; scanner/setup failures
and missing or invalid reports fail the Snyk job. `SNYK_TOKEN` is required for
a scan; without it, Snyk is skipped. CI image findings are also reported by
the Trivy and Grype scans above.

## Notifications

Google Chat notifications are enabled for component CI, releases, and pull
request activity targeting `develop` or `main`. Configure the
`GOOGLE_CHAT_WEBHOOK` repository secret; pull request notifications also accept
the legacy `PR_NOTIFICATION` secret as a fallback. If no webhook secret is
configured, pull request notifications are skipped.

## Secrets and access

| Name | Kind | Used for |
|---|---|---|
| `SONAR_TOKEN` | secret | SonarQube (skipped when absent) |
| `SNYK_TOKEN` | secret | Snyk Container scans for all app and Compose images |
| `GOOGLE_CHAT_WEBHOOK` | secret | Google Chat notifications for component CI and releases; PR notifications also accept `PR_NOTIFICATION` |

Docker Hub and AWS access are GitHub OIDC, no stored keys. Releases and the base
image push to Docker Hub through the `m8flow` organization's OIDC connection
(`docker.oidc_connection_id` in each `devx-ci.yaml`; it trusts this repository
on `main`). `m8flow-<env>-cicd-deploy-role` deploys to `m8flow-eks`. Images went to ECR (us-east-2) until 2026-10; the
images released there stay until they are deleted.

## Other workflows

| Workflow | Purpose |
|---|---|
| `check-migrations.yml` | On every PR and push (about 15 seconds, so it can be a required check): every migration can be read and compiles, and the revision chain has one head (fails the run); destructive operations in a changed migration's `upgrade()` are flagged as warnings on the file and line. The checker's tests (`.github/scripts/test_check_migrations.py`) run first. |
| `build-base-image.yml` | Rebuilds the Python base image the backend builds on (weekly and on change). |
| `codex-pr-review.yml` | Automated pull request review. |
| `compliance.yml` | On every PR and push, and daily: REUSE lint, Bandit (fails on high), `pip-audit` and `npm audit`, and the dependency license check that regenerates `DEPENDENCIES.md` (fails on GPL or AGPL runtime dependencies). |
| `secret-scan.yml` | Gitleaks on the PR's commits, and on the full history for pushes and weekly. Reviewed values are allowlisted by exact value in `.gitleaks.toml`; one-off findings are listed by fingerprint in `.gitleaksignore`. |
| `codeql.yml` | CodeQL for Python and TypeScript on every PR and push, and weekly. |
| `test-matrix.yml` | Backend tests on Python 3.12 (Linux, macOS) and designer lint, tests, and build on Node.js 20.19, 22, and 24, with experimental Python 3.13 and Windows rows. |
| `pr-notification.yml` | Pull request activity to Google Chat. |

## Known gaps

- The node-wire proxy uses Semgrep only until its SonarCloud project
  (`AOT-Technologies_m8flow-node-wire-proxy`) exists.

## Upgrading DevX

Point every `uses:` line at the new release's commit SHA with the version as a
trailing comment, and read its CHANGELOG entry for any config changes.
