# Integration tests

## Keycloak tenant user login (`test_keycloak_tenant_user_login.py`)

This test runs only when Keycloak is configured and reachable. It is skipped automatically if not.

**To run the test:**

1. Start Keycloak (e.g. from repo root: `extensions/m8flow-backend/keycloak/start_keycloak.sh`).
2. Set environment variables:
   - `KEYCLOAK_ADMIN_PASSWORD` (or `M8FLOW_KEYCLOAK_ADMIN_PASSWORD`)
   - `M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_P12` — path to `extensions/m8flow-backend/keystore.p12`
   - `M8FLOW_KEYCLOAK_SPOKE_KEYSTORE_PASSWORD`
3. Run from repo root with PYTHONPATH including `extensions/m8flow-backend/src`, or run from the extension directory.

If any requirement is missing, the test is skipped and the skip reason explains what to set.
