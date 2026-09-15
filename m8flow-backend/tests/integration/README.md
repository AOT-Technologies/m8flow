# Integration tests

This directory is reserved for opt-in live-integration smoke tests.

There is currently **no** live-Keycloak suite checked in. Earlier tests that
imported `spiffworkflow_backend` were removed with the wheel-based host cutover.

Unit coverage for auth, tenants, and Keycloak Admin API helpers lives under
`tests/unit/`. Follow-up: add an opt-in live-Keycloak smoke test against the
`AuthProvider` seam when a stable local Keycloak profile is documented.
