# Governance

m8flow is an open-source project stewarded by **AOT Technologies**. This
document describes the roles in the project, how decisions are made, and how
releases are cut.

## Roles

- **Maintainers** review and merge contributions, triage issues, cut releases,
  and set technical direction. The maintainers are the AOT Technologies team
  members with write access to this repository.
- **Contributors** are anyone who opens issues or pull requests under the
  [contributing guide](CONTRIBUTING.md).

## Decision making

- Routine changes are approved by maintainer review on a pull request. A pull
  request needs at least one maintainer approval.
- Significant or breaking changes are discussed in an issue before
  implementation and need maintainer consensus. Changes that affect tenant
  isolation, authentication, or role-based access always count as
  significant. As project steward, AOT Technologies makes the final decision
  where maintainers can't reach consensus.
- Changes to the public surface follow the
  [versioning and deprecation policy](docs/reference/versioning.md).

## Releases

Maintainers cut releases through the automated release workflow, following
[Release and roll back m8flow](docs/how-to/release-and-roll-back.md). Every
release is recorded in [CHANGELOG.md](CHANGELOG.md) and on the
[releases page](https://github.com/AOT-Technologies/m8flow/releases).

## Security

Vulnerability reports follow the private process in [SECURITY.md](SECURITY.md).
Maintainers coordinate fixes and disclosure there, not in public issues.

## Becoming a maintainer

Sustained, high-quality contributions may lead to an invitation to become a
maintainer, at the discretion of the existing maintainers.

## Code of conduct

All participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
