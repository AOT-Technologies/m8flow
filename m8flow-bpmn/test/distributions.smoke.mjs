/**
 * Distribution export smoke — vite-node resolves camunda-shaped entry points.
 * Full construct/importXML needs a real browser (jsdom lacks SVG/CSS APIs
 * diagram-js requires); that coverage stays in designer Playwright e2e.
 */
import assert from 'node:assert/strict';
import { access } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// dmn-js touches window at module evaluation time.
globalThis.window ??= {
  getSelection: () => null,
  document: { createElement: () => ({ style: {} }) },
};

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

for (const rel of [
  'lib/Modeler.ts',
  'lib/NavigatedViewer.ts',
  'lib/DmnModeler.ts',
  'vite/index.js',
  'dist/assets/modeler.css',
  'dist/assets/viewer.css',
  'dist/assets/dmn.css',
]) {
  await access(path.join(root, rel));
}

const { default: Modeler } = await import('../lib/Modeler.ts');
const { default: NavigatedViewer, applyTaskStateMarkers } = await import('../lib/NavigatedViewer.ts');
const { default: DmnModeler } = await import('../lib/DmnModeler.ts');

assert.equal(typeof Modeler, 'function');
assert.equal(typeof NavigatedViewer, 'function');
assert.equal(typeof DmnModeler, 'function');
assert.equal(typeof applyTaskStateMarkers, 'function');

console.log('ok exports: Modeler, NavigatedViewer, DmnModeler, applyTaskStateMarkers');
