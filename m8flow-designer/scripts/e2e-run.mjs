#!/usr/bin/env node
// Runs the Playwright e2e suite and saves the results as a new run folder:
//   e2e/reports/<YYYY-MM-DD_HH-mm-ss>/report.html         report of this run
//   e2e/reports/<YYYY-MM-DD_HH-mm-ss>/results.json        every test's result + errors
//   e2e/reports/<YYYY-MM-DD_HH-mm-ss>/artifacts/<test>/   failed tests only: screenshot
//                                                         + error-context.md (page snapshot)
// Everything else Playwright writes into artifacts/ is removed, then the
// dashboard over all runs (e2e/reports/index.html) is rebuilt.
//
// Usage (any Playwright args pass through):
//   npm run test:e2e
//   npm run test:e2e -- e2e/login.spec.ts
//   npm run test:e2e -- -g "CHK-08" --headed
// Optional env:
//   E2E_REPORT_KEEP=30   keep only the newest 30 run folders
//   E2E_RUN_ID=my-label  name the run folder yourself

import { spawnSync } from 'node:child_process';
import { readdirSync, rmSync, existsSync, statSync } from 'node:fs';
import { extname, join, resolve } from 'node:path';

import { buildDashboard, REPORTS_DIR } from './e2e-dashboard.mjs';

const pad = (n) => String(n).padStart(2, '0');
const d = new Date();
const runId = process.env.E2E_RUN_ID ||
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}-${pad(d.getMinutes())}-${pad(d.getSeconds())}`;

const cli = resolve(import.meta.dirname, '..', 'node_modules', '@playwright', 'test', 'cli.js');
const result = spawnSync(process.execPath, [cli, 'test', ...process.argv.slice(2)], {
  stdio: 'inherit',
  cwd: resolve(import.meta.dirname, '..'),
  env: { ...process.env, E2E_RUN_ID: runId },
});

// Keep only failure screenshots and error-context.md: drop any other file
// (.last-run.json, ...) and any folder left empty (passed tests).
const KEEP = new Set(['.png', '.jpg', '.jpeg', '.md']);
function pruneArtifacts(dir) {
  if (!existsSync(dir)) return;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      pruneArtifacts(full);
      if (!readdirSync(full).length) rmSync(full, { recursive: true, force: true });
    } else if (!KEEP.has(extname(entry.name).toLowerCase())) {
      rmSync(full, { force: true });
    }
  }
}
pruneArtifacts(join(REPORTS_DIR, runId, 'artifacts'));

const keep = Number(process.env.E2E_REPORT_KEEP ?? 0);
if (keep > 0 && existsSync(REPORTS_DIR)) {
  const dirs = readdirSync(REPORTS_DIR)
    .filter((n) => statSync(join(REPORTS_DIR, n)).isDirectory())
    .sort();
  for (const old of dirs.slice(0, Math.max(0, dirs.length - keep))) {
    rmSync(join(REPORTS_DIR, old), { recursive: true, force: true });
  }
}

const { file } = buildDashboard();
console.log(`\nRun report: e2e/reports/${runId}/report.html`);
console.log(`Dashboard:  ${file}`);
console.log('Open either file in a browser, or run: npm run test:e2e:dashboard');

process.exit(result.status ?? 1);
