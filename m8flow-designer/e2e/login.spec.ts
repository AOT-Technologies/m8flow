import { expect, test, type Page } from '@playwright/test';

import {
  type DesignerPersona,
  editorCredentials,
  expectKeycloakInvalidCredentials,
  integratorCredentials,
  masterBootstrapAdminCredentials,
  openProfileMenu,
  reviewerCredentials,
  signInAsPlatformAdmin,
  signInAsSharedRealmUser,
  submitPlatformAdminCredentials,
  submitSharedRealmCredentials,
  submitterCredentials,
  superAdminCredentials,
  tenantAdminCredentials,
  useSession,
  viewerCredentials,
} from './helpers/auth';

/**
 * LGN-01..07 -- login to M8Flow and Platform Admin access through the live
 * UI -> backend -> Keycloak seam. (Formerly CHK-01/CHK-02, renamed so the IDs
 * no longer clash with processes.spec.ts.)
 *
 * Platform Admin = the master-realm "Platform Admin Sign In" link on the
 * shared-realm Keycloak page, plus the platform-admin-only chrome it unlocks:
 * Tenants nav + /tenants registry, the All Tenants selector, and the
 * Total tenants KPI. Keycloak shows the link to everyone before login, so
 * "restricted to super-admin" is asserted as: only super-admin can sign in
 * through it, and no other role sees or can use platform-admin features.
 *
 * Each test ends with a one-line result message (console.log), printed only
 * when every check in the test has passed.
 */

type SharedRealmRole = {
  role: string;
  /** Role name as written in the result messages. */
  label: string;
  credentials: () => DesignerPersona;
  /** Tenant Management nav is tenant-admin only (hidden for super-admin too). */
  tenantManagementNav: boolean;
  /** Keycloak's master bootstrap admin shares this username -- see LGN-05b. */
  sharesMasterUsername?: boolean;
};

const SHARED_REALM_ROLES: SharedRealmRole[] = [
  { role: 'tenant-admin', label: 'Tenant admin', credentials: tenantAdminCredentials, tenantManagementNav: true, sharesMasterUsername: true },
  { role: 'editor', label: 'Editor', credentials: editorCredentials, tenantManagementNav: false },
  { role: 'submitter', label: 'Submitter', credentials: submitterCredentials, tenantManagementNav: false },
  { role: 'viewer', label: 'Viewer', credentials: viewerCredentials, tenantManagementNav: false },
  { role: 'reviewer', label: 'Reviewer', credentials: reviewerCredentials, tenantManagementNav: false },
  { role: 'integrator', label: 'Integrator', credentials: integratorCredentials, tenantManagementNav: false },
];

function tenantsNav(page: Page) {
  return page.getByRole('link', { name: 'Tenants', exact: true });
}

function tenantSelector(page: Page) {
  return page.getByRole('combobox', { name: /Tenant/ });
}

async function expectProfileShows(page: Page, username: string) {
  await openProfileMenu(page);
  await expect(page.getByRole('menu', { name: 'Profile' })).toContainText(username);
  await page.keyboard.press('Escape');
}

test.describe('Login -- shared-realm roles', () => {
  for (const { role, label, credentials, tenantManagementNav } of SHARED_REALM_ROLES) {
    test(`LGN-01 [${role}]: signs in and lands on Home without platform-admin chrome`, async ({
      page,
    }) => {
      const persona = credentials();

      await signInAsSharedRealmUser(page, persona);
      await expectProfileShows(page, persona.username);

      // Home loaded with a tenant (no tenant-cookie 400 alert).
      await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible();
      await expect(page.getByRole('alert')).toHaveCount(0);

      // No platform-admin chrome for any shared-realm role.
      await expect(tenantSelector(page)).toHaveCount(0);
      await expect(page.getByText('Total tenants', { exact: true })).toHaveCount(0);
      await expect(tenantsNav(page)).toHaveCount(0);

      // Role-appropriate nav: Tenant Management is tenant-admin only.
      await expect(page.getByRole('link', { name: 'Tenant Management', exact: true })).toHaveCount(
        tenantManagementNav ? 1 : 0,
      );

      console.log(
        `[LGN-01] ${label} logged in successfully; platform-admin options are hidden` +
          (tenantManagementNav ? ' and Tenant Management is shown.' : '.'),
      );
    });
  }

  test('LGN-06: wrong password is rejected at the shared-realm login', async ({ page }) => {
    const editor = editorCredentials();
    await submitSharedRealmCredentials(page, { ...editor, password: `${editor.password}-wrong` });
    await expectKeycloakInvalidCredentials(page, 'm8flow');
    console.log('[LGN-06] Login with a wrong password was rejected with "Invalid username or password."');
  });

  test('LGN-07: super-admin cannot sign in through the shared-realm form', async ({ page }) => {
    // super-admin lives only in the master realm.
    await submitSharedRealmCredentials(page, superAdminCredentials());
    await expectKeycloakInvalidCredentials(page, 'm8flow');
    console.log('[LGN-07] Super admin cannot log in through the normal login form; Platform Admin Sign In is required.');
  });
});

