# Release and roll back m8flow

Cut a release candidate, promote it to a general availability (GA) release
with a signed tag and a GitHub Release, and recover when a release goes wrong. This page is for
maintainers with write access to the repository.

The [workflows README](../../.github/workflows/README.md) describes the CI and
deployment pipelines these steps run on, and the
[versioning policy](../reference/versioning.md) defines what each version
number promises.

## Prerequisites

- Write access to `AOT-Technologies/m8flow`.
- For a final release, a GPG or SSH signing key that's
  [registered on your GitHub account](https://docs.github.com/en/authentication/managing-commit-signature-verification/adding-a-gpg-key-to-your-github-account),
  and git configured to sign tags with it.
- [uv](https://docs.astral.sh/uv/) and Python 3.12, to run the release scripts.

## Cut a release candidate

A release candidate (`X.Y.Z-rc`) publishes images for testing. It doesn't get
a GitHub Release. To cut one, follow these steps:

1. In GitHub, open **Actions** → **Release** → **Run workflow**, on `main`.
2. Leave **channel** as `rc`. Leave **tag_name** empty to increment the patch
   of the latest candidate, or set it, for example `2.1.0-rc`.
3. Run it. The workflow creates the tag and pushes every selected component's
   image to the registry at that tag.

Deploy the candidate to a test environment with each component's workflow,
and test it before you promote it.

## Cut a final release

A final release is tagged `X.Y.Z` (no `v` prefix), signed by you, and has a
GitHub Release with notes, software bills of materials (SBOMs), checksums, and
signatures.

### Prepare the release

To prepare the release, follow these steps:

1. Check that `main` is green: the component CI, **Compliance**,
   **Secret scan**, **CodeQL**, and **Test matrix** workflows.
2. Close or move every open issue in the release's milestone.
3. On a branch, set every component to the release version:

   ```bash
   python3 bin/release/set-version.py <version>
   ```

   Replace `<version>` with the release, for example `2.1.0`.

4. In `CHANGELOG.md`, rename `## [Unreleased]` to
   `## [<version>] - <yyyy-mm-dd>`, add a new empty `## [Unreleased]` before
   it, and add the link reference at the end of the file. Replace
   `<yyyy-mm-dd>` with the release date:

   ```markdown
   [<version>]: https://github.com/AOT-Technologies/m8flow/releases/tag/<version>
   ```

5. Open a pull request with these changes and get it reviewed. The release
   notes come from this changelog section, so the review approves them.

### Tag and publish

To tag and publish the release, follow these steps:

1. After the pull request merges, create a signed tag at the tip of `main`
   and push it:

   ```bash
   git checkout main
   git pull
   git tag -s <version> -m "m8flow <version>"
   git push origin <version>
   ```

2. Open **Actions** → **Release** → **Run workflow** on `main`, with
   **channel** `ga` and **tag_name** `<version>`. The workflow refuses a tag
   that's unsigned, signed with a key GitHub can't verify, or not at the tip
   of `main`. It then builds and pushes every component's image at that tag.
3. Open **Actions** → **GitHub Release** → **Run workflow**, with **version**
   `<version>`. It checks that the component versions match the tag, then
   creates a **draft** release with these assets:

   | Asset | Contents |
   |---|---|
   | `m8flow-<version>-source.tar.gz` | The source at the tag |
   | `m8flow-<version>-backend.cdx.json` | CycloneDX SBOM of the backend's runtime dependencies |
   | `m8flow-<version>-designer.cdx.json` | CycloneDX SBOM of the designer's runtime dependencies |
   | `m8flow-<version>-DEPENDENCIES.md` | The license of every runtime dependency |
   | `SHA256SUMS` | SHA-256 checksums of the preceding assets |
   | `SHA256SUMS.sigstore.json` | Keyless Sigstore signature of `SHA256SUMS` |

   Every asset also gets a build-provenance attestation.

4. Open the draft on the [releases page](https://github.com/AOT-Technologies/m8flow/releases),
   review it, check **Set as the latest release**, and publish it.
5. Deploy the release with each component's workflow, as described in the
   [workflows README](../../.github/workflows/README.md#deploying).

### Verify a release

Anyone can check that a release's assets came from this repository's workflow.

To verify the checksums and their signature, download the assets and run the
following commands:

```bash
cosign verify-blob SHA256SUMS \
    --bundle SHA256SUMS.sigstore.json \
    --certificate-identity-regexp '^https://github.com/AOT-Technologies/m8flow/\.github/workflows/github-release\.yml@' \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com
sha256sum -c SHA256SUMS
```

To verify an asset's build provenance, run the following command:

```bash
gh attestation verify m8flow-<version>-source.tar.gz --repo AOT-Technologies/m8flow
```

## Roll back

### Roll back a deployment

A component's deploy workflow checks the service's health after it rolls out
the new image, and rolls the workload back to the previous image if the check
fails.

To roll back by hand, run the component's workflow again with the
`image_uri` of the previous release. If the release ran database migrations,
restore the database backup taken before the upgrade first; an older backend
doesn't run against a newer schema. [Upgrade m8flow](upgrade.md#roll-back)
covers backups.

### Withdraw a bad release

Published tags and images are never moved or overwritten, because users may
already depend on them. To withdraw a bad release, follow these steps:

1. Fix the problem on `main`, and cut the next patch release (`X.Y.Z+1`)
   with the steps in [Cut a final release](#cut-a-final-release).
2. Edit the bad release on the releases page: check **Set as a pre-release**
   and add a warning at the top of the notes that names the fixed version.
3. Add a note under the bad version in `CHANGELOG.md`.
4. If the problem is a security vulnerability, publish a
   [security advisory](https://github.com/AOT-Technologies/m8flow/security/advisories)
   that names the affected and fixed versions, as described in
   [SECURITY.md](../../SECURITY.md).

Delete a tag or release only for a legal problem or when it exposed a
secret. In that case, also rotate the secret: deleting the release doesn't
remove copies others have downloaded.

## Related pages

- [Versioning and deprecation policy](../reference/versioning.md)
- [Upgrade m8flow](upgrade.md)
- [Quality and compliance gates](../reference/quality-and-compliance.md)
