#!/usr/bin/env node
// Builds, from every saved run (e2e/reports/<run id>/results.json):
//   e2e/reports/index.html             dashboard over all runs (KPIs, trend,
//                                      run history, test cases)
//   e2e/reports/<run id>/report.html   report of that one run (KPIs, test
//                                      cases, errors, failure screenshots)
// Both are static files: open them directly in a browser.
//
// Usage:
//   node scripts/e2e-dashboard.mjs            rebuild the reports
//   node scripts/e2e-dashboard.mjs --serve    rebuild, then also serve e2e/reports/
//                                             on http://localhost:9323

import { createServer } from 'node:http';
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync, createReadStream } from 'node:fs';
import { join, relative, extname, resolve, sep } from 'node:path';

export const REPORTS_DIR = resolve(import.meta.dirname, '..', 'e2e', 'reports');

const ANSI = /\u001b\[[0-9;]*m/g;
const strip = (s) => (s ?? '').replace(ANSI, '');
const rel = (p) => relative(REPORTS_DIR, p).split(sep).join('/');

function collectSpecs(suite, file, out) {
  for (const spec of suite.specs ?? []) {
    for (const test of spec.tests ?? []) {
      const results = test.results ?? [];
      const last = results.at(-1) ?? {};
      const attachments = results.flatMap((r) => r.attachments ?? []).filter((a) => a.path && existsSync(a.path));
      const errors = results.flatMap((r) => r.errors?.length ? r.errors : r.error ? [r.error] : []);
      const status =
        test.status === 'expected' ? 'passed'
        : test.status === 'unexpected' ? 'failed'
        : test.status === 'flaky' ? 'flaky'
        : 'skipped';
      out.push({
        id: spec.id,
        caseId: (spec.title.match(/^([A-Z]+-\d+)/) ?? [])[1] ?? '',
        title: spec.title,
        suite: suite.title !== file ? suite.title : '',
        file,
        line: spec.line,
        project: test.projectName,
        status,
        duration: results.reduce((s, r) => s + (r.duration ?? 0), 0),
        retries: Math.max(0, results.length - 1),
        error: errors.map((e) => strip(e.message || e.value || '')).filter(Boolean).join('\n\n'),
        stack: strip(errors.find((e) => e.stack)?.stack ?? ''),
        location: last.errorLocation ? `${last.errorLocation.file?.split(/[\\/]/).pop()}:${last.errorLocation.line}` : '',
        screenshots: attachments.filter((a) => a.contentType?.startsWith('image/')).map((a) => rel(a.path)),
        errorContext: attachments
          .filter((a) => a.name === 'error-context')
          .map((a) => readFileSync(a.path, 'utf-8').slice(0, 20000))
          .join('\n'),
      });
    }
  }
  for (const child of suite.suites ?? []) collectSpecs(child, file, out);
}

export function loadRuns() {
  if (!existsSync(REPORTS_DIR)) return [];
  const runs = [];
  for (const id of readdirSync(REPORTS_DIR).sort()) {
    const dir = join(REPORTS_DIR, id);
    const json = join(dir, 'results.json');
    if (!statSync(dir).isDirectory() || !existsSync(json)) continue;
    let report;
    try {
      report = JSON.parse(readFileSync(json, 'utf-8'));
    } catch {
      continue;
    }
    const tests = [];
    for (const suite of report.suites ?? []) collectSpecs(suite, suite.file ?? suite.title, tests);
    const count = (s) => tests.filter((t) => t.status === s).length;
    runs.push({
      id,
      startTime: report.stats?.startTime ?? null,
      duration: report.stats?.duration ?? 0,
      total: tests.length,
      passed: count('passed'),
      failed: count('failed'),
      flaky: count('flaky'),
      skipped: count('skipped'),
      globalErrors: (report.errors ?? []).map((e) => strip(e.message)),
      report: `${id}/report.html`,
      tests,
    });
  }
  return runs;
}

function render(template, payload) {
  const data = JSON.stringify({ generatedAt: new Date().toISOString(), ...payload }).replace(/</g, '\\u003c');
  return template.replace('/*__E2E_DATA__*/null', () => data);
}

export function buildDashboard() {
  const runs = loadRuns();
  const template = readFileSync(join(import.meta.dirname, 'e2e-dashboard.template.html'), 'utf-8');
  writeFileSync(join(REPORTS_DIR, 'index.html'), render(template, { single: false, runs }));
  // Per-run report: same page, one run, paths rebased onto the run folder.
  for (const run of runs) {
    const prefix = `${run.id}/`;
    const strip = (p) => (p.startsWith(prefix) ? p.slice(prefix.length) : p);
    const local = { ...run, report: null, tests: run.tests.map((t) => ({ ...t, screenshots: t.screenshots.map(strip) })) };
    writeFileSync(join(REPORTS_DIR, run.id, 'report.html'), render(template, { single: true, runs: [local] }));
  }
  return { runs, file: join(REPORTS_DIR, 'index.html') };
}

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.webm': 'video/webm', '.zip': 'application/zip', '.xml': 'application/xml',
  '.txt': 'text/plain; charset=utf-8', '.md': 'text/markdown; charset=utf-8',
};

export function serve(port = Number(process.env.E2E_REPORT_PORT ?? 9323)) {
  const server = createServer((req, res) => {
    const urlPath = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    let file = resolve(REPORTS_DIR, '.' + urlPath);
    if (!file.startsWith(REPORTS_DIR)) { res.writeHead(403).end(); return; }
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html');
    if (!existsSync(file)) { res.writeHead(404).end('Not found'); return; }
    res.writeHead(200, { 'Content-Type': MIME[extname(file).toLowerCase()] ?? 'application/octet-stream' });
    createReadStream(file).pipe(res);
  });
  server.listen(port, () => console.log(`E2E dashboard: http://localhost:${port}/  (Ctrl+C to stop)`));
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(import.meta.filename)) {
  const { runs, file } = buildDashboard();
  console.log(`E2E dashboard rebuilt from ${runs.length} run(s): ${file}`);
  if (process.argv.includes('--serve')) serve();
}
