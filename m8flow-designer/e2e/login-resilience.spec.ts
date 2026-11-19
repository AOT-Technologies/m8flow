import { expect, test, type Page } from '@playwright/test';

import {
  editorCredentials,
  expectCombinedKeycloakLoginPage,
  gotoExpectingRedirect,
  signInAsSharedRealmUser,
} from './helpers/auth';
import { KEYCLOAK_BASE_URL } from './helpers/fixtures';

async function configureNetwork(page: Page, network: 'normal' | 'slow'): Promise<() => void> {
  if (network === 'normal') return () => undefined;
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  const appliedRules = new Set<string>();
  cdp.on('Network.requestWillBeSentExtraInfo', (event) => {
    if (event.appliedNetworkConditionsId) appliedRules.add(event.appliedNetworkConditionsId);
  });
  // Throttle authentication HTML/assets, including redirects between realms.
  // CI serves the designer through Vite: throttling its unbundled module graph
  // can exhaust the test before the browser even reaches Keycloak.
  const { ruleIds } = await cdp.send('Network.emulateNetworkConditionsByRule', {
    offline: false,
    matchedNetworkConditions: [
      {
        urlPattern: `${new URL(KEYCLOAK_BASE_URL).origin}/*`,
        latency: 400,
        downloadThroughput: 400_000 / 8,
        uploadThroughput: 400_000 / 8,
      },
    ],
  });
  return () => expect(appliedRules.has(ruleIds[0]), 'Keycloak requests used Slow 3G').toBe(true);
}

// Exercise the real designer -> host -> Keycloak -> host path. Standalone
// theme fixtures cannot detect a misconfigured or prematurely healthy realm.
for (const network of ['normal', 'slow'] as const) {
  test(`Login resilience: editor signs in on a ${network} network`, async ({ page }) => {
    test.setTimeout(180_000);
    const verifyNetwork = await configureNetwork(page, network);
    await signInAsSharedRealmUser(page, editorCredentials());
    for (const path of ['/v1.0/onboarding', '/v1.0/tasks']) {
      const response = await page.request.get(path);
      expect(response.status(), `${path} after ${network} sign-in`).toBe(200);
    }
    verifyNetwork();
  });

  test(`Login resilience: master realm has a combined form on a ${network} network`, async ({ page }) => {
    test.setTimeout(180_000);
    const verifyNetwork = await configureNetwork(page, network);
    await gotoExpectingRedirect(page, '/');
    await expectCombinedKeycloakLoginPage(page);
    await page.locator('#m8f-master-login-button').click();
    await expect(page).toHaveURL(/\/realms\/master\//);
    await expectCombinedKeycloakLoginPage(page);
    verifyNetwork();
  });
}
