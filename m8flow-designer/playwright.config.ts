import { defineConfig, devices } from '@playwright/test';

const designerBaseUrl = process.env.M8FLOW_DESIGNER_BASE_URL ?? 'http://localhost:6853';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  timeout: 90_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: designerBaseUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: designerBaseUrl,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
