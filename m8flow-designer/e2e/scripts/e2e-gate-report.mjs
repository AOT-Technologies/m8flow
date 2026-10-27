#!/usr/bin/env node
// Applies the E2E gate criteria to one run and writes a short report.
//
// Usage (from m8flow-designer/):
//   node e2e/scripts/e2e-gate-report.mjs                      # newest run in e2e/reports
//   node e2e/scripts/e2e-gate-report.mjs --run <run id>       # a specific run
//   options: --selection <json file from select-e2e-tests>  --markdown <out file>
//            --summary <file, e.g. $GITHUB_STEP_SUMMARY>      --report-url <link to the report>
//
// Gate criteria (see e2e/README.md):
//   PASS  - every selected test passed, or was skipped with a reason
//   PASS* - passed only after a retry (flaky): allowed, but listed as a warning
//   FAIL  - any test failed or timed out, a global/setup error occurred,
//           tests were selected but none ran (e.g. the stack never came up),
//           or every test was skipped
// Exit code: 0 for PASS, 1 for FAIL.

import { appendFileSync, existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const reportsDir = resolve(here, '..', 'reports');

function arg(name) {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? undefined : process.argv[i + 1];
}

function newestRun() {
  if (!existsSync(reportsDir)) return undefined;
  return readdirSync(reportsDir)
    .filter((n) => statSync(join(reportsDir, n)).isDirectory())
    .sort()
    .at(-1);
}

const ANSI = /\u001b\[[0-9;]*m/g;
const firstLine = (s) => (s ?? '').replace(ANSI, '').split('\n').find((l) => l.trim())?.trim() ?? '';

const runId = arg('run') ?? process.env.E2E_RUN_ID ?? newestRun();
const resultsFile = runId ? join(reportsDir, runId, 'results.json') : undefined;
const selection = arg('selection') && existsSync(arg('selection'))
  ? JSON.parse(readFileSync(arg('selection'), 'utf-8'))
  : undefined;

const tests = [];
let globalErrors = [];
let duration = 0;
if (resultsFile && existsSync(resultsFile)) {
  const data = JSON.parse(readFileSync(resultsFile, 'utf-8'));
  globalErrors = (data.errors ?? []).map((e) => firstLine(e.message));
  duration = data.stats?.duration ?? 0;
  const walk = (suite) => {
    for (const spec of suite.specs ?? []) {
      for (const t of spec.tests ?? []) {
        const results = t.results ?? [];
        const last = results.at(-1) ?? {};
        const status =
          t.status === 'expected' ? 'passed'
          : t.status === 'flaky' ? 'flaky'
          : t.status === 'skipped' ? 'skipped'
          : 'failed';
        const skip = (t.annotations ?? []).find((a) => a.type === 'skip');
        tests.push({
          file: spec.file,
          title: spec.title,
          status,
          error: firstLine(last.error?.message ?? last.errors?.[0]?.message),
          skipReason: skip?.description ?? '',
        });
      }
    }
    (suite.suites ?? []).forEach(walk);
  };
  (data.suites ?? []).forEach(walk);
}

const count = (s) => tests.filter((t) => t.status === s).length;
const passed = count('passed');
const failed = count('failed');
const flaky = count('flaky');
const skipped = count('skipped');

const problems = [];
if (!resultsFile || !existsSync(resultsFile)) problems.push('No results.json found: the E2E run did not complete.');
if (globalErrors.length) problems.push(`Global/setup error: ${globalErrors[0]}`);
if (failed) problems.push(`${failed} test(s) failed.`);
if (resultsFile && existsSync(resultsFile) && tests.length === 0) problems.push('Tests were selected but none ran.');
if (tests.length > 0 && passed + flaky === 0 && failed === 0) problems.push('Every test was skipped, so nothing was actually verified.');
const pass = problems.length === 0;

const lines = [];
lines.push(`## E2E Gate: ${pass ? (flaky ? '✅ PASS (with flaky tests)' : '✅ PASS') : '❌ FAIL'}`);
lines.push('');
if (selection) {
  const scope = selection.mode === 'full' ? 'Full suite' : `Modules: ${selection.modules.join(', ')}`;
  lines.push(`**Scope:** ${scope}`);
  if (selection.uncovered?.length) {
    lines.push(`**Changed modules with no E2E coverage yet:** ${selection.uncovered.join(', ')}`);
  }
  lines.push('');
}
lines.push('| Passed | Failed | Flaky | Skipped | Total | Duration |');
lines.push('|---|---|---|---|---|---|');
lines.push(`| ${passed} | ${failed} | ${flaky} | ${skipped} | ${tests.length} | ${Math.round(duration / 1000)}s |`);
lines.push('');
if (problems.length) {
  lines.push('**Why the gate failed**');
  problems.forEach((p) => lines.push(`- ${p}`));
  lines.push('');
}
const failedTests = tests.filter((t) => t.status === 'failed');
if (failedTests.length) {
  lines.push('**Failed tests**');
  lines.push('');
  lines.push('| Spec | Test | Error |');
  lines.push('|---|---|---|');
  failedTests.forEach((t) => lines.push(`| ${t.file} | ${t.title} | ${t.error.replace(/\|/g, '\\|').slice(0, 200)} |`));
  lines.push('');
}
const flakyTests = tests.filter((t) => t.status === 'flaky');
if (flakyTests.length) {
  lines.push('**Flaky (passed on retry)**');
  flakyTests.forEach((t) => lines.push(`- ${t.file} › ${t.title}`));
  lines.push('');
}
const skippedTests = tests.filter((t) => t.status === 'skipped');
if (skippedTests.length) {
  lines.push(`<details><summary>Skipped tests (${skippedTests.length})</summary>`);
  lines.push('');
  skippedTests.forEach((t) => lines.push(`- ${t.file} › ${t.title}${t.skipReason ? ` — ${t.skipReason}` : ''}`));
  lines.push('');
  lines.push('</details>');
  lines.push('');
}
const reportUrl = arg('report-url');
if (reportUrl) lines.push(`Full report (screenshots, errors, results.json): ${reportUrl}`);
if (runId) lines.push(`Run: \`${runId}\``);

const markdown = lines.join('\n') + '\n';
process.stdout.write(markdown);
if (runId && existsSync(join(reportsDir, runId))) writeFileSync(join(reportsDir, runId, 'gate-summary.md'), markdown);
if (arg('markdown')) writeFileSync(arg('markdown'), markdown);
if (arg('summary')) appendFileSync(arg('summary'), markdown);
process.exit(pass ? 0 : 1);
