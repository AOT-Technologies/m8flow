#!/usr/bin/env node
// Repeatable build-size report: walks dist/, prints raw/gzip/brotli size per
// output file (biggest first) plus totals by extension. This is the tool
// every performance-track ticket in the m8flow-designer optimization map
// (.scratch/m8flow-designer-optimization/map.md) uses for its required
// before/after comparison — build once here (ticket 01: bundle-and-component
// audit), reused by every ticket after it, so it's never rebuilt per-ticket.
//
// Usage: npm run build && npm run build:report
// Optionally writes machine-readable output too: npm run build:report -- --json > report.json

import { readdirSync, statSync, readFileSync } from 'node:fs';
import { join, extname, relative } from 'node:path';
import { gzipSync, brotliCompressSync } from 'node:zlib';

const DIST_DIR = join(import.meta.dirname, '..', 'dist');
const asJson = process.argv.includes('--json');

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walk(full));
    } else {
      out.push(full);
    }
  }
  return out;
}

function fmtKb(bytes) {
  return `${(bytes / 1024).toFixed(2)} KB`;
}

let files;
try {
  files = walk(DIST_DIR);
} catch (err) {
  console.error(`No dist/ found at ${DIST_DIR} — run "npm run build" first.`);
  process.exit(1);
}

const rows = files
  // .gz/.br are compressed-output-ticket's own artifacts (see ticket 03) —
  // measuring their raw size against themselves would be meaningless, and
  // their whole point is captured by measuring the uncompressed original.
  // stats.html is the bundle-analyzer's own dev-time report (only produced
  // by `npm run build:analyze`, never shipped) — including its ~1.8 MB of
  // inlined module-graph data would swamp every real number below.
  .filter((f) => !f.endsWith('.gz') && !f.endsWith('.br') && !f.endsWith('stats.html'))
  .map((f) => {
    const raw = readFileSync(f);
    return {
      file: relative(DIST_DIR, f),
      ext: extname(f) || '(none)',
      raw: raw.length,
      gzip: gzipSync(raw, { level: 9 }).length,
      brotli: brotliCompressSync(raw).length,
    };
  })
  .sort((a, b) => b.raw - a.raw);

const totals = { raw: 0, gzip: 0, brotli: 0 };
const byExt = new Map();
for (const row of rows) {
  totals.raw += row.raw;
  totals.gzip += row.gzip;
  totals.brotli += row.brotli;
  const bucket = byExt.get(row.ext) ?? { raw: 0, gzip: 0, brotli: 0, count: 0 };
  bucket.raw += row.raw;
  bucket.gzip += row.gzip;
  bucket.brotli += row.brotli;
  bucket.count += 1;
  byExt.set(row.ext, bucket);
}

if (asJson) {
  // Deliberately no `process.exit(0)` here (there used to be one). When
  // stdout is a pipe rather than a TTY — exactly what `execFileSync`
  // gives a caller like check-initial-load-budget.mjs — Node writes it
  // asynchronously; a big single `console.log` (this repo's dist/ output
  // is easily >8KB of JSON) can still be draining when `process.exit()`
  // tears the process down, truncating the pipe mid-write. The reader
  // then sees a cut-off JSON string and `JSON.parse` throws. Reproduced
  // directly: calling this script via `execFileSync` failed consistently
  // with "Unexpected end of JSON input" while piping the same command to
  // a file in a shell always succeeded (the shell redirect doesn't hit
  // this race the same way execFileSync's pipe does). Letting the script
  // exit naturally — nothing else is scheduled once this branch finishes,
  // so the process ends as soon as the event loop drains, after the write
  // completes — fixes it without needing an artificial delay or a sync
  // write API.
  console.log(JSON.stringify({ files: rows, totals, byExt: Object.fromEntries(byExt) }, null, 2));
} else {
  console.log(`\nBundle size report — ${DIST_DIR}\n`);
  console.log('Per-file (largest first):');
  for (const row of rows) {
    console.log(
      `  ${row.file.padEnd(60)} raw ${fmtKb(row.raw).padStart(11)}  gzip ${fmtKb(row.gzip).padStart(11)}  brotli ${fmtKb(row.brotli).padStart(11)}`,
    );
  }

  console.log('\nBy extension:');
  for (const [ext, bucket] of [...byExt.entries()].sort((a, b) => b[1].raw - a[1].raw)) {
    console.log(
      `  ${ext.padEnd(10)} (${bucket.count} file${bucket.count === 1 ? '' : 's'})  raw ${fmtKb(bucket.raw).padStart(11)}  gzip ${fmtKb(bucket.gzip).padStart(11)}  brotli ${fmtKb(bucket.brotli).padStart(11)}`,
    );
  }

  console.log('\nTotals:');
  console.log(`  raw ${fmtKb(totals.raw)}  gzip ${fmtKb(totals.gzip)}  brotli ${fmtKb(totals.brotli)}\n`);
}
