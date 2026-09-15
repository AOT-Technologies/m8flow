import { expect, type Page } from '@playwright/test';

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
  await page.goto('/');
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
}

export async function logOutFromDesigner(page: Page): Promise<void> {
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
 * Super-admin-only sidebar tenant filter (Sidebar.tsx's `showTenantSelector`).
 * `label` is the tenant's display name as shown in the `<option>` (e.g.
 * `'m8flow'`), not its id — the option value isn't guaranteed to match.
 */
export async function selectSidebarTenant(page: Page, label: string): Promise<void> {
  await page.getByRole('combobox', { name: /Tenant/ }).selectOption({ label });
}
