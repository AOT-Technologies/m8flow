# Contributing to m8flow

Thanks for your interest in contributing. This guide covers how to set up a
development environment, the checks a pull request must pass, and the
conventions for submitting changes. By contributing, you agree that your
contributions are licensed under the project's [Apache License 2.0](LICENSE).

Read the [Code of Conduct](CODE_OF_CONDUCT.md) before you take part.

## Prerequisites

You need the following tools:

| Tool | Version | Notes |
|---|---|---|
| Git | Any recent version | |
| Docker with Compose v2 | Compose v2 | Runs PostgreSQL, Keycloak, Redis, and the other services |
| Python | 3.12 or 3.13 | Backend, connector proxies, NATS consumer, and MCP server |
| [uv](https://docs.astral.sh/uv/) | Latest | Installs Python dependencies from the committed lockfiles |
| Node.js and npm | 20.19 or later (22 LTS or 24 LTS recommended) | `m8flow-designer` and `m8flow-bpmn` |

## Development setup

Clone the repository and create your local settings:

```bash
git clone https://github.com/AOT-Technologies/m8flow.git
cd m8flow
cp sample.env .env
```

[Run the backend and designer from source](docs/how-to/run-from-source.md)
starts the infrastructure in Docker and the backend and designer on your
machine with hot reload.

## Checks

CI runs the following checks on pull requests to `main`. Run the ones that
match your change before you open a pull request. [Develop and test
m8flow](docs/how-to/develop-and-test.md) explains each one.

| Area | Command |
|---|---|
| Backend lint | `cd m8flow-backend && uvx ruff@0.12.1 check . --config ruff.toml` |
| Backend tests | `cd m8flow-backend && uv sync --group dev && uv run pytest -n auto` |
| Designer lint | `cd m8flow-designer && npm run lint` |
| Designer tests | `cd m8flow-designer && npm test` |
| Designer build | `cd m8flow-designer && npm run build` |
| Licensing, secrets, and SAST | `./bin/compliance/run-compliance-checks.sh` |

[Quality and compliance gates](docs/reference/quality-and-compliance.md) lists
every automated gate and what makes it fail.

## Rules for changes

Reviews check the rules in [Develop and test
m8flow](docs/how-to/develop-and-test.md#rules-for-changes). The most important
ones:

- Keep tenant isolation and permission checks intact. Don't add queries that
  skip the tenant binding.
- After a change to sign-in, tokens, tenant selection, or permissions, test
  with a non-admin user such as `editor` or `reviewer`, not only with an admin.
- Make database migrations reversible where you can, and keep existing data.
- Don't add a dependency unless you need it, and explain why in the pull
  request. New dependencies must have a license that's compatible with
  Apache-2.0; see [Licensing](#licensing).
- Add an entry under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for any
  change a user or operator would notice.

## Licensing

m8flow is licensed under Apache-2.0 and is [REUSE](https://reuse.software/)
compliant. [`REUSE.toml`](REUSE.toml) declares the copyright and license of
every file by path, so a new file in an existing folder needs no header. If
you want an explicit SPDX header in a file, add it with
`bin/compliance/add-license-headers.sh <file>...`.

When you add a file you didn't write, such as a font, an icon set, a copied
stylesheet, or a vendored library, add an annotation for it to `REUSE.toml`
with its real copyright holder and license, and put the license text in
[`LICENSES/`](LICENSES/). Don't commit anything whose license doesn't allow
redistribution in an open-source project, such as commercial fonts or icon
packs.

## Git identity

Configure your git identity before you commit. Commits must use your real name
and a valid email so attribution is accurate:

```bash
git config user.name "<your-name>"
git config user.email "<your-email>"
```

Replace the following:

- `<your-name>`: your real full name.
- `<your-email>`: the email address tied to your GitHub account.

## Submitting changes

To submit a change, follow these steps:

1. Fork the repository and create a branch from `main`, for example
   `feature/short-description` or `fix/short-description`.
2. Make your change, with tests and documentation updates where relevant.
3. Run the [checks](#checks) that match your change.
4. Open a pull request against `main` with a clear description of the change
   and why you made it. Link any related issue.
5. A maintainer reviews your pull request. Address feedback by pushing more
   commits to your branch.

## Reporting bugs and requesting features

Use the [GitHub issue templates](https://github.com/AOT-Technologies/m8flow/issues/new/choose).
For **security vulnerabilities**, don't open a public issue. Follow the
[security policy](SECURITY.md) instead.
