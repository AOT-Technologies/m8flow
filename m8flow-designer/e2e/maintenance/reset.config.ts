import { defineConfig, type PlaywrightTestConfig } from '@playwright/test';

import base from '../../playwright.config';

/**
 * Config for the E2E reset only (maintenance/reset-e2e-data.ts):
 *   npx playwright test -c e2e/maintenance/reset.config.ts
 * Same browser, base URL and dev server as the suite. Relative paths here are
 * resolved from this folder, so the dev server runs from m8flow-designer.
 */
const webServer = base.webServer as PlaywrightTestConfig['webServer'] & object;

export default defineConfig({
  ...base,
  testDir: '.',
  testMatch: 'reset-e2e-data.ts',
  testIgnore: [],
  retries: 0,
  reporter: [['list']],
  outputDir: '../reports/reset-artifacts',
  webServer: { ...webServer, cwd: '../..' } as PlaywrightTestConfig['webServer'],
});
