# Security policy

The m8flow maintainers take the security of the project seriously. This
document explains which versions receive security fixes and how to report a
vulnerability responsibly.

## Supported versions

m8flow follows [Semantic Versioning](https://semver.org/). Security fixes go to
the latest minor release of the current major version and to the `main`
branch. See the [versioning policy](docs/reference/versioning.md) for what a
version covers.

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report suspected vulnerabilities privately through either of the following:

- **GitHub Security Advisories**: use the
  [private vulnerability reporting](https://github.com/AOT-Technologies/m8flow/security/advisories/new)
  form for this repository (preferred).
- **Email**: send details to **opensource@aot-technologies.com**.

Include as much of the following as you can:

- A description of the vulnerability and its potential impact.
- The component involved (for example, `m8flow-backend`, `m8flow-designer`,
  the Keycloak extensions, a connector proxy, the NATS consumer, or the MCP
  server).
- Whether it crosses a tenant boundary or bypasses a role check. Tenant
  isolation and role-based access are core guarantees, so say so explicitly.
- Steps to reproduce, including a minimal proof of concept if available.
- The version, commit, image tag, or deployment configuration affected.

## What to expect

- **Acknowledgement** within 3 business days of your report.
- An initial assessment and severity triage within 10 business days.
- Coordinated disclosure: we work with you on a fix and a public disclosure
  timeline, and credit you in the advisory unless you prefer to remain
  anonymous.

Give us a reasonable opportunity to fix the issue before any public
disclosure.

## Scope

This policy covers the code in this repository and the container images built
from it. Report vulnerabilities in third-party dependencies, such as Keycloak,
PostgreSQL, or a Python or npm package, to the upstream project. If a
dependency issue affects m8flow users, we still welcome a heads-up so we can
pin or patch accordingly.

The `sample.env` file and the Keycloak realm exports contain well-known
local-development credentials. They are not secrets, and every deployment
must replace them. Reports that only show these defaults work against a local
stack are out of scope; reports of a code path that silently accepts them in a
production configuration are in scope.
