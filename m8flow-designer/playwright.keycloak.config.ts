import { defineConfig, devices } from '@playwright/test';

// Standalone theme tests: no designer/backend server or production realm needed.
// See theme-tests/README.md for the disposable Keycloak fixture.
export default defineConfig({
  testDir: './theme-tests',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 20_000 },
  outputDir: './e2e/reports/keycloak-theme/artifacts',
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    channel: process.env.PLAYWRIGHT_CHANNEL,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
