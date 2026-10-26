import { createHash } from 'node:crypto';

import { expect, type BrowserContext, type Page } from '@playwright/test';

export type DesignerPersona = {
  username: string;
  password: string;
};

export function editorCredentials(): DesignerPersona {
  return {
    username: process.env.M8FLOW_E2E_EDITOR_USERNAME ?? 'editor',
    password: process.env.M8FLOW_E2E_EDITOR_PASSWORD ?? 'editor',
  };
}

export function superAdminCredentials(): DesignerPersona {
  return {
    username: process.env.M8FLOW_E2E_SUPER_ADMIN_USERNAME ?? 'super-admin',
    password: process.env.M8FLOW_E2E_SUPER_ADMIN_PASSWORD ?? 'super-admin',
  };
}

/**
 * Shared-realm seed users (m8flow-tenant-template.json + keycloak-init-realms.sh):
 * one user per role, password = username by default. Override per role with
 * M8FLOW_E2E_<ROLE>_USERNAME / M8FLOW_E2E_<ROLE>_PASSWORD.
 */
function seededPersona(envKey: string, fallback: string): DesignerPersona {
  return {
    username: process.env[`M8FLOW_E2E_${envKey}_USERNAME`] ?? fallback,
    password: process.env[`M8FLOW_E2E_${envKey}_PASSWORD`] ?? fallback,
  };
}

/** Shared-realm `admin` user, assigned the tenant-admin role. */
export function tenantAdminCredentials(): DesignerPersona {
  return seededPersona('TENANT_ADMIN', 'admin');
}

export function submitterCredentials(): DesignerPersona {
  return seededPersona('SUBMITTER', 'submitter');
}

export function viewerCredentials(): DesignerPersona {
  return seededPersona('VIEWER', 'viewer');
}

export function reviewerCredentials(): DesignerPersona {
  return seededPersona('REVIEWER', 'reviewer');
}

export function integratorCredentials(): DesignerPersona {
  return seededPersona('INTEGRATOR', 'integrator');
}

/**
 * Master-realm Keycloak bootstrap admin (KC_BOOTSTRAP_ADMIN_USERNAME, default
 * admin/admin). A real master-realm account WITHOUT the super-admin role --
 * used to prove Platform Admin access needs super-admin, not just a master login.
 */
export function masterBootstrapAdminCredentials(): DesignerPersona {
  return seededPersona('MASTER_BOOTSTRAP_ADMIN', 'admin');
}

export const SELECTED_TENANT_COOKIE = 'm8flow_selected_tenant';

function isDesignerOrigin(url: URL): boolean {
  return url.origin.includes('localhost:6853');
}

/** Clear app cookies + storage so each journey starts unauthenticated. */
export async function clearDesignerSession(page: Page): Promise<void> {
  await page.context().clearCookies();
  // Hit designer origin so we can clear storage; auto-redirect may start.
  await page.goto('/').catch(() => undefined);
  await page.evaluate(() => {
    try {
      localStorage.clear();
      sessionStorage.clear();
      // Force Keycloak to show the credential form on the next auto-login
      // (same flag logout() sets) so a leftover SSO session cannot silently
      // re-authenticate as the previous user.
      sessionStorage.setItem('m8flow_post_logout_prompt', '1');
    } catch {
      // Storage may be unavailable on about:blank / cross-origin hops.
    }
  }).catch(() => undefined);
  await page.context().clearCookies();
}

export async function cookieValue(page: Page, name: string): Promise<string | undefined> {
  const fromDocument = await page.evaluate((cookieName) => {
    const match = document.cookie
      .split('; ')
      .find((entry) => entry.startsWith(`${cookieName}=`));
    return match ? decodeURIComponent(match.slice(cookieName.length + 1)) : '';
  }, name);
  if (fromDocument) {
    return fromDocument;
  }
  const cookies = await page.context().cookies();
  return cookies.find((cookie) => cookie.name === name)?.value;
}

/**
 * Logged-out designer `/` auto-redirects to the shared-realm Keycloak login
 * (TenantSelectPage). Platform admin is offered as a link on that page.
 */
