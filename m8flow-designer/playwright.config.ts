import { defineConfig, devices } from '@playwright/test';

const designerBaseUrl = process.env.M8FLOW_DESIGNER_BASE_URL ?? 'http://localhost:6853';

/**
 * Every run saves only what is needed, under e2e/reports/<run id>/:
 *   results.json   result + error of every test in the suite
 *   artifacts/     FAILED tests only: full-page screenshot + error-context.md
 *   report.html    report of the run (built by scripts/e2e-dashboard.mjs)
 * No video or trace is recorded. scripts/e2e-run.mjs removes any other file
 * Playwright drops into artifacts/.
 * The run id is fixed once here and inherited by the worker processes
 * through process.env, so every worker writes into the same folder.
 */
if (!process.env.E2E_RUN_ID) {
  // Local time, e.g. 2026-10-14_15-42-07 (sorts chronologically).
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  process.env.E2E_RUN_ID =
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_` +
    `${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;
}
const runDir = `e2e/reports/${process.env.E2E_RUN_ID}`;

export default defineConfig({
  testDir: './e2e',
  // Run reports live in e2e/reports/; never treat them as tests.
  testIgnore: ['**/reports/**'],
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  outputDir: `${runDir}/artifacts`,
  reporter: [
    ['list'],
    ['json', { outputFile: `${runDir}/results.json` }],
  ],
  timeout: 90_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: designerBaseUrl,
    trace: 'off',
    screenshot: { mode: 'only-on-failure', fullPage: true },
    video: 'off',
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
