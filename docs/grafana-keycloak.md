# Grafana (otel-lgtm) and Keycloak OIDC

For **Loki logs, Promtail, and the “M8Flow Unified Logs” dashboard**, see [grafana-logs.md](grafana-logs.md).

The Docker Compose service `otel-lgtm` ([`docker/m8flow-docker-compose.yml`](../docker/m8flow-docker-compose.yml)) runs Grafana (bundled in `grafana/otel-lgtm`) on host port **`GRAFANA_HTTP_PORT`** (default **3000**).

Authentication is driven entirely by **`GRAFANA_*`** (and **`KEYCLOAK_HOSTNAME`**) in [`.env`](../sample.env) / [`sample.env`](../sample.env). Compose maps those values to Grafana `GF_*` variables on the `otel-lgtm` service only (see `otel-lgtm.environment`).

There is **no separate Compose file** for Grafana modes: you edit `.env`, then recreate the container.

---

## Switching between local development and production

### What actually changes

| Goal | What you do |
|------|--------------|
| Use **local anonymous** Grafana | Set the variables in the **Local dev** column below, restart `otel-lgtm`. |
| Use **production** Grafana (OIDC, no anonymous UI) | Set the variables in the **Production** column below, restart `otel-lgtm`. |
| **Test production-like OIDC on your laptop** | Use **Production** settings but keep **`GRAFANA_SERVER_ROOT_URL`** and **`KEYCLOAK_HOSTNAME`** on **`http://localhost:…`** (see [Production-style auth on localhost](#production-style-auth-on-localhost)). |

`GRAFANA_ENV_MODE` is **documentation only** (e.g. `local` vs `production`). Grafana does not read it; it helps your team remember which profile you intended.

After **any** Grafana auth change:

```bash
docker compose -f docker/m8flow-docker-compose.yml up -d otel-lgtm
```

### Variable checklist (copy/paste discipline)

Switch modes by changing these keys in `.env` (all are documented in [`sample.env`](../sample.env)):

| Variable | Local development | Production |
|----------|-------------------|------------|
| `GRAFANA_ENV_MODE` | `local` (label) | `production` (label) |
| `GRAFANA_AUTH_ANONYMOUS_ENABLED` | `true` | `false` |
| `GRAFANA_OIDC_ENABLED` | `false` | `true` |
| `GRAFANA_SERVER_ROOT_URL` | Often `http://localhost:3000` | Public Grafana URL, e.g. `https://grafana.example.com` |
| `KEYCLOAK_HOSTNAME` | URL your **browser** uses for Keycloak (e.g. `http://localhost:7002`) | Public Keycloak URL, e.g. `https://auth.example.com` |
| `GRAFANA_OIDC_CLIENT_ID` | N/A when OIDC off | Must match Keycloak **master** realm client (e.g. `grafana`) |
| `GRAFANA_OIDC_CLIENT_SECRET` | Empty when OIDC off | Confidential client secret from Keycloak |
| `GRAFANA_COOKIE_SECURE` | `false` for `http://` | `true` when `GRAFANA_SERVER_ROOT_URL` uses `https://` |
| `GRAFANA_AUTH_DISABLE_LOGIN_FORM` | Usually `false` | Optional `true` once OIDC works (Keycloak-only login) |

Shared in both modes (adjust only if you rename roles):

- **`GRAFANA_ALLOWED_ROLE`** — master-realm role name; users **without** this role do not get Grafana Admin when strict role mapping is on (see below).
- **`GRAFANA_OAUTH_ROLE_ATTRIBUTE_STRICT`** — typically `true` whenever OIDC is enabled.

---

## Local development (anonymous, no Keycloak for Grafana)

Typical `.env` choices:

- `GRAFANA_ENV_MODE=local`
- `GRAFANA_AUTH_ANONYMOUS_ENABLED=true`
- `GRAFANA_OIDC_ENABLED=false`
- `GRAFANA_OIDC_CLIENT_SECRET=` (empty)
- `GRAFANA_SERVER_ROOT_URL=http://localhost:3000` (or your chosen host/port)
- `GRAFANA_COOKIE_SECURE=false` if using `http://`

You do **not** need a Grafana client in Keycloak for this mode.

---

## Production deployment (OIDC, role-gated)

Typical `.env` choices:

- `GRAFANA_ENV_MODE=production`
- `GRAFANA_AUTH_ANONYMOUS_ENABLED=false`
- `GRAFANA_OIDC_ENABLED=true`
- `GRAFANA_SERVER_ROOT_URL` and **`KEYCLOAK_HOSTNAME`** set to the **public** URLs users type in the browser (usually `https://…`).
- `GRAFANA_OIDC_CLIENT_ID` / `GRAFANA_OIDC_CLIENT_SECRET` from a **confidential** client in Keycloak **master** realm.
- `GRAFANA_COOKIE_SECURE=true` when Grafana is served over HTTPS.

Then complete Keycloak steps below (client, redirect URIs, realm role, role mappers).

---

## Production-style auth on localhost

You can run **the same switches as production** while still using **`http://localhost:3000`** and **`http://localhost:7002`**:

- Set **`GRAFANA_AUTH_ANONYMOUS_ENABLED=false`**, **`GRAFANA_OIDC_ENABLED=true`**, **`GRAFANA_COOKIE_SECURE=false`** (required for HTTP).
- Register **`GRAFANA_SERVER_ROOT_URL=http://localhost:3000`** and matching redirect URI **`http://localhost:3000/login/generic_oauth`** on the Keycloak client.
- Keep **`KEYCLOAK_HOSTNAME=http://localhost:7002`** so the browser’s authorize URL matches your local Keycloak.

This is useful to validate OIDC and **`GRAFANA_ALLOWED_ROLE`** before pointing DNS at real hosts.

---

### Keycloak: create client

In realm **master**:

1. **Clients → Create client**
   - Client type: **OpenID Connect**
   - Client ID: match `GRAFANA_OIDC_CLIENT_ID` (e.g. `grafana`)
   - Client authentication: **On** (confidential), unless you intentionally use a public client + PKCE

2. **Login settings**

   - Root URL / Home URL: same as `GRAFANA_SERVER_ROOT_URL`
   - Valid redirect URIs: `{GRAFANA_SERVER_ROOT_URL}/login/generic_oauth`
   - Valid post logout redirect URIs: `{GRAFANA_SERVER_ROOT_URL}/login`
   - Web origins: Grafana origin only (scheme + host + port), e.g. `http://localhost:3000` or `https://grafana.example.com`

3. **Credentials**

   - Copy the client secret into `.env` as `GRAFANA_OIDC_CLIENT_SECRET`

### Keycloak: realm role for Grafana admins

1. **Realm roles → Create role** named exactly **`GRAFANA_ALLOWED_ROLE`** (default `grafana-admin`).
2. Assign that role to users who should access Grafana.

### Keycloak: expose `realm_access.roles` for Grafana

Grafana’s generic OAuth role mapping uses JMESPath on the OAuth **userinfo** response:

```text
contains(realm_access.roles[*], '<GRAFANA_ALLOWED_ROLE>') && 'Admin' || ''
```

Keycloak’s default userinfo may **not** include `realm_access.roles`. If login succeeds but Grafana denies access (no Admin role), add roles to the token or userinfo:

- Recommended: client scope / mapper **Realm roles** on the Grafana client so **`realm_access.roles`** appears in the **access token**, and ensure Grafana can evaluate roles (if userinfo is insufficient, you may need additional Grafana/Keycloak mapper tuning or consult Grafana docs for `id_token` role extraction).

Document your chosen mapper in team runbooks so upgrades stay consistent.

---

## Compose wiring notes

- **Browser → Keycloak authorize**: `GF_AUTH_GENERIC_OAUTH_AUTH_URL` is built from **`KEYCLOAK_HOSTNAME`** (must be reachable from the user’s browser).
- **Grafana container → Keycloak token/userinfo**: uses **`http://keycloak-proxy:7002`** inside the Docker network.

If Keycloak’s public hostname differs from Docker DNS (normal in production), keep **`KEYCLOAK_HOSTNAME`** as the **public** URL and leave internal URLs as in Compose.

---

## Verification

| Mode | Check |
|------|--------|
| Local (anonymous) | Open `GRAFANA_SERVER_ROOT_URL` — dashboard usable without signing in when anonymous is enabled |
| Production / OIDC | Anonymous browsing of Grafana as Admin should be off; **Sign in with Keycloak** works; users **without** `GRAFANA_ALLOWED_ROLE` do not receive Admin when strict mapping is on |

```bash
curl -fsS -o /dev/null -w "%{http_code}" "${GRAFANA_SERVER_ROOT_URL}/login"
```

Health of stack: `docker compose -f docker/m8flow-docker-compose.yml ps`
