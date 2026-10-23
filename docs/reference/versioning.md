# Versioning and deprecation policy

m8flow follows [Semantic Versioning 2.0.0](https://semver.org/). This page
defines what a version number promises, which parts of m8flow those promises
cover, and how features are deprecated and removed.

## Version numbers

A release version is `MAJOR.MINOR.PATCH`:

- **MAJOR** changes the public surface in a way existing users must act on.
- **MINOR** adds backward-compatible features, such as a new endpoint, a new
  connector, or a new optional setting.
- **PATCH** fixes bugs without changing the public surface.

Within a major version, m8flow makes no breaking changes to the public
surface. Breaking changes wait for the next major version, and the
[changelog](../../CHANGELOG.md) lists each one under **Breaking** with the
steps to take.

## Tags and images

Every release is a git tag on `main`, and every container image is published
with the same tag:

| Tag | Meaning |
|---|---|
| `X.Y.Z` | A final release. The tag is signed by the maintainer who cut it, and it has a GitHub Release with notes, SBOMs, checksums, and signatures. |
| `X.Y.Z-rc` | A release candidate for testing. It has images but no GitHub Release, and carries no compatibility promise. |

Tags have no `v` prefix. [Release and roll back m8flow](../how-to/release-and-roll-back.md)
describes how releases are cut.

## The public surface

The compatibility promise covers the following:

| Surface | Where it's defined |
|---|---|
| HTTP API under `/v1.0/` and `/v1.0/m8flow/`: paths, methods, request and response fields, and status codes | [`api.yml`](../../m8flow-backend/src/m8flow_backend/api.yml) and the [HTTP API reference](http-api.md) |
| Configuration: documented environment variables, their defaults, and their meaning | [Configuration](configuration.md) and [`sample.env`](../../sample.env) |
| Process models: the BPMN and DMN elements m8flow runs, its BPMN extension attributes, and the `M8FLOW_SECRET:<key>` reference syntax | [BPMN support](bpmn-support.md) |
| Roles and permissions: the seven role names and what each allows | [Roles and permissions](roles-and-permissions.md) |
| Event triggers: the trigger endpoint, the API key format, and the event payload | [Trigger processes from external systems](../how-to/trigger-processes-with-api-keys.md) |
| MCP server: tool names and their arguments | [Set up the MCP server and the MCP Tools page](../how-to/set-up-mcp-tools.md) |
| Auth provider interface for other identity providers | [Write an auth provider](../auth-provider/writing-a-provider.md) |
| Stored data: an upgrade within a major version keeps your process models, instances, tasks, tenants, and secrets | [Upgrade m8flow](../how-to/upgrade.md) |

## Not covered

The following can change in any release. If you depend on one of them, pin
an exact version:

- Python modules, classes, and functions inside `m8flow-backend` and the other
  services. m8flow is an application, not a library.
- Designer components, routes, and styling, including the Storybook component
  library.
- The database schema. Alembic migrations move it forward on upgrade; don't
  read or write m8flow tables directly.
- Docker Compose service names, volume names, and the default host ports.
- Log message text, metric and trace attribute names, and Grafana dashboards.
- Endpoints, settings, or features marked **experimental** in the docs or the
  API spec.
- Release candidates (`X.Y.Z-rc`).

## Deprecation

A public feature is removed only in a major version. Before that:

1. The feature is marked **deprecated** in a minor release, in the changelog
   and in its documentation. Deprecated HTTP operations are marked
   `deprecated: true` in `api.yml`.
2. The deprecated feature keeps working for the rest of that major version.
3. The major release that removes it lists the removal under **Breaking** in
   the changelog, with what to use instead.

## Supported versions

Security fixes and bug fixes go to the latest minor release of the current
major version. [SECURITY.md](../../SECURITY.md) has the support table and the
process for reporting a vulnerability.

## Related pages

- [Release and roll back m8flow](../how-to/release-and-roll-back.md)
- [Upgrade m8flow](../how-to/upgrade.md)
- [Changelog](../../CHANGELOG.md)
