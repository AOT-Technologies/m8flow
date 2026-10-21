# m8flow documentation

This folder holds the m8flow documentation: how to run m8flow, how to use the
designer, how the platform works, and the exact values you look up while
building with it. For what m8flow is and what it can do, start with the
[project README](../README.md).

## Start here

Pick the path that matches what you came to do.

| You are… | Start with | Then read |
|---|---|---|
| New to m8flow | [Quick start](tutorials/quick-start.md) | [Product tour](tour.md) |
| Designing processes | [Product tour](tour.md) | [About process execution](explanation/process-execution.md) · [BPMN support](reference/bpmn-support.md) |
| Administering a tenant | [Manage tenants and members](how-to/manage-tenants-and-members.md) | [Roles and permissions](reference/roles-and-permissions.md) · [About multi-tenancy and access control](explanation/multi-tenancy-and-access.md) |
| Connecting other systems | [Call an external service from a process](how-to/call-external-services.md) | [Trigger processes from external systems](how-to/trigger-processes-with-api-keys.md) · [HTTP API](reference/http-api.md) |
| Connecting an AI assistant | [Set up the MCP server and the MCP Tools page](how-to/set-up-mcp-tools.md) | [Configuration](reference/configuration.md#mcp-server) |
| Running m8flow for others | [Services and ports](reference/services-and-ports.md) | [Configuration](reference/configuration.md) · [Upgrade m8flow](how-to/upgrade.md) · [Troubleshoot m8flow](how-to/troubleshoot.md) |
| Contributing code | [Contributing guide](../CONTRIBUTING.md) | [Run the backend and designer from source](how-to/run-from-source.md) · [Develop and test m8flow](how-to/develop-and-test.md) · [About the m8flow architecture](explanation/architecture.md) |
| Releasing m8flow | [Release and roll back m8flow](how-to/release-and-roll-back.md) | [Versioning and deprecation policy](reference/versioning.md) · [Quality and compliance gates](reference/quality-and-compliance.md) |

## All pages

The pages follow the [Diátaxis](https://diataxis.fr/) framework. Each page is
one kind of document, so you know what to expect when you open it.

### Tutorials

Lessons that take you from nothing to a working result. The
[quick start](tutorials/quick-start.md) starts the stack, then builds,
publishes, and runs your first process.

### Tours

[A tour of the m8flow designer](tour.md) walks through every area of the
designer, with screenshots and recordings.

### How-to guides

Steps for one task, for readers who already know the basics.

- [Run the backend and designer from source](how-to/run-from-source.md)
- [Develop and test m8flow](how-to/develop-and-test.md)
- [Manage tenants and members](how-to/manage-tenants-and-members.md)
- [Call an external service from a process](how-to/call-external-services.md)
- [Trigger processes from external systems](how-to/trigger-processes-with-api-keys.md)
- [Set up the MCP server and the MCP Tools page](how-to/set-up-mcp-tools.md)
- [Enable logs, metrics, and traces](how-to/enable-observability.md)
- [Upgrade m8flow](how-to/upgrade.md)
- [Troubleshoot m8flow](how-to/troubleshoot.md)
- [Release and roll back m8flow](how-to/release-and-roll-back.md)

### Explanation

Background on how m8flow works and why it's built that way.

- [About the m8flow architecture](explanation/architecture.md): the
  components, the host modules, and the path of a request.
- [About multi-tenancy and access control](explanation/multi-tenancy-and-access.md):
  realms, tenants, sign-in, row-level security, and roles.
- [About process execution](explanation/process-execution.md): model status,
  templates, human tasks, timers, and service tasks.

### Reference

Exact values to look up.

- [Services and ports](reference/services-and-ports.md)
- [Configuration](reference/configuration.md)
- [Roles and permissions](reference/roles-and-permissions.md)
- [BPMN support](reference/bpmn-support.md)
- [HTTP API](reference/http-api.md)
- [Repository layout](reference/repository-layout.md)
- [Versioning and deprecation policy](reference/versioning.md)
- [Quality and compliance gates](reference/quality-and-compliance.md)

### Auth provider

A deeper guide to the identity layer, for teams that run m8flow with an
identity provider other than the built-in Keycloak setup.

- [Auth provider overview](auth-provider/README.md)
- [How the auth provider works](auth-provider/how-it-works.md)
- [Identity provider prerequisites](auth-provider/prerequisites.md)
- [JWT token shape](auth-provider/jwt-token-shape.md)
- [Write an auth provider](auth-provider/writing-a-provider.md)

## Terminology

The pages use one vocabulary for the product: process model, process
instance, catalog, active tenant, secret sentinel, and so on. The glossary in
[`CONTEXT.md`](../CONTEXT.md) defines each term and the words to avoid.

## Change these docs

Keep each page to one Diátaxis type, write headings in sentence case, and
address the reader as "you". Put images in [`images/`](images/).

The diagrams, screenshots, and recordings are generated, not drawn by hand.
Their sources live in the documentation skills, not in this repository:
`doc-media` builds the diagrams and terminal recordings, and `doc-screenshots`
captures the screenshots and browser recordings. Each skill's
`projects/m8flow/README.md` explains how to rebuild the m8flow figures. Don't
edit the images in `images/` by hand.

To report a mistake in the docs, open an issue in the
[issue tracker](https://github.com/AOT-Technologies/m8flow/issues).
