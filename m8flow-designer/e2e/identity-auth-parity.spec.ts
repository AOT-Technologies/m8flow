import { expect, test } from '@playwright/test';

import {
  cookieValue,
  clearDesignerSession,
  editorCredentials,
  expectCombinedKeycloakLoginPage,
  expectSharedRealmKeycloakLogin,
  logOutFromDesigner,
  SELECTED_TENANT_COOKIE,
  signInAsPlatformAdmin,
  signInAsSharedRealmUser,
  signInAtSharedRealm,
  superAdminCredentials,
} from './helpers/auth';
import {
  acceptInvitationApi,
  addTenantMember,
  createTenantInvitation,
  ensureSecondParityTenant,
  expectOnboardingAndTasks,
  getSeedTenant,
  invitationPassword,
  removeTenantMember,
  tokenFromInvitationLink,
  uniqueEmail,
} from './helpers/backendApi';
import { PARITY_SECOND_TENANT_SLUG, SEED_TENANT_LABEL } from './helpers/fixtures';

/**
 * Identity + Auth parity (ticket 06). Closed spec: PAR-01–07. Arrange
 * invitations/tenants/members via host APIs; act on the designer → backend →
 * Keycloak seam.
 */
test.describe('Identity + Auth parity', () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await signInAsPlatformAdmin(page, superAdminCredentials());
      const seed = await getSeedTenant(page);
      await addTenantMember(page, seed.id, editorCredentials().username, ['Designers']);
    } finally {
      await page.close();
    }
  });

  test('PAR-01: auto-redirect to shared-realm login and platform-admin switch', async ({
    page,
  }) => {
    await clearDesignerSession(page);
    await page.goto('/');
    await expectSharedRealmKeycloakLogin(page);
    await expectCombinedKeycloakLoginPage(page);

    await page.locator('#m8f-master-login-button').click();
    await page.waitForURL(/\/realms\/master\//, { timeout: 30_000 });
    await expectCombinedKeycloakLoginPage(page);
  });

  test('PAR-02: editor after tenant finalization can read onboarding and tasks', async ({
    page,
  }) => {
    const editor = editorCredentials();
    await signInAsSharedRealmUser(page, editor);
    await expectOnboardingAndTasks(page, { username: editor.username });
  });

  test('PAR-03: second organization picker then onboarding and tasks still succeed', async ({
    page,
  }) => {
    const password = invitationPassword();
    const email = uniqueEmail('e2e-multi-org');
    let secondTenantId: string | undefined;

    await signInAsPlatformAdmin(page, superAdminCredentials());
    const seedTenant = await getSeedTenant(page);
    const secondTenant = await ensureSecondParityTenant(page);
    secondTenantId = secondTenant.id;

    const invitation = await createTenantInvitation(page, seedTenant.id, email);
    await acceptInvitationApi(page, tokenFromInvitationLink(invitation.invitation_link!), password);
    await addTenantMember(page, secondTenant.id, email, ['Designers']);
    await logOutFromDesigner(page);

    try {
      await signInAtSharedRealm(page, { username: email, password });
      await expect(page.getByRole('heading', { name: 'Select a tenant', exact: true })).toBeVisible({
        timeout: 30_000,
      });
      // Options live in a closed Select portal until the trigger is opened.
      await page.getByTestId('tenant-select-trigger').click();
      await expect(page.getByTestId(`organization-option-${SEED_TENANT_LABEL}`)).toBeVisible();
      await expect(page.getByTestId(`organization-option-${PARITY_SECOND_TENANT_SLUG}`)).toBeVisible();

      await page.getByTestId(`organization-option-${PARITY_SECOND_TENANT_SLUG}`).click();
      await page.getByTestId('tenant-select-confirm-button').click();
      await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible({
        timeout: 60_000,
      });
      await expectOnboardingAndTasks(page, { username: email });
    } finally {
      await signInAsPlatformAdmin(page, superAdminCredentials());
      if (secondTenantId) {
        await removeTenantMember(page, secondTenantId, email);
      }
    }
  });

  test('PAR-04: zero-org user is blocked and can logout', async ({ page }) => {
    const password = invitationPassword();
    const email = uniqueEmail('e2e-zero-org');

    await signInAsPlatformAdmin(page, superAdminCredentials());
    const seedTenant = await getSeedTenant(page);
    const invitation = await createTenantInvitation(page, seedTenant.id, email);
    await acceptInvitationApi(page, tokenFromInvitationLink(invitation.invitation_link!), password);
    await removeTenantMember(page, seedTenant.id, email);
    await logOutFromDesigner(page);

    await signInAtSharedRealm(page, { username: email, password });
    await expect(page.getByTestId('no-tenant-access-message')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('heading', { name: 'Home', exact: true })).toHaveCount(0);

    await page.getByTestId('back-to-login-button').click();
    await expectSharedRealmKeycloakLogin(page, 60_000);
    expect(await cookieValue(page, SELECTED_TENANT_COOKIE)).toBeFalsy();
  });

  test('PAR-05: single-org user auto-finalizes with no picker', async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await expect(page.getByRole('heading', { name: 'Select a tenant', exact: true })).toHaveCount(0);
    await expect(page.getByTestId(`organization-option-${SEED_TENANT_LABEL}`)).toHaveCount(0);
    expect(await cookieValue(page, SELECTED_TENANT_COOKIE)).toBeTruthy();
  });

  test('PAR-06: logout clears session and localStorage cannot bypass the cookie gate', async ({
    page,
  }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    expect(await cookieValue(page, SELECTED_TENANT_COOKIE)).toBeTruthy();

    await logOutFromDesigner(page);
    expect(await cookieValue(page, 'access_token')).toBeFalsy();
    expect(await cookieValue(page, SELECTED_TENANT_COOKIE)).toBeFalsy();

    await page.evaluate(() => {
      window.localStorage.setItem('m8flow_global_selected_tenant', 'm8flow');
    });
    await page.goto('/processes');
    await expectSharedRealmKeycloakLogin(page);
    await expect(page.getByRole('heading', { name: 'Processes', exact: true })).toHaveCount(0);

    await signInAsSharedRealmUser(page, editorCredentials());
    const keep = (await page.context().cookies()).filter(
      (cookie) => cookie.name !== SELECTED_TENANT_COOKIE,
    );
    await page.context().clearCookies();
    await page.context().addCookies(keep);
    await page.evaluate(() => {
      window.localStorage.setItem('m8flow_global_selected_tenant', 'm8flow');
    });

    const finalization = page.waitForRequest(
      (request) => request.url().includes('tenant_finalization=1'),
      { timeout: 30_000 },
    );
    await page.goto('/');
    await finalization;
    await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible({
      timeout: 60_000,
    });
    expect(await cookieValue(page, SELECTED_TENANT_COOKIE)).toBeTruthy();
  });

  test('PAR-07: accept invitation then go to login and sign in', async ({ page }) => {
    const password = invitationPassword();
    const email = uniqueEmail('e2e-invite');

    await signInAsPlatformAdmin(page, superAdminCredentials());
    const seedTenant = await getSeedTenant(page);
    const invitation = await createTenantInvitation(page, seedTenant.id, email);
    const token = tokenFromInvitationLink(invitation.invitation_link!);
    await logOutFromDesigner(page);

    await page.goto(`/accept-invitation?token=${encodeURIComponent(token)}`);
    await expect(page.getByRole('heading', { name: 'Complete your registration' })).toBeVisible();
    await page.getByTestId('accept-invitation-password').fill(password);
    await page.getByTestId('accept-invitation-confirm-password').fill(password);
    await page.getByTestId('accept-invitation-submit').click();
    await expect(page.getByTestId('accept-invitation-go-login')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Home', exact: true })).toHaveCount(0);

    await page.getByTestId('accept-invitation-go-login').click();
    await expectSharedRealmKeycloakLogin(page);
    await expect(page.getByRole('heading', { name: 'Home', exact: true })).toHaveCount(0);

    await signInAsSharedRealmUser(page, { username: email, password });
    await expectOnboardingAndTasks(page, { username: email });
  });
});
