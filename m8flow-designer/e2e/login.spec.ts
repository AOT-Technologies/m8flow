import { expect, test } from '@playwright/test';

import {
  editorCredentials,
  openProfileMenu,
  signInAsPlatformAdmin,
  signInAsSharedRealmUser,
  superAdminCredentials,
} from './helpers/auth';

/**
 * CHK-01 / CHK-02 — designer login journeys through the live
 * designer → backend → Keycloak seam.
 */
test.describe('m8flow-designer login journeys', () => {
  test('CHK-01: shared-realm editor lands on Home without platform-admin chrome', async ({
    page,
  }) => {
    const editor = editorCredentials();

    await signInAsSharedRealmUser(page, editor);

    await openProfileMenu(page);
    await expect(page.getByRole('menu', { name: 'Profile' })).toContainText(editor.username);

    // Non–platform-admin: no All Tenants selector, no Total tenants KPI.
    await expect(page.getByRole('combobox', { name: /Tenant/ })).toHaveCount(0);
    await expect(page.getByText('Total tenants', { exact: true })).toHaveCount(0);

    // Home stats loaded (not a tenant-cookie 400 alert).
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByText('Active process instances', { exact: true })).toBeVisible();
  });

  test('CHK-02: master-realm super-admin lands with All Tenants scope', async ({
    page,
  }) => {
    const admin = superAdminCredentials();

    await signInAsPlatformAdmin(page, admin);

    await openProfileMenu(page);
    await expect(page.getByRole('menu', { name: 'Profile' })).toContainText(admin.username);
    await page.keyboard.press('Escape');

    // Default landing is /tenants; Home still exposes All-Tenants chrome.
    await page.getByRole('link', { name: 'Home', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible({
      timeout: 30_000,
    });

    const tenantSelect = page.getByRole('combobox', { name: /Tenant/ });
    await expect(tenantSelect).toBeVisible();
    await expect(tenantSelect).toHaveValue('');
    await expect(tenantSelect.locator('option').first()).toHaveText('All Tenants');

    await expect(page.getByText('Total tenants', { exact: true })).toBeVisible();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByText('Active process instances', { exact: true })).toBeVisible();
  });
});
