import { expect, test } from '@playwright/test';

import {
  clearDesignerSession,
  cookieValue,
  editorCredentials,
  expectCombinedKeycloakLoginPage,
  expectSharedRealmKeycloakLogin,
  gotoExpectingRedirect,
  integratorCredentials,
  logOutFromDesigner,
  SELECTED_TENANT_COOKIE,
  signInAsSharedRealmUser,
  signInAtSharedRealm,
  superAdminCredentials,
  useSession,
} from './helpers/auth';
import {
  acceptInvitationApi,
  addTenantMember,
  cleanupInvitedUser,
  cleanupLeftoverMockUsers,
  createTenantInvitation,
  ensureSecondParityTenant,
  expectOnboardingAndTasks,
  getSeedTenant,
  invitationPassword,
  removeTenantMember,
  tokenFromInvitationLink,
  uniqueEmail,
} from './helpers/backendApi';
import { PARITY_SECOND_TENANT_SLUG, SEED_TENANT_SLUG } from './helpers/fixtures';

/**
 * Identity + Auth parity (ticket 06). Closed spec: PAR-01–07. Arrange
 * invitations/tenants/members via host APIs; act on the designer → backend →
 * Keycloak seam.
 */
test.describe('Login, tenants and invitations', () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    try {
      await useSession(page, superAdminCredentials(), 'platformAdmin');
      const seed = await getSeedTenant(page);
      await addTenantMember(page, seed.id, editorCredentials().username, ['Designers']);
      // Remove mock users/invitations left behind by earlier interrupted runs.
      await cleanupLeftoverMockUsers(page, seed.id);
    } finally {
      await page.close();
    }
  });

  test('PAR-01: A logged-out user is sent to the login page, and Platform Admin Sign In opens the admin login', async ({
    page,
  }) => {
    await clearDesignerSession(page);
    await gotoExpectingRedirect(page, '/');
    await expectSharedRealmKeycloakLogin(page);
    await expectCombinedKeycloakLoginPage(page);

    await page.locator('#m8f-master-login-button').click();
    await page.waitForURL(/\/realms\/master\//, { timeout: 30_000 });
    await expectCombinedKeycloakLoginPage(page);
    console.log('[PAR-01] Logged-out user was sent to the login page; Platform Admin Sign In opened the admin login.');
  });

  test('PAR-02: An editor can log in and see their onboarding and tasks', async ({
    page,
  }) => {
    const editor = editorCredentials();
    await signInAsSharedRealmUser(page, editor);
    await expectOnboardingAndTasks(page, { username: editor.username });
    console.log('[PAR-02] Editor logged in and can see their onboarding and tasks.');
  });

  test('PAR-03: A user in two tenants picks a tenant after login and continues to Home', async ({
    page,
  }) => {
    // The tenant selection dropdown only appears when the same user belongs to
    // more than one tenant. The existing seed `integrator` user stays in its
    // original tenant (m8flow) and is ADDED to a second tenant, so it belongs
    // to two tenants at login.
    // Group 'Designers' (editor role) in the second tenant so /v1.0/tasks is
    // readable there; integrator itself has no task read in m8flow.
    const integrator = integratorCredentials();
    let secondTenantId: string | undefined;

    // 1. Super admin adds the existing integrator user to a new tenant
    //    (integrator is NOT removed from m8flow).
    await useSession(page, superAdminCredentials(), 'platformAdmin');
    const secondTenant = await ensureSecondParityTenant(page);
    secondTenantId = secondTenant.id;
    await addTenantMember(page, secondTenant.id, integrator.username, ['Designers']);
    // No logout needed: signing in as integrator starts from a cleared session,
    // and keeping the super-admin session alive lets later tests reuse it.

    try {
      // 2-3. Log in as integrator: the tenant selection dropdown is shown and
      //      lists both tenants (original m8flow + the new tenant).
      await signInAtSharedRealm(page, integrator);
      await expect(page.getByRole('heading', { name: /^Select a tenant$/i })).toBeVisible({
        timeout: 30_000,
      });
      const tenantDropdown = page.getByTestId('tenant-select-trigger');
      await expect(tenantDropdown).toBeVisible();
      // Options live in a closed Select portal until the trigger is opened.
      await tenantDropdown.click();
      await expect(page.getByTestId(`organization-option-${SEED_TENANT_SLUG}`)).toBeVisible();
      await expect(page.getByTestId(`organization-option-${PARITY_SECOND_TENANT_SLUG}`)).toBeVisible();

      // 4. Select a tenant and continue: Home loads in that tenant.
      await page.getByTestId(`organization-option-${PARITY_SECOND_TENANT_SLUG}`).click();
      await page.getByTestId('tenant-select-confirm-button').click();
      await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible({
        timeout: 60_000,
      });
      await expectOnboardingAndTasks(page, { username: integrator.username });
    } finally {
      // Undo only the membership this test added (the new tenant). Integrator
      // keeps its original m8flow membership, so other specs that log in as
      // integrator still land directly on Home without the picker.
      await useSession(page, superAdminCredentials(), 'platformAdmin');
      if (secondTenantId) {
        await removeTenantMember(page, secondTenantId, integrator.username);
      }
    }
    console.log('[PAR-03] Integrator belongs to two tenants: the tenant selection dropdown was shown, a tenant was selected, and the user continued to Home successfully.');
  });

  test('PAR-04: A user with no tenant cannot open Home and can log out', async ({ page }) => {
    const password = invitationPassword();
    const email = uniqueEmail('e2e-zero-org');

    await useSession(page, superAdminCredentials(), 'platformAdmin');
    const seedTenant = await getSeedTenant(page);
    try {
      const invitation = await createTenantInvitation(page, seedTenant.id, email);
      await acceptInvitationApi(page, tokenFromInvitationLink(invitation.invitation_link!), password);
      await removeTenantMember(page, seedTenant.id, email);
      // No logout needed: signInAtSharedRealm starts from a cleared session.

      await signInAtSharedRealm(page, { username: email, password });
      await expect(page.getByTestId('no-tenant-access-message')).toBeVisible({ timeout: 30_000 });
      await expect(page.getByRole('heading', { name: 'Home', exact: true })).toHaveCount(0);

      await page.getByTestId('back-to-login-button').click();
      await expectSharedRealmKeycloakLogin(page, 60_000);
      expect(await cookieValue(page, SELECTED_TENANT_COOKIE)).toBeFalsy();
    } finally {
      // Delete the mock user so repeated runs leave no test data behind.
      await useSession(page, superAdminCredentials(), 'platformAdmin');
      await cleanupInvitedUser(page, seedTenant.id, email);
    }
    console.log('[PAR-04] User with no tenant is blocked from Home and can go back to the login page.');
  });

  test('PAR-05: A user in one tenant goes straight to Home without picking a tenant', async ({ page }) => {
    await signInAsSharedRealmUser(page, editorCredentials());
    await expect(page.getByRole('heading', { name: /^Select a tenant$/i })).toHaveCount(0);
    await expect(page.getByTestId(`organization-option-${SEED_TENANT_SLUG}`)).toHaveCount(0);
    expect(await cookieValue(page, SELECTED_TENANT_COOKIE)).toBeTruthy();
    console.log('[PAR-05] Editor in one tenant went straight to Home without picking a tenant.');
  });

  test('PAR-06: Logging out ends the session, and the app cannot be reopened without logging in again', async ({
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
    await gotoExpectingRedirect(page, '/');
    await finalization;
    await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible({
      timeout: 60_000,
    });
    expect(await cookieValue(page, SELECTED_TENANT_COOKIE)).toBeTruthy();
    console.log('[PAR-06] Logout ended the session; the app asked to log in again.');
  });

  test('PAR-07: An invited user accepts the invitation and logs in', async ({
    page,
    browser,
  }) => {
    // Mock invitee: e2e-invite-<unique>@example.test (reserved domain, no real
    // mailbox). With SMTP not configured, M8Flow shows the invitation URL in
    // the dialog instead of e-mailing it.
    const email = uniqueEmail('e2e-invite');
    const password = invitationPassword();

    await useSession(page, superAdminCredentials(), 'platformAdmin');
    const seedTenant = await getSeedTenant(page);
    const inviteeContext = await browser.newContext();

    try {
      // 1. Enter the test e-mail, send the invitation, copy the invitation URL.
      await page.goto(`/tenant-management/${encodeURIComponent(seedTenant.id)}`);
      await page.getByTestId('tenant-invite-user-button').click();
      await page.getByTestId('invite-user-email-input').fill(email);
      await page.getByTestId('invite-user-role-editor').click();
      await page.getByTestId('invite-user-submit').click();

      const linkField = page.getByTestId('invite-user-dev-link');
      await expect(linkField).toBeVisible({ timeout: 30_000 });
      await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
      await page.getByTestId('invite-copy-link').click();
      await expect(page.getByTestId('invite-copy-link')).toContainText('Copied');
      const invitationUrl = await linkField.inputValue();
      expect(invitationUrl).toContain('/accept-invitation?token=');

      // 2. Open the invitation link in a new tab (separate, logged-out session).
      const inviteTab = await inviteeContext.newPage();
      await inviteTab.goto(invitationUrl);
      await expect(inviteTab.getByRole('heading', { name: 'Complete your registration' })).toBeVisible();

      // 3. Set a password and confirm it.
      await inviteTab.getByTestId('accept-invitation-password').fill(password);
      await inviteTab.getByTestId('accept-invitation-confirm-password').fill(password);
      await inviteTab.getByTestId('accept-invitation-submit').click();
      await expect(inviteTab.getByTestId('accept-invitation-go-login')).toBeVisible();
      await expect(inviteTab.getByRole('heading', { name: 'Home', exact: true })).toHaveCount(0);

      // 4. Log in with the invited account.
      await inviteTab.getByTestId('accept-invitation-go-login').click();
      await expectSharedRealmKeycloakLogin(inviteTab);
      await signInAsSharedRealmUser(inviteTab, { username: email, password });
      await expectOnboardingAndTasks(inviteTab, { username: email });
    } finally {
      await inviteeContext.close();
      // Delete the mock user so repeated runs leave no test data behind.
      await cleanupInvitedUser(page, seedTenant.id, email);
    }
    console.log(`[PAR-07] Invitation sent to ${email}, accepted in a new tab, and the invited user logged in successfully; test user removed.`);
  });
});
