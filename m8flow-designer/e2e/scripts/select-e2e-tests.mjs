#!/usr/bin/env node
// Decides which E2E specs a change needs, using e2e/modules.json.
//
// Usage (from m8flow-designer/ or the repo root):
//   node e2e/scripts/select-e2e-tests.mjs --base origin/refactor/next-gen   # diff base...HEAD
//   node e2e/scripts/select-e2e-tests.mjs --files "path/a.ts path/b.tsx"   # explicit list
//   node e2e/scripts/select-e2e-tests.mjs --full                           # whole suite
//   node e2e/scripts/select-e2e-tests.mjs --modules auth,processes         # chosen modules
// Add --github-output to write run/mode/specs/modules to $GITHUB_OUTPUT.
//
// Rules, in order, for each changed file:
//   1. matches "ignore"      -> no E2E needed for that file
//   2. matches "fullSuite"   -> run every spec
//   3. matches a module      -> run that module's specs
//   4. other file under m8flow-designer/src or m8flow-backend/src -> full suite (safe default)
//   5. anything else         -> no E2E needed
// Modules without specs yet are reported as "no E2E coverage yet" (not blocking).

import { execSync } from 'node:child_process';
import { appendFileSync, existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(readFileSync(resolve(here, '..', 'modules.json'), 'utf-8'));

function arg(name) {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1) return undefined;
  const value = process.argv[i + 1];
  return value && !value.startsWith('--') ? value : '';
}
const has = (name) => process.argv.includes(`--${name}`);

/**
 * Minimal glob matcher, without building a RegExp from the pattern:
 *   ** (a whole path segment) = zero or more segments
 *   *  (inside a segment)     = any characters within that one segment
 */
function matchSegment(pattern, text) {
  // Iterative wildcard match with single-star backtracking: linear-ish, no regex.
  let p = 0;
  let t = 0;
  let star = -1;
  let mark = 0;
  while (t < text.length) {
    if (p < pattern.length && pattern[p] !== '*' && pattern[p] === text[t]) {
      p += 1;
      t += 1;
    } else if (p < pattern.length && pattern[p] === '*') {
      star = p;
      mark = t;
      p += 1;
    } else if (star !== -1) {
      p = star + 1;
      mark += 1;
      t = mark;
    } else {
      return false;
    }
  }
  while (p < pattern.length && pattern[p] === '*') p += 1;
  return p === pattern.length;
}

function globMatch(glob, file) {
  const pat = glob.split('/');
  const parts = file.split('/');
  // memo[i][j]: does pat[i..] match parts[j..]? Bounded by pattern x path size.
  const memo = new Map();
  const go = (i, j) => {
    const key = i * (parts.length + 1) + j;
    if (memo.has(key)) return memo.get(key);
    let ok;
    if (i === pat.length) {
      ok = j === parts.length;
    } else if (pat[i] === '**') {
      ok = go(i + 1, j) || (j < parts.length && go(i, j + 1));
    } else {
      ok = j < parts.length && matchSegment(pat[i], parts[j]) && go(i + 1, j + 1);
    }
    memo.set(key, ok);
    return ok;
  };
  return go(0, 0);
}
const matcher = (globs) => (file) => globs.some((glob) => globMatch(glob, file));

const isIgnored = matcher(config.ignore);
const isFull = matcher(config.fullSuite);
const modules = config.modules.map((m) => ({ ...m, match: matcher(m.paths) }));
const allSpecs = [...new Set(modules.flatMap((m) => m.specs))];

// Every spec must belong to a module (otherwise PRs could never select it),
// and every listed spec must exist.
const e2eDir = resolve(here, '..');
const onDisk = readdirSync(e2eDir).filter((f) => f.endsWith('.spec.ts')).map((f) => `e2e/${f}`);
const unmapped = onDisk.filter((f) => !allSpecs.includes(f));
const missing = allSpecs.filter((f) => !existsSync(resolve(e2eDir, '..', f)));
if (unmapped.length || missing.length) {
  if (unmapped.length) console.error(`Specs not mapped to any module in modules.json: ${unmapped.join(', ')}`);
  if (missing.length) console.error(`Specs in modules.json that do not exist: ${missing.join(', ')}`);
  process.exit(1);
}

function changedFiles() {
  const files = arg('files');
  if (files !== undefined) return files.split(/[\s,]+/).filter(Boolean);
  const base = arg('base') || 'origin/refactor/next-gen';
  const root = execSync('git rev-parse --show-toplevel', { encoding: 'utf-8' }).trim();
  return execSync(`git diff --name-only ${base}...HEAD`, { cwd: root, encoding: 'utf-8' })
    .split('\n')
    .map((f) => f.trim())
    .filter(Boolean);
}

function decide() {
  if (has('full')) {
    return { mode: 'full', specs: allSpecs, modules: modules.map((m) => m.name), reasons: ['Full suite requested'], uncovered: [] };
  }
  const chosen = arg('modules');
  if (chosen) {
    const names = chosen.split(',').map((s) => s.trim()).filter(Boolean);
    const unknown = names.filter((n) => !modules.some((m) => m.name === n));
    if (unknown.length) throw new Error(`Unknown module(s): ${unknown.join(', ')}`);
    const picked = modules.filter((m) => names.includes(m.name));
    return {
      mode: 'modules',
      specs: [...new Set(picked.flatMap((m) => m.specs))],
      modules: names,
      reasons: [`Modules requested: ${names.join(', ')}`],
      uncovered: picked.filter((m) => m.specs.length === 0).map((m) => m.name),
    };
  }

  const files = changedFiles();
  const hit = new Set();
  const reasons = [];
  let full = false;
  for (const file of files) {
    if (isIgnored(file)) continue;
    if (isFull(file)) {
      full = true;
      reasons.push(`${file} -> full suite (shared code)`);
      continue;
    }
    const owners = modules.filter((m) => m.match(file));
    if (owners.length) {
      owners.forEach((m) => hit.add(m.name));
      reasons.push(`${file} -> ${owners.map((m) => m.name).join(', ')}`);
    } else if (/^m8flow-(designer|backend)\/src\//.test(file)) {
      full = true;
      reasons.push(`${file} -> full suite (no module mapping)`);
    }
  }
  if (full) {
    return { mode: 'full', specs: allSpecs, modules: modules.map((m) => m.name), reasons, uncovered: [], files };
  }
  const picked = modules.filter((m) => hit.has(m.name));
  const specs = [...new Set(picked.flatMap((m) => m.specs))];
  return {
    mode: specs.length ? 'modules' : 'none',
    specs,
    modules: picked.map((m) => m.name),
    reasons: reasons.length ? reasons : ['No E2E-relevant changes'],
    uncovered: picked.filter((m) => m.specs.length === 0).map((m) => m.name),
    files,
  };
}

const result = decide();
const run = result.specs.length > 0;
console.log(JSON.stringify({ run, ...result }, null, 2));

if (has('github-output') && process.env.GITHUB_OUTPUT) {
  // Full mode passes no spec list, so Playwright runs everything in e2e/.
  const specArgs = result.mode === 'full' ? '' : result.specs.join(' ');
  appendFileSync(
    process.env.GITHUB_OUTPUT,
    [
      `run=${run}`,
      `mode=${result.mode}`,
      `specs=${specArgs}`,
      `modules=${result.modules.join(',')}`,
      `uncovered=${result.uncovered.join(',')}`,
    ].join('\n') + '\n',
  );
}
