# Changelog for m8flow

## Unreleased

`Added`

* Global tenant selector for super-admins that scopes process-instance and task lists by the selected tenant.

`Changed`

* Super-admin tenant filtering on the Template Library now also includes PUBLIC templates from other tenants (tenant-owned OR public), mirroring regular tenant scoping. Filtering by a tenant therefore returns that tenant's templates plus all public templates.

## 1.0.0 - 2026-03-31

`Added`

* Initial release with features
    * Multi-tenant Workflow Engine
    * Workflow Template Library
    * Connectors
    * Event-based Workflow Execution

`Known Issues`

* In this release, only Docker deployment is supported.
* Local backend and frontend development are not available.

