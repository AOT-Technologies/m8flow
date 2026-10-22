# Quality and compliance gates

The automated checks that guard m8flow's code, dependencies, and licensing:
what each one checks, where it runs, and what makes it fail. To run the
licensing, secret, static analysis (SAST), and vulnerability checks locally, run
`./bin/compliance/run-compliance-checks.sh` from the repository root.

## Gates on every pull request

The following checks run on every pull request:

| Gate | Workflow | Checks | Fails on |
|---|---|---|---|
| Component CI | `<component>-cicd.yaml` (DevX) | Build, unit tests, and image build; Ruff lint for the backend | Any lint error, failed test, or failed build |
| SAST | `<component>-cicd.yaml` (DevX) | Semgrep on every pull request; SonarQube on pushes and releases | Reported in the run summary; doesn't block yet |
| Image and SBOM scans | `<component>-cicd.yaml` (DevX) | Trivy vulnerability and secret scan of the image; scan of the CycloneDX software bill of materials (SBOM) | Reported in the run summary; doesn't block yet |
| Test matrix | `test-matrix.yml` | Backend tests on Python 3.12 (Linux, macOS); designer ESLint, tests, and build on Node.js 20.19, 22, and 24 (Linux) and 24 (macOS) | Any failure on a supported row |
| CodeQL | `codeql.yml` | `security-and-quality` queries for Python and TypeScript | New alerts appear under **Security → Code scanning** |
| Bandit | `compliance.yml` | Python SAST on shipped source | Any high-severity finding |
| Dependency vulnerabilities | `compliance.yml` | `pip-audit` on each Python service's runtime dependencies; `npm audit` on the designer's | Any known vulnerability (Python); a high or critical one (npm) |
| Dependency licenses | `compliance.yml` | The license of every runtime dependency, written to `DEPENDENCIES.md` | A GPL or AGPL runtime dependency |
| REUSE | `compliance.yml` | Every file declares a copyright and license, through `REUSE.toml` or a header | A file without one |
| Secrets | `secret-scan.yml` | Gitleaks on the pull request's commits; full history on pushes and weekly | A finding not allowlisted in `.gitleaks.toml` or triaged in `.gitleaksignore` |
| Migrations | `check-migrations.yml` | Every Alembic migration compiles, and destructive operations are flagged | A migration that doesn't compile, or more than one head |

Rows of the test matrix marked experimental, such as Python 3.13 and Windows,
report results but don't fail the run.

## Scheduled scans

The following scans also run on a schedule:

| Scan | Schedule | Why |
|---|---|---|
| CodeQL | Weekly | New queries run against unchanged code |
| Gitleaks | Weekly, full history | New rules run against old commits |
| Compliance | Daily | New advisories against unchanged lockfiles |
| Dependabot | Weekly | Update pull requests for Python, npm, Maven, Docker, and GitHub Actions dependencies |

## Licensing

m8flow is licensed under Apache-2.0, recorded in [`LICENSE`](../../LICENSE)
and [`NOTICE`](../../NOTICE). [`REUSE.toml`](../../REUSE.toml) declares the
copyright and license of every file by path, and
[`LICENSES/`](../../LICENSES/) holds each license's text, so the repository
is [REUSE](https://reuse.software/) compliant without a header in every file.
To add an explicit SPDX header to a file, run
`bin/compliance/add-license-headers.sh <file>...`.

Third-party files in the repository, such as fonts, get their own annotation
in `REUSE.toml`. A file whose license is unconfirmed or doesn't allow
redistribution is marked `LicenseRef-NeedsReview` or with a `LicenseRef-`
naming its commercial license, and the REUSE job warns about it until it's
resolved.

[`DEPENDENCIES.md`](../../DEPENDENCIES.md) lists every runtime dependency of
the backend, the MCP server, the NATS consumer, the node-wire proxy, the
designer, and `m8flow-bpmn`, with its license and one of the following
classifications:

| Classification | Licenses | Meaning |
|---|---|---|
| Safe | MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0, and similar | Compatible with Apache-2.0 |
| Needs review | LGPL, custom, guessed, or unknown | A maintainer confirms the obligations are met |
| Risky | GPL, AGPL | Not allowed in a runtime dependency; CI fails |

To regenerate it after a dependency change, run the following commands from
the repository root:

```bash
(cd m8flow-bpmn && npm ci --ignore-scripts)
(cd m8flow-designer && npm ci --ignore-scripts)
python3 bin/compliance/dependency_licenses.py --write --check
```

## Secret scanning

Gitleaks scans with its default rules plus [`.gitleaks.toml`](../../.gitleaks.toml).
Reviewed values that aren't live credentials, such as the local-development
defaults in `sample.env`, the Keycloak realm exports, and test fixtures, are
allowlisted in `.gitleaks.toml` by exact value, grouped by why each is safe.
Matching the value rather than the commit keeps them allowed when a commit is
rebased, squashed, or edited, and any other value in the same file still
fails the scan. [`.gitleaksignore`](../../.gitleaksignore) is for one-off
findings, by fingerprint.

If the scan flags a real secret, remove it, rotate it with whoever issued it,
and treat it as exposed even after the commit is gone. If it flags a false
positive, add its exact value to `.gitleaks.toml` as an anchored regex, under
the group that says why it's safe. For a finding that isn't a reusable value,
add its fingerprint from the scan output to `.gitleaksignore` with a comment
instead.

The `sample.env` file and the realm exports hold well-known local-development
credentials. Every deployment must replace them; see
[Values to replace before deploying](configuration.md#values-to-replace-before-deploying).

## Release integrity

Final releases are tagged `X.Y.Z` with a signed tag that the release workflow
verifies. The GitHub Release carries CycloneDX SBOMs, `SHA256SUMS`, a keyless
Sigstore signature of the checksums, and a build-provenance attestation for
every asset. [Release and roll back m8flow](../how-to/release-and-roll-back.md#verify-a-release)
shows how to verify them.

## Related pages

- [Develop and test m8flow](../how-to/develop-and-test.md)
- [Release and roll back m8flow](../how-to/release-and-roll-back.md)
- [Contributing guide](../../CONTRIBUTING.md)