test.describe('Login -- super-admin (Platform Admin)', () => {
  test('LGN-02: super-admin signs in via Platform Admin and gets All Tenants scope', async ({
    page,
  }) => {
    const admin = superAdminCredentials();

    // Lands on /tenants (GLOBAL_ADMIN_LANDING_PATH).
    await signInAsPlatformAdmin(page, admin);
    await expectProfileShows(page, admin.username);

    await expect(tenantsNav(page)).toBeVisible();
    await expect(page.getByRole('link', { name: 'Tenant Management', exact: true })).toHaveCount(0);

    await page.getByRole('link', { name: 'Home', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible({
      timeout: 30_000,
    });
    await expect(tenantSelector(page)).toBeVisible();
    await expect(tenantSelector(page)).toHaveText('All tenants');
    await expect(page.getByText('Total tenants', { exact: true })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByText('Active process instances', { exact: true })).toBeVisible();

    console.log('[LGN-02] Super admin logged in via Platform Admin Sign In and sees the All tenants scope.');
  });

  test('LGN-03: super-admin can open the tenant registry (UI and API)', async ({ page }) => {
    // Reuses the super-admin session from LGN-02 (no new login).
    await useSession(page, superAdminCredentials(), 'platformAdmin');

    await tenantsNav(page).click();
    await expect(page.getByRole('heading', { name: 'Tenants', exact: true })).toBeVisible();
    await expect(page.getByText('Not available', { exact: true })).toHaveCount(0);

    const response = await page.request.get('/v1.0/m8flow/tenants');
    expect(response.status()).toBe(200);

    console.log('[LGN-03] Super admin can access the tenant registry (page loads, API returned 200).');
  });
});

test.describe('Platform Admin access is restricted to super-admin', () => {
  for (const { role, label, credentials, sharesMasterUsername } of SHARED_REALM_ROLES) {
    test(`LGN-04 [${role}]: cannot open the tenant registry (UI or API)`, async ({ page }) => {
      // Reuses this role's session from LGN-01 (no new login).
      await useSession(page, credentials());

      await page.goto('/tenants');
      await expect(page.getByRole('heading', { name: 'Tenants', exact: true })).toBeVisible();
      await expect(page.getByText('Not available', { exact: true })).toBeVisible();
      await expect(
        page.getByText('The tenant registry is for platform admins. Your role cannot list or manage'),
      ).toBeVisible();
      await expect(tenantsNav(page)).toHaveCount(0);

      // UI bypass: the registry API must refuse a non-super-admin directly.
      const response = await page.request.get('/v1.0/m8flow/tenants');
      expect(response.status()).toBe(403);

      console.log(`[LGN-04] Platform Admin access is restricted for ${label} users: tenant registry shows "Not available" and the API returned 403.`);
    });

    test(`LGN-05 [${role}]: is rejected at Platform Admin sign-in`, async ({ page }) => {
      test.skip(
        Boolean(sharesMasterUsername),
        'Master realm has its own bootstrap "admin" account with the same default credentials -- covered by LGN-05b.',
      );
      // Shared-realm users do not exist in the master realm.
      await submitPlatformAdminCredentials(page, credentials());
      await expectKeycloakInvalidCredentials(page, 'master');

      console.log(`[LGN-05] Platform Admin Sign In is restricted for ${label} users: login was rejected.`);
    });
  }

  test('LGN-05b: master-realm account without super-admin gets no Platform Admin access', async ({
    page,
    baseURL,
  }) => {
    const originSource = baseURL ?? process.env.M8FLOW_DESIGNER_BASE_URL;
    expect(originSource, 'Designer base URL must be configured (Playwright baseURL or M8FLOW_DESIGNER_BASE_URL)').toBeTruthy();
    const designerOrigin = new URL(originSource!).origin;
    await submitPlatformAdminCredentials(page, masterBootstrapAdminCredentials());

    const rejected = page.locator('#input-error').first();
    await Promise.race([
      rejected.waitFor({ state: 'visible', timeout: 60_000 }),
      page.waitForURL((url) => url.origin === designerOrigin, { timeout: 60_000 }),
    ]);
    if (await rejected.isVisible()) {
      // Acceptable outcome 1: Keycloak/backend refuses the login outright.
      await expect(page).toHaveURL(/\/realms\/master\//);
      console.log('[LGN-05b] Master account without the super-admin role was rejected at Platform Admin Sign In.');
      return;
    }

    // Acceptable outcome 2: signed in, but none of the platform-admin features.
    await page.goto('/tenants');
    await expect(
      page
        .getByText('Not available', { exact: true })
        .or(page.getByRole('alert'))
        .or(page.locator('#username')),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Tenant name', { exact: true })).toHaveCount(0);
    await expect(tenantsNav(page)).toHaveCount(0);
    await expect(tenantSelector(page)).toHaveCount(0);

    const response = await page.request.get('/v1.0/m8flow/tenants');
    expect(response.status()).not.toBe(200);

    console.log('[LGN-05b] Master account without the super-admin role logged in but gets no Platform Admin features.');
  });
});