export async function expectSharedRealmKeycloakLogin(page: Page, timeout = 30_000): Promise<void> {
  await page.waitForURL(/\/realms\/m8flow\//, { timeout });
  await expectCombinedKeycloakLoginPage(page);
  await expect(page.locator('#m8f-master-login-button')).toBeVisible({ timeout });
}

/** Keycloak hosted login must collect username and password on one page. */
export async function expectCombinedKeycloakLoginPage(page: Page): Promise<void> {
  await expect(page.locator('#username')).toBeVisible();
  await expect(page.locator('#password')).toBeVisible();
  await expect(page.locator('#kc-login')).toBeVisible();
}

async function fillKeycloakCredentials(
  page: Page,
  persona: DesignerPersona,
): Promise<void> {
  await expectCombinedKeycloakLoginPage(page);
  await page.locator('#username').fill(persona.username);
  await page.locator('#password').fill(persona.password);
  await page.locator('#kc-login').click();
}

/** Seed users may still have Keycloak UPDATE_PASSWORD from the realm import. */
async function completeKeycloakUpdatePasswordIfShown(
  page: Page,
  persona: DesignerPersona,
): Promise<void> {
  const heading = page.getByRole('heading', { name: 'Update password', exact: true });
  if (!(await heading.isVisible())) {
    return;
  }
  await page.getByRole('textbox', { name: 'New Password' }).fill(persona.password);
  await page.getByRole('textbox', { name: 'Confirm password' }).fill(persona.password);
  await page.getByRole('button', { name: 'Submit' }).click();
}

async function waitForDesignerOrigin(page: Page): Promise<void> {
  await page.waitForURL((url) => isDesignerOrigin(url), { timeout: 60_000 });
}

async function waitAfterKeycloakCredentials(page: Page, persona: DesignerPersona): Promise<void> {
  const updatePassword = page.getByRole('heading', { name: 'Update password', exact: true });
  await Promise.race([
    page.waitForURL((url) => isDesignerOrigin(url), { timeout: 60_000 }),
    updatePassword.waitFor({ state: 'visible', timeout: 60_000 }),
  ]);
  await completeKeycloakUpdatePasswordIfShown(page, persona);
  await waitForDesignerOrigin(page);
}

async function openSharedRealmLogin(page: Page): Promise<void> {
  await clearDesignerSession(page);
  // The app redirects a logged-out '/' to Keycloak straight away, which can
  // interrupt page.goto itself. That redirect is exactly what we want, so
  // ignore the interruption and let expectSharedRealmKeycloakLogin wait for it.
  await page.goto('/').catch((error: unknown) => {
    if (!/interrupted by another navigation/i.test(String(error))) throw error;
  });
  await expectSharedRealmKeycloakLogin(page);
}

/**
 * Shared-realm sign-in through Keycloak, stopping once the browser is back
 * on designer. Callers assert Home, the tenant picker, or the zero-org gate.
 */
export async function signInAtSharedRealm(
  page: Page,
  persona: DesignerPersona,
): Promise<void> {
  await openSharedRealmLogin(page);
  await fillKeycloakCredentials(page, persona);
  await waitAfterKeycloakCredentials(page, persona);
}

/**
 * Shared-realm sign-in: designer `/` auto-redirect → Keycloak m8flow realm,
 * then tenant finalization and Home.
 */
export async function signInAsSharedRealmUser(
  page: Page,
  persona: DesignerPersona,
): Promise<void> {
  await signInAtSharedRealm(page, persona);
  await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible({
    timeout: 60_000,
  });
  await rememberSession(page.context(), sessionKey('shared', persona));
}

/**
 * Platform admin sign-in: shared-realm Keycloak → "Platform admin sign in"
 * link → master realm credentials → designer Home.
 */
export async function signInAsPlatformAdmin(
  page: Page,
  persona: DesignerPersona,
): Promise<void> {
  await openSharedRealmLogin(page);
  await page.locator('#m8f-master-login-button').click();
  await page.waitForURL(/\/realms\/master\//, { timeout: 30_000 });
  await fillKeycloakCredentials(page, persona);
  await waitAfterKeycloakCredentials(page, persona);
  // Master-realm redirect targets /tenants (GLOBAL_ADMIN_LANDING_PATH).
  await expect(page.getByRole('heading', { name: 'Tenants', exact: true })).toBeVisible({
    timeout: 60_000,
  });
  await rememberSession(page.context(), sessionKey('platformAdmin', persona));
}

// ---------------------------------------------------------------------------
// Session reuse
// Logging in through Keycloak takes several seconds per test. Every successful
// signInAsSharedRealmUser / signInAsPlatformAdmin saves that user's cookies
// (the session is cookie-based: access/refresh/id tokens + selected tenant).
// useSession() puts those cookies into the next test's fresh browser context
// instead of logging in again. The cache lives in memory for one test run
// (workers: 1), so nothing is written to disk.
// A test that is about the login itself, or needs a logged-out start, must
// keep using the full sign-in helpers.
// ---------------------------------------------------------------------------

type SessionKind = 'shared' | 'platformAdmin';
type SavedCookies = Awaited<ReturnType<BrowserContext['cookies']>>;

const savedSessions = new Map<string, SavedCookies>();

/** Keycloak realm each session kind signs in to. */
const SESSION_REALM: Record<SessionKind, string> = { shared: 'm8flow', platformAdmin: 'master' };

/**
 * Cache key for a saved session: realm + username + a short fingerprint of the
 * password, so the same username in another realm, or with other credentials,
 * never reuses a saved session. Kept in memory only; the password itself is
 * not part of the key.
 */
function sessionKey(kind: SessionKind, persona: DesignerPersona): string {
  const fingerprint = createHash('sha256').update(persona.password).digest('hex').slice(0, 12);
  return `${SESSION_REALM[kind]}:${kind}:${persona.username}:${fingerprint}`;
}

async function rememberSession(context: BrowserContext, key: string): Promise<void> {
  savedSessions.set(key, await context.cookies());
}

/** Drops every saved session that uses this access token (called on logout). */
function forgetSessionsWithToken(accessToken: string | undefined): void {
  if (!accessToken) return;
  for (const [key, cookies] of savedSessions) {
    if (cookies.some((c) => c.name === 'access_token' && c.value === accessToken)) {
      savedSessions.delete(key);
    }
  }
}

/**
 * Signed in as `persona`, reusing a saved session when possible.
 * - shared (default): lands on Home, like signInAsSharedRealmUser.
 * - platformAdmin: lands on Tenants, like signInAsPlatformAdmin.
 * If the saved session is gone or no longer valid, logs in normally.
 */
export async function useSession(
  page: Page,
  persona: DesignerPersona,
  kind: SessionKind = 'shared',
): Promise<void> {
  const key = sessionKey(kind, persona);
  const cookies = savedSessions.get(key);
  if (cookies) {
    await page.context().clearCookies();
    await page.context().addCookies(cookies);
    await page.goto(kind === 'platformAdmin' ? '/tenants' : '/');
    const landing = page.getByRole('heading', {
      name: kind === 'platformAdmin' ? 'Tenants' : 'Home',
      exact: true,
    });
    // Either the app loads (session still valid) or Keycloak asks to log in
    // (session expired). Anything else is a real failure, not a reason to
    // silently log in again.
    const kcLogin = page.locator('#kc-login');
    try {
      await landing.or(kcLogin).first().waitFor({ state: 'visible', timeout: 30_000 });
    } catch {
      savedSessions.delete(key);
      throw new Error(
        `useSession(${key}): neither the ${kind === 'platformAdmin' ? 'Tenants' : 'Home'} page ` +
          `nor the Keycloak login appeared within 30s. Current URL: ${page.url()}`,
      );
    }
    if (await landing.isVisible()) {
      return;
    }
    // Saved session expired: Keycloak is asking to log in, so log in fresh.
    savedSessions.delete(key);
  }
  if (kind === 'platformAdmin') {
    await signInAsPlatformAdmin(page, persona);
  } else {
    await signInAsSharedRealmUser(page, persona);
  }
}

/**
 * Submit credentials on the shared-realm login form without asserting the
 * outcome -- for negative journeys (wrong password, master-only user).
 */
export async function submitSharedRealmCredentials(
  page: Page,
  persona: DesignerPersona,
): Promise<void> {
  await openSharedRealmLogin(page);
  await fillKeycloakCredentials(page, persona);
}

/**
 * Click "Platform Admin Sign In" and submit credentials on the master-realm
 * form without asserting the outcome -- for negative journeys.
 */
export async function submitPlatformAdminCredentials(
  page: Page,
  persona: DesignerPersona,
): Promise<void> {
  await openSharedRealmLogin(page);
  await page.locator('#m8f-master-login-button').click();
  await page.waitForURL(/\/realms\/master\//, { timeout: 30_000 });
  await fillKeycloakCredentials(page, persona);
}

const KEYCLOAK_REALM_URL = {
  m8flow: /\/realms\/m8flow\//,
  master: /\/realms\/master\//,
} as const;

/** Keycloak rejected the credentials and kept the user on that realm's login form. */
export async function expectKeycloakInvalidCredentials(
  page: Page,
  realm: 'm8flow' | 'master',
): Promise<void> {
  await expect(page.locator('#input-error').first()).toContainText(
    'Invalid username or password.',
  );
  await expect(page).toHaveURL(KEYCLOAK_REALM_URL[realm]);
  await expectCombinedKeycloakLoginPage(page);
}

export async function logOutFromDesigner(page: Page): Promise<void> {
  // A logged-out session must not be reused by later tests.
  forgetSessionsWithToken(await cookieValue(page, 'access_token'));
  await openProfileMenu(page);
  await page.getByRole('menuitem', { name: 'Log out' }).click();
  // Logout hops through backend + Keycloak, then designer auto-redirects
  // back to the shared-realm login form.
  await expectSharedRealmKeycloakLogin(page, 60_000);
}

export async function openProfileMenu(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Profile' }).click();
  await expect(page.getByRole('menu', { name: 'Profile' })).toBeVisible();
}

/**
 * Super-admin-only sidebar tenant filter (Sidebar.tsx's `showTenantSelector`,
 * a `ui/select`). `label` is the tenant's display name as shown in the option
 * (e.g. `'m8flow'`), not its id.
 */
export async function selectSidebarTenant(page: Page, label: string): Promise<void> {
  await page.getByRole('combobox', { name: /Tenant/ }).click();
  await page.getByRole('option', { name: label, exact: true }).click();
}
