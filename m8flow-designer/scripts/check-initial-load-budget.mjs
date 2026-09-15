#!/usr/bin/env node
// CI gate for the initial-load bundle-size budget decided in
// .scratch/m8flow-designer-optimization/issues/07-derive-bundle-size-budgets.md:
// the combined gzip size of the main entry chunk + `vendor-react` +
// `vendor-ui` (everything a user's first paint pays for, before any route
// lazy-loads) must stay under 150 KB gzip. Reuses report-bundle-size.mjs's
// own gzip computation (spawned with --json) rather than re-implementing
// it, so the two scripts can't silently drift apart.
//
// Usage: npm run build && npm run check:initial-load-budget
//
// Deliberately does NOT cover the modeler-route chunks (BpmnCanvas/
// DmnCanvas/properties-panel-fields/EditorDialog) — ticket 07 decided
// those stay "track, don't gate", not a CI-enforced ceiling.

import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const BUDGET_GZIP_BYTES = 150 * 1024;

// Matches the three chunk-name prefixes ticket 06's `manualChunks` and
// Vite's own default main-entry naming produce. `.js` only — `index-*.css`
// (the app's stylesheet) is a separate, un-budgeted asset; ticket 07's
// number was computed from JS chunks only, so silently folding CSS in here
// would change what's being enforced without a new decision.
const INITIAL_LOAD_PATTERN = /^assets\/(index|vendor-react|vendor-ui)-[^/]+\.js$/;

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const reportScript = path.join(scriptDir, 'report-bundle-size.mjs');

let report;
try {
  const stdout = execFileSync(process.execPath, [reportScript, '--json'], { encoding: 'utf8' });
  report = JSON.parse(stdout);
} catch (err) {
  console.error('Failed to run report-bundle-size.mjs --json:', err.message);
  process.exit(1);
}

const matched = report.files.filter((f) => INITIAL_LOAD_PATTERN.test(f.file));

if (matched.length === 0) {
  console.error(
    `No files matched ${INITIAL_LOAD_PATTERN} in the build output — the chunk-naming ` +
      'convention ticket 06 established may have changed. Not silently passing: fix this ' +
      'pattern (or investigate why the expected chunks are missing) before trusting this gate.',
  );
  process.exit(1);
}

const totalGzip = matched.reduce((sum, f) => sum + f.gzip, 0);
const fmtKb = (bytes) => `${(bytes / 1024).toFixed(2)} KB`;

console.log('Initial-load budget check:');
for (const f of matched) {
  console.log(`  ${f.file.padEnd(40)} gzip ${fmtKb(f.gzip)}`);
}
console.log(`  ${'total'.padEnd(40)} gzip ${fmtKb(totalGzip)} (budget: ${fmtKb(BUDGET_GZIP_BYTES)})`);

if (totalGzip > BUDGET_GZIP_BYTES) {
  console.error(
    `\nInitial-load budget exceeded: ${fmtKb(totalGzip)} > ${fmtKb(BUDGET_GZIP_BYTES)}. ` +
      'See .scratch/m8flow-designer-optimization/issues/07-derive-bundle-size-budgets.md.',
  );
  process.exit(1);
}

console.log('\nWithin budget.');
