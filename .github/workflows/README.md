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
| Push or merge to `main` | The same CI, then the image is published as `docker.io/m8flow/<image>:sha-<commit>`. |
| Push to `refactor/next-gen` | The same CI. Nothing is published. |
| `release.yaml` (manual) | Channel `rc`: tags a `main` commit `X.Y.Z-rc` and adds that tag to each component's existing `sha-<commit>` image. Channel `ga`: adds the release tag `X.Y.Z` to the tested candidate's images (`rc_tag`), tags the candidate's commit `X.Y.Z` in git, and drafts the GitHub Release. It publishes; it does not deploy. |
| `github-release.yml` (called by `release.yaml`, or manual to redo one) | Creates the draft GitHub Release for an `X.Y.Z` tag, with notes from `main`'s `CHANGELOG.md`, SBOMs, checksums, a Sigstore signature, and provenance attestations. |
| A component's caller, run manually | Deploys any published image (`sha-<commit>`, `X.Y.Z-rc` or `X.Y.Z`) to an environment (dev, qa or demo). |

## Releasing

Actions → **Release** → Run workflow, on `main`. Any other branch is refused,
because the Docker Hub OIDC connection trusts `main` only.
[Release and roll back m8flow](../../docs/how-to/release-and-roll-back.md)
describes the release flow, the workflow's inputs, and the full procedure.

### The release workflows are test-bound

`.github/scripts/test_release_workflow.py` runs the real `run:` scripts out of
`release.yaml` and `github-release.yml`, so it reaches into them by job name
and step name. Renaming a job or a step it names, or turning one of those
`run: |` blocks into a folded scalar or a single-line `run:`, fails the suite
with a message naming what it looked for. Move a value into the step's `env`
rather than interpolating `${{ }}` inside a script it covers. The steps under
contract are `branch/Release channel`, `plan/Resolve commit`,
`plan/Resolve sources`, `plan/Check the registry` and `summary/Report` in
`release.yaml`, and `build/Validate version` and
`build/Verify the tag marks a candidate` in `github-release.yml`.

One message goes to Google Chat with every component's result, and each
component's build sends its own.

## Deploying

Actions → the component's workflow → Run workflow, with `environment` and a
published `image_uri`: a `main` build such as
`docker.io/m8flow/m8flow-backend:sha-<commit>`, a candidate such as `:2.0.8-rc`,
or a release such as `:2.0.0`.

Before the deploy touches the cluster, `verify-image.yml` checks that
`image_uri` is this component's image, with a tag or a digest, and that it
exists on Docker Hub. If either check fails, the deploy doesn't run.

The deploy patches the running workload's image (the backend's also patches
the celery worker, flower, NATS consumer and notification worker), then checks it
(`<host>` is `dev.m8flow.ai`, `staging.m8flow.ai` for qa, or `demo.m8flow.ai`):

| Component | Health check after the deploy |
|---|---|
| Backend | `GET https://<host>/api/v1.0/readyz` |
| Designer | `GET https://<host>/` |
| Keycloak | `GET https://<host>/realms/m8flow/.well-known/openid-configuration` (5 minute window) |
| Node-wire proxy, MCP server | rollout status |

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
and missing or invalid reports fail the Snyk job. Eligible scans also fail if
the required `SNYK_TOKEN` secret is missing. Scans from fork pull requests are
skipped because GitHub withholds secrets from forks. Configure the secret at
the repository or organization level before relying on these scans. CI image
findings are also reported by the preceding Trivy and Grype scans.

`.github/workflows/trivy-security-scans.yaml` is a separate, secret-free scan of all five first-party
application images. It uses a fixed matrix, so every triggered run scans all five images rather than
selecting components from the changed paths. Push and pull request runs are gated by explicit paths
for Docker build files, root-level build inputs, and the source directories copied into these images;
unrelated changes do not trigger it. Weekly and manual runs always scan the full matrix. Each job
builds the image from the checked-out commit, scans OS and library vulnerabilities, uploads JSON and
SARIF reports as a 30-day workflow artifact, and uploads SARIF to Code Scanning on push, scheduled,
and manual runs. Pull requests still get the JSON/SARIF artifacts, but skip SARIF upload because
their token may be read-only. The backend image also contains the NATS consumer and notification
worker; the retired connector proxy is not a separate image to scan. Findings are report-only; build
or scanner errors fail the job.

