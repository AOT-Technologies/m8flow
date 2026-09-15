/**
 * Login for m8flow-designer piggybacks on the same backend-mediated Keycloak
 * flow m8flow-frontend uses (see UserService.ts there): the browser is sent to
 * the host backend's `/v1.0/login` route, which redirects to Keycloak's hosted
 * login page (the "Keycloak login page" referred to here — it is served by
 * Keycloak/the backend, not by any frontend React component). Keycloak then
 * redirects to the backend's `/v1.0/login_return`, which exchanges the code
 * for tokens and sets non-httpOnly `access_token` / `id_token` cookies on
 * this shared `localhost` host before finally redirecting back here.
 *
 * See m8flow_backend/routes/login_controller.py for the backend side.
 */

const BACKEND_BASE_URL: string =
  (import.meta.env.VITE_BACKEND_BASE_URL as string | undefined) ?? 'http://localhost:6840';

function readCookie(name: string): string | null {
  const match = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split('.')[1];
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    return JSON.parse(atob(padded)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function tokenIsExpired(decoded: Record<string, unknown> | null): boolean {
  const exp = decoded?.exp;
  if (typeof exp !== 'number') {
    return false;
  }
  return exp * 1000 <= Date.now();
}

export function getAccessToken(): string | null {
  return readCookie('access_token');
}

export function isLoggedIn(): boolean {
  const token = getAccessToken();
  if (!token) {
    return false;
  }
  return !tokenIsExpired(decodeJwtPayload(token));
}

export function getCurrentUser(): { username: string | null; email: string | null } | null {
  const token = readCookie('id_token') ?? getAccessToken();
  if (!token) {
    return null;
  }
  const decoded = decodeJwtPayload(token);
  if (!decoded) {
    return null;
  }
  return {
    username: typeof decoded.preferred_username === 'string' ? decoded.preferred_username : null,
    email: typeof decoded.email === 'string' ? decoded.email : null,
  };
}

const SUPER_ADMIN_ROLE = 'super-admin';

function groupIndicatesSuperAdmin(group: string): boolean {
  const normalized = group.replace(/^\/+|\/+$/g, '').split('/').pop();
  return (
    normalized === SUPER_ADMIN_ROLE ||
    (normalized?.endsWith(`:${SUPER_ADMIN_ROLE}`) ?? false)
  );
}

function tokenIndicatesSuperAdmin(decoded: Record<string, unknown>): boolean {
  const roles = decoded.roles;
  if (Array.isArray(roles) && roles.includes(SUPER_ADMIN_ROLE)) {
    return true;
  }

  const groups = decoded.groups;
  if (Array.isArray(groups)) {
    for (const group of groups) {
      if (typeof group === 'string' && groupIndicatesSuperAdmin(group)) {
        return true;
      }
    }
  }

  const realmAccess = decoded.realm_access;
  if (realmAccess && typeof realmAccess === 'object') {
    const realmRoles = (realmAccess as Record<string, unknown>).roles;
    if (Array.isArray(realmRoles) && realmRoles.includes(SUPER_ADMIN_ROLE)) {
      return true;
    }
  }

  return false;
}

/**
 * Mirrors m8flow-frontend UserService.isSuperAdmin() — client-side JWT
 * heuristic only (ticket 02). Prefer access_token (Keycloak puts M8Flow
 * roles in a top-level `roles` claim there), fall back to id_token.
 */
export function isSuperAdmin(): boolean {
  for (const token of [getAccessToken(), readCookie('id_token')]) {
    const decoded = token ? decodeJwtPayload(token) : null;
    if (decoded && tokenIndicatesSuperAdmin(decoded)) {
      return true;
    }
  }
  return false;
}

export const MASTER_REALM_IDENTIFIER = 'master';
export const SELECTED_TENANT_COOKIE = 'm8flow_selected_tenant';
export const GLOBAL_ADMIN_LANDING_PATH = '/tenants';

const TENANT_FINALIZATION_REDIRECT_EXEMPT_PATHS = new Set(['/', '/tenant']);

export type OrganizationMembership = {
  alias: string;
  id: string | null;
  name: string | null;
};

export function getSelectedTenantId(): string | null {
  return readCookie(SELECTED_TENANT_COOKIE);
}

/**
 * Prefer the directory/JWT display name for the active tenant cookie.
 * Cookie may be the tenant id; JWT org claims often omit `name`.
 */
export function labelForActiveTenant(
  selected: string | null | undefined,
  memberships: OrganizationMembership[],
): string | null {
  const trimmed = selected?.trim();
  if (!trimmed) {
    return null;
  }
  for (const membership of memberships) {
    if (membership.id === trimmed || membership.alias === trimmed) {
      const name = membership.name?.trim();
      if (name) {
        return name;
      }
      const alias = membership.alias?.trim();
      if (alias) {
        return alias;
      }
    }
  }
  return trimmed;
}

/**
 * Label for the non-super-admin shell badge. Cookie is the active tenant;
 * membership name is display-only. Never reads localStorage.
 */
export function getActiveTenantDisplayLabel(
  extraMemberships: OrganizationMembership[] = [],
): string | null {
  const memberships =
    extraMemberships.length > 0
      ? extraMemberships
      : getOrganizationMemberships();
  return labelForActiveTenant(getSelectedTenantId(), memberships);
}

export function clearSelectedTenantCookie(): void {
  document.cookie = `${SELECTED_TENANT_COOKIE}=; Max-Age=0; Path=/`;
}

export function getAuthenticationIdentifier(): string | null {
  const value = readCookie('authentication_identifier');
  return value && value.trim() ? value.trim() : null;
}

/** Master-realm session or super-admin: skip the shared-realm cookie gate. */
export function skipsTenantCookieGate(): boolean {
  return isSuperAdmin() || getAuthenticationIdentifier() === MASTER_REALM_IDENTIFIER;
}

function membershipsFromPayload(decoded: Record<string, unknown>): OrganizationMembership[] {
  const claim = decoded.organization;
  if (Array.isArray(claim)) {
    return claim.flatMap((item) => {
      if (typeof item === 'string' && item.trim()) {
        return [{ alias: item.trim(), id: null, name: null }];
      }
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const record = item as Record<string, unknown>;
        const alias = typeof record.alias === 'string' ? record.alias.trim() : '';
        if (!alias) {
          return [];
        }
        return [
          {
            alias,
            id: typeof record.id === 'string' && record.id.trim() ? record.id.trim() : null,
            name: typeof record.name === 'string' && record.name.trim() ? record.name.trim() : null,
          },
        ];
      }
      return [];
    });
  }
  if (!claim || typeof claim !== 'object') {
    return [];
  }
  return Object.entries(claim).flatMap(([alias, details]) => {
    const trimmedAlias = alias.trim();
    if (!trimmedAlias) {
      return [];
    }
    if (!details || typeof details !== 'object' || Array.isArray(details)) {
      return [{ alias: trimmedAlias, id: null, name: null }];
    }
    const record = details as Record<string, unknown>;
    return [
      {
        alias: trimmedAlias,
        id: typeof record.id === 'string' && record.id.trim() ? record.id.trim() : null,
        name: typeof record.name === 'string' && record.name.trim() ? record.name.trim() : null,
      },
    ];
  });
}

/**
 * Shared-realm organizations from the current JWT. Names may be missing;
 * load display names from GET /v1.0/m8flow/organization-memberships when needed.
 */
export function getOrganizationMemberships(): OrganizationMembership[] {
  for (const token of [readCookie('id_token'), getAccessToken()]) {
    const decoded = token ? decodeJwtPayload(token) : null;
    if (!decoded) {
      continue;
    }
    const memberships = membershipsFromPayload(decoded);
    if (memberships.length > 0) {
      return memberships;
    }
  }
  return [];
}

export function isTenantSelectionExemptPath(pathname: string): boolean {
  return pathname === '/accept-invitation' || pathname.startsWith('/accept-invitation/');
}

/**
 * Whether the designer should show the landing / tenant-selection page.
 * `localStorage` is never treated as finalization; only `m8flow_selected_tenant`.
 */
export function shouldShowTenantSelectionGate(pathname: string): boolean {
  if (isTenantSelectionExemptPath(pathname)) {
    return false;
  }
  if (!isLoggedIn()) {
    return true;
  }
  if (skipsTenantCookieGate()) {
    return false;
  }
  if (pathname === '/tenant') {
    return true;
  }
  return !getSelectedTenantId();
}

export function tenantFinalizationRedirectUrl(): string {
  const pathname = window.location.pathname || '/';
  if (TENANT_FINALIZATION_REDIRECT_EXEMPT_PATHS.has(pathname)) {
    return `${window.location.origin}/`;
  }
  return `${window.location.origin}${pathname}${window.location.search || ''}`;
}

const POST_LOGOUT_PROMPT_KEY = 'm8flow_post_logout_prompt';
const LAST_AUTH_REALM_KEY = 'm8flow_last_auth_realm';

function consumePostLogoutPrompt(): boolean {
  try {
    if (sessionStorage.getItem(POST_LOGOUT_PROMPT_KEY) !== '1') {
      return false;
    }
    sessionStorage.removeItem(POST_LOGOUT_PROMPT_KEY);
    return true;
  } catch {
    return false;
  }
}

/** Realm used for the previous session (set on logout so we resume the same Keycloak realm). */
export function getLastAuthRealm(): string | null {
  try {
    const value = sessionStorage.getItem(LAST_AUTH_REALM_KEY);
    return value && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

export function login(options?: {
  authenticationIdentifier?: string;
  /** Force Keycloak to show the credential form (no silent SSO). */
  promptLogin?: boolean;
  tenant?: string;
  tenantFinalization?: boolean;
  redirectUrl?: string;
}): void {
  const redirectUrl = options?.redirectUrl ?? window.location.href;
  const params = new URLSearchParams({
    redirect_url: redirectUrl,
  });
  const fromQuery = new URLSearchParams(window.location.search).get(
    'authentication_identifier',
  );
  const identifier = options?.authenticationIdentifier || fromQuery;
  if (identifier) {
    params.set('authentication_identifier', identifier);
  }
  if (options?.tenant) {
    params.set('tenant', options.tenant);
  }
  if (options?.tenantFinalization) {
    params.set('tenant_finalization', '1');
  }
  // Always evaluate the post-logout flag (do not short-circuit) so it is cleared.
  const fromLogout = consumePostLogoutPrompt();
  if (!options?.tenantFinalization && (options?.promptLogin || fromLogout)) {
    params.set('prompt', 'login');
  }
  window.location.href = `${BACKEND_BASE_URL}/v1.0/login?${params.toString()}`;
}

/** Master-realm platform admin login (Keycloak `super-admin` role). Lands on the tenant registry. */
export function loginAsPlatformAdmin(options?: {
  promptLogin?: boolean;
  redirectUrl?: string;
}): void {
  login({
    authenticationIdentifier: MASTER_REALM_IDENTIFIER,
    promptLogin: options?.promptLogin,
    redirectUrl:
      options?.redirectUrl ?? `${window.location.origin}${GLOBAL_ADMIN_LANDING_PATH}`,
  });
}

/** Backend hop that sets `m8flow_selected_tenant` for one shared-realm organization. */
export function finalizeTenantLogin(organization: OrganizationMembership): void {
  login({
    authenticationIdentifier: getAuthenticationIdentifier() || undefined,
    tenant: organization.alias,
    tenantFinalization: true,
    redirectUrl: tenantFinalizationRedirectUrl(),
  });
}

/**
 * After logout / cold visit: resume the same realm as the last session when
 * known (so platform admins return to master), and always force the Keycloak
 * credential form so a leftover SSO cookie cannot skip the password prompt.
 */
export function resumeLoginAfterLogout(): void {
  const lastRealm = getLastAuthRealm();
  if (lastRealm === 'master') {
    loginAsPlatformAdmin({ promptLogin: true });
    return;
  }
  login({
    authenticationIdentifier: lastRealm || undefined,
    promptLogin: true,
  });
}

export function logout(): void {
  const idToken = readCookie('id_token') ?? '';
  const authId = readCookie('authentication_identifier') ?? '';
  try {
    sessionStorage.setItem(POST_LOGOUT_PROMPT_KEY, '1');
    if (authId) {
      sessionStorage.setItem(LAST_AUTH_REALM_KEY, authId);
    }
  } catch {
    // sessionStorage may be unavailable; logout still proceeds.
  }
  // Trailing slash so Keycloak's registered `http://localhost:6853/*`
  // post-logout URI matches (bare origin often fails "Invalid redirect uri").
  const redirectUrl = `${window.location.origin}/`;
  const params = new URLSearchParams({
    redirect_url: redirectUrl,
    id_token: idToken,
  });
  if (authId) {
    params.set('authentication_identifier', authId);
  }
  window.location.href = `${BACKEND_BASE_URL}/v1.0/logout?${params.toString()}`;
}
