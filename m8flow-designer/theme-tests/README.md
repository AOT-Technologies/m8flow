# Standalone Keycloak theme regression tests

Use a disposable Keycloak container on port 16842, with the repo's
`m8flow-backend/keycloak/themes/m8flow` mounted read-only at
`/opt/keycloak/themes/m8flow`. Run the cached `m8flow-keycloak` image with
`--entrypoint /opt/keycloak/bin/kc.sh`, bootstrap username `theme-test-admin`,
bootstrap password `theme-test-only-password`, and arguments:

```text
start-dev --db=dev-file --hostname-strict=false --features=organization
--spi-theme-cache-themes=false --spi-theme-cache-templates=false
--spi-theme-static-max-age=-1
```

After startup, pipe `setup-keycloak.sh` into `docker exec -i CONTAINER bash`.
In PowerShell, use `Get-Content -Raw theme-tests/setup-keycloak.sh | docker exec -i CONTAINER bash -c 'tr -d "\r" | bash'`
to remove carriage returns added by the native-command pipeline.
The fixture creates test users, clients and a deliberately username-only
authentication flow. **Never run it against an existing application container.**

From `m8flow-designer`, run:

```sh
npx playwright test --config playwright.keycloak.config.ts
```

Set `PLAYWRIGHT_CHANNEL=msedge` or `chrome` to use an installed browser.
Each test has a fresh browser context. Normal/Slow 3G coverage lives in
`e2e/login-resilience.spec.ts`, which exercises the real application and disables
cache with 400 ms latency and 400 kbps upload/download on the Keycloak origin
through Chromium CDP. It asserts that authentication requests matched the
throttling rule. Vite's unbundled designer modules remain unthrottled so CI tests
authentication loading rather than development-server download size.
Controlled recovery responses use actual FreeMarker-rendered challenge HTML.
These tests verify Keycloak credentials and theme behavior; host tenant/RBAC
integration is covered by the application's login and protected-route tests.
