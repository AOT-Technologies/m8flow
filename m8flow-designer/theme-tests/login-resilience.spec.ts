import { expect, test, type Page } from '@playwright/test';

const keycloak = process.env.M8FLOW_KEYCLOAK_TEST_BASE_URL ?? 'http://localhost:16842';
const callback = `${keycloak}/callback`;

function loginUrl(realm: string, usernameOnly = false): string {
  const url = new URL(`/realms/${realm}/protocol/openid-connect/auth`, keycloak);
  url.search = new URLSearchParams({
    client_id: usernameOnly ? 'theme-username' : 'theme-test',
    redirect_uri: callback,
    response_type: 'code',
    scope: 'openid',
  }).toString();
  return url.href;
}

async function combinedForm(page: Page): Promise<void> {
  await expect(page.locator('#username')).toBeVisible();
  await expect(page.locator('#password')).toBeVisible();
  await expect(page.locator('#kc-login')).toBeVisible();
  await expect(page.locator('#m8f-hidden-username-login-fallback')).toBeHidden();
}

async function disruptScripts(page: Page, mode: 'delayed' | 'failed'): Promise<() => Promise<void>> {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  // Modules in template.ftl hold DOMContentLoaded, but must not hold recovery.
  await page.route('**/resources/**/js/**', async (route) => {
    if (mode === 'failed') {
      await route.abort('failed');
    } else {
      await gate;
      await route.continue();
    }
  });
  const elapsed = mode === 'delayed'
    ? new Promise<void>((resolve) => setTimeout(resolve, 10_000))
    : Promise.resolve();
  return async () => {
    await elapsed;
    release();
  };
}

for (const realm of ['m8flow', 'master']) {
  test(`${realm}: a pending recovery shows loading rather than an error`, async ({ page }) => {
    const challenge = await page.request.get(loginUrl(realm, true));
    const combined = await page.request.get(loginUrl(realm));
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    await page.route('**/login-actions/restart**', async (route) => {
      await gate;
      await route.fulfill({ response: combined });
    });
    await page.route('**/protocol/openid-connect/auth**', (route) => route.fulfill({ response: challenge }));
    try {
      await page.goto(loginUrl(realm), { waitUntil: 'commit' });
      // Locator assertions may wait for the pending navigation to finish.
      // Inspect the old document while the recovery response is held instead.
      await expect.poll(() => page.evaluate(() => {
        const status = document.getElementById('m8f-login-recovery-status');
        const fallback = document.getElementById('m8f-hidden-username-login-fallback');
        return { text: status?.textContent, loading: status?.hidden === false, errorHidden: fallback?.hidden };
      })).toEqual({ text: 'Preparing sign in\u2026', loading: true, errorHidden: true });
    } finally {
      release();
    }
    await combinedForm(page);
  });

  for (const mode of ['delayed', 'failed'] as const) {
    test(`${realm}: combined form stays usable with ${mode} theme scripts`, async ({ page }) => {
      const finish = await disruptScripts(page, mode);
      try {
        await page.goto(loginUrl(realm), { waitUntil: 'commit' });
        await combinedForm(page);
        await page.locator('#username').fill('theme-editor');
        await page.locator('#password').fill('theme-test-password');
        await expect(page.locator('#kc-login')).toBeEnabled();
        await Promise.all([
          page.waitForURL((url) => url.pathname === '/callback' && url.searchParams.has('code'), {
            waitUntil: 'commit',
          }),
          page.locator('#kc-login').click(),
        ]);
      } finally {
        await finish();
        await page.waitForLoadState('load');
      }
    });

    test(`${realm}: username-only challenge recovers automatically with ${mode} scripts`, async ({ page }) => {
      // Get a genuine server-rendered challenge from a fixture client bound to
      // a username-only test flow. The normal client keeps its combined flow.
      const challenge = await page.request.get(loginUrl(realm, true));
      expect(challenge.status()).toBe(200);
      expect(await challenge.text()).toContain('id="m8f-username-only-login"');
      const combined = await page.request.get(loginUrl(realm));
      let restarts = 0;
      await page.route('**/login-actions/restart**', async (route) => {
        restarts += 1;
        await route.fulfill({ response: combined });
      });
      await page.route('**/protocol/openid-connect/auth**', (route) => route.fulfill({ response: challenge }));
      const finish = await disruptScripts(page, mode);
      try {
        await page.goto(loginUrl(realm), { waitUntil: 'commit' }).catch((error: unknown) => {
          if (!/interrupted by another navigation|ERR_ABORTED/.test(String(error))) throw error;
        });
        // Must recover before the ten-second script delay is released.
        await expect(page.locator('#username')).toBeVisible({ timeout: 5_000 });
        await combinedForm(page);
        expect(restarts).toBe(1);
      } finally {
        await finish();
        await page.waitForLoadState('load');
      }
    });
  }

  test(`${realm}: repeated challenges stop after two restarts and manual Retry works`, async ({ page }) => {
    const response = await page.request.get(loginUrl(realm, true));
    const html = await response.text();
    let restarts = 0;
    await page.route('**/login-actions/restart**', async (route) => {
      restarts += 1;
      // Keep realm/client/tab stable while Keycloak's transient code changes.
      const body = html.replace(/(data-login-restart-url="[^"]*)"/g, `$1&amp;session_code=${restarts}"`);
      await route.fulfill({ response, body });
    });
    await page.route('**/protocol/openid-connect/auth**', (route) => route.fulfill({ response }));
    await page.goto(loginUrl(realm), { waitUntil: 'commit' }).catch((error: unknown) => {
      if (!/interrupted by another navigation|ERR_ABORTED/.test(String(error))) throw error;
    });
    await expect(page.getByRole('alert')).toContainText('Unable to open the sign-in form');
    await expect(page.getByRole('status')).toBeHidden();
    expect(restarts).toBe(2);
    const combined = await page.request.get(loginUrl(realm));
    await page.unroute('**/login-actions/restart**');
    await page.route('**/login-actions/restart**', (route) => route.fulfill({ response: combined }));
    await page.getByRole('link', { name: 'Retry', exact: true }).click();
    await combinedForm(page);
  });

  test(`${realm}: a blocked storage getter shows a usable Retry link`, async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, 'sessionStorage', {
        get: () => { throw new DOMException('Blocked', 'SecurityError'); },
      });
    });
    await page.goto(loginUrl(realm, true));
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Retry', exact: true })).toHaveAttribute('href', /login-actions\/restart/);
  });

  test(`${realm}: JavaScript-disabled browsers have a native Retry link`, async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    try {
      const page = await context.newPage();
      await page.goto(loginUrl(realm, true));
      await expect(page.locator('#m8f-return-to-full-sign-in-noscript')).toBeVisible();
      await expect(page.getByRole('status')).toBeHidden();
    } finally {
      await context.close();
    }
  });
}
