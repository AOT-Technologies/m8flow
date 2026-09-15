# m8flow-designer

A small standalone React app: sign in, land on a home page. It is intentionally
independent of `m8flow-frontend`'s SpiffArena-derived app shell (Carbon/MUI,
`@spiffworkflow-frontend` aliasing, tenant-selection gate, etc.) — a plain
Vite + React + TypeScript project with two dependencies (`react`,
`react-dom`).

## Login

There is no Keycloak-hosted login page *component* to copy into a frontend —
Keycloak serves its own login page (themed via
`m8flow-backend/keycloak/themes/m8flow/login/`). What m8flow-frontend's
`UserService.doLogin()` conceptually does is redirect the browser to the host
backend, which redirects to that Keycloak page, and Keycloak redirects back
once the user authenticates, with `access_token` / `id_token` cookies set by
the backend. `src/auth.ts` here follows that same pattern:

- `login()` / `loginAsPlatformAdmin()` send the browser to
  `${VITE_BACKEND_BASE_URL}/v1.0/login?...`. Logged-out visits auto-redirect
  straight to Keycloak's shared "m8flow" realm sign-in — the designer's
  tenant-selection gate no longer renders a realm chooser. Platform admins
  reach the master realm via the "Platform Admin Sign In" link Keycloak's own
  login page renders (see `m8flow-backend/keycloak/themes/m8flow/login/`).
  After shared-realm login, a user with one
  organization is finalized via `GET /v1.0/login?...&tenant=<alias>&tenant_finalization=1`;
  a user with many organizations picks one on the same page. The active tenant
  is the `m8flow_selected_tenant` cookie — not `localStorage`.
  `/accept-invitation?token=…` is a public page (no tenant gate): validate,
  set password (min 8), then **Go to login** — it does not auto-login.
  Invitation emails and JSON `invitation_link` use this designer origin
  (`M8FLOW_FRONTEND_BASE_URL`, default `http://localhost:6853`), not leftover
  frontend `:6841`.
- Keycloak redirects to the backend's `/v1.0/login_return`, which exchanges
  the authorization code for tokens (server-side, via the confidential
  `m8flow-backend` Keycloak client) and sets `access_token` / `id_token`
  cookies before redirecting back to `redirect_url`.
- `isLoggedIn()` / `getCurrentUser()` / `isSuperAdmin()` read those cookies.
- `logout()` sends the browser to `${VITE_BACKEND_BASE_URL}/v1.0/logout?...`,
  which clears the app's cookies and ends the Keycloak SSO session.

The browser-redirect `GET /v1.0/login` / `/v1.0/login_return` / `/v1.0/logout`
routes live in `m8flow-backend/src/m8flow_backend/routes/login_controller.py`
— they didn't exist when this app was first scaffolded (dropped along with
the rest of the upstream auth controller during the `m8flow-bpmn-core`
cutover, `9819b5586`, and not listed in `docs/dropped-routes.md` as an
intentional removal) and were added back separately. Verified end-to-end
against a running Keycloak + backend with the seeded non-admin `editor` user.

## Running

```sh
cd m8flow-designer
npm install
npm run dev       # http://localhost:6853
```

`VITE_BACKEND_BASE_URL` defaults to `http://localhost:${M8FLOW_BACKEND_PORT}`
(from the repo-root `.env`, normally `6840`) via `vite.config.ts`; override it
with an env var if needed. Dev API calls use a Vite proxy on `/v1.0` (same
origin) so credentialed Home fetches do not depend on cross-port CORS;
login/logout still hit the absolute backend URL so Keycloak's redirect URI
stays on `:6840`.

## E2E (Playwright)

Requires a running backend + Keycloak (docker compose) on the usual local
ports. Credentials default to the seeded local users and can be overridden:

```sh
cd m8flow-designer
npm run test:e2e
# optional:
# M8FLOW_E2E_EDITOR_USERNAME=editor M8FLOW_E2E_EDITOR_PASSWORD=editor \
# M8FLOW_E2E_SUPER_ADMIN_USERNAME=super-admin M8FLOW_E2E_SUPER_ADMIN_PASSWORD=super-admin \
# npm run test:e2e
```

Journeys: `e2e/login.spec.ts` (CHK-01 editor Home, CHK-02 platform admin) and
`e2e/identity-auth-parity.spec.ts` (PAR-01–07: landing, editor onboarding/tasks,
multi-org picker, zero-org gate, auto-finalize, logout/cookie gate,
accept-invitation). Requires docker compose
(backend `:6840`, Keycloak `:6842`) plus designer `:6853`.