## Notifications

Google Chat notifications are enabled for component CI, releases, and pull
request activity targeting `develop` or `main`. Configure the
`GOOGLE_CHAT_WEBHOOK` repository secret; pull request notifications also accept
the legacy `PR_NOTIFICATION` secret as a fallback. The standalone pull request
notifier warns and skips if neither secret is available. DevX component CI and
release notification jobs fail their workflow when `GOOGLE_CHAT_WEBHOOK` is
missing. The exception is a fork-originated pull request: GitHub withholds its
secrets, so DevX warns and skips that notification.

## Secrets and access

| Name | Kind | Used for |
|---|---|---|
| `SONAR_TOKEN` | secret | SonarQube (skipped when absent) |
| `SNYK_TOKEN` | secret | Snyk Container scans for all app and Compose images |
| `GOOGLE_CHAT_WEBHOOK` | secret | Google Chat notifications for component CI and releases; PR notifications also accept `PR_NOTIFICATION` |

Docker Hub and AWS access are GitHub OIDC, no stored keys. `main` builds, releases and the base
image push to Docker Hub through the `m8flow` organization's OIDC connection
(`docker.oidc_connection_id` in each `devx-ci.yaml`; it trusts this repository
on `main`). `m8flow-<env>-cicd-deploy-role` deploys to `m8flow-eks`. Images went to ECR (us-east-2) until 2026-10; the
images released there stay until they are deleted.

## Other workflows

| Workflow | Purpose |
|---|---|
| `check-migrations.yml` | On every PR and push (about 15 seconds, so it can be a required check): every migration can be read and compiles, and the revision chain has one head (fails the run); destructive operations in a changed migration's `upgrade()` are flagged as warnings on the file and line. The checker's tests (`.github/scripts/test_check_migrations.py`) run first. |
| `verify-image.yml` | Called by each component's caller before a deploy: refuses an `image_uri` that is another component's image or isn't on Docker Hub. |
| `build-base-image.yml` | Rebuilds the Python base image the backend builds on (weekly and on change). |
| `codex-pr-review.yml` | Automated pull request review. |
| `compliance.yml` | On every PR and push, and daily: REUSE lint, Bandit (fails on high), `pip-audit` and `npm audit`, and the dependency license check that regenerates `DEPENDENCIES.md` (fails on GPL or AGPL runtime dependencies). |
| `secret-scan.yml` | Gitleaks on the PR's commits, and on the full history for pushes and weekly. Reviewed values are allowlisted by exact value in `.gitleaks.toml`; one-off findings are listed by fingerprint in `.gitleaksignore`. |
| `codeql.yml` | CodeQL for Python and TypeScript on every PR and push, and weekly. |
| `.github/workflows/trivy-security-scans.yaml` | Builds and scans the fixed matrix of all five first-party images when path filters match a PR or push, weekly, or manually; uploads reports on every run and submits SARIF to Code Scanning on push, weekly, and manual runs. |
| `test-matrix.yml` | Backend tests on Python 3.12 (Linux, macOS) and designer lint, tests, and build on Node.js 20.19, 22, and 24, with experimental Python 3.13 and Windows rows. |
| `pr-notification.yml` | Pull request activity to Google Chat. |

## Known gaps

- The node-wire proxy uses Semgrep only until its SonarCloud project
  (`AOT-Technologies_m8flow-node-wire-proxy`) exists.

## Upgrading DevX

Point every `uses:` line at the new release's commit SHA with the version as a
trailing comment, and read its CHANGELOG entry for any config changes.
