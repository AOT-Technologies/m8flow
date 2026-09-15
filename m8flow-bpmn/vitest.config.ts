import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { defineConfig, type Plugin } from 'vitest/config';

const require = createRequire(import.meta.url);

function resolvePropertiesPanelPreact(...segments: string[]) {
  const panelRoot = path.dirname(require.resolve('@bpmn-io/properties-panel/package.json'));
  return path.join(panelRoot, 'preact', ...segments);
}

/** Resolve extensionless relative imports used by bpmn.io packages. */
function resolveJsExtensions(): Plugin {
  return {
    name: 'm8flow-bpmn-resolve-js-extensions',
    enforce: 'pre',
    resolveId(source, importer) {
      if (!importer || !source.startsWith('.')) return null;
      if (path.extname(source)) return null;
      const base = path.resolve(path.dirname(importer), source);
      for (const ext of ['.js', '.mjs', '.cjs', '.json']) {
        if (fs.existsSync(base + ext)) return base + ext;
      }
      if (fs.existsSync(base) && fs.statSync(base).isDirectory()) {
        for (const file of ['index.js', 'index.mjs']) {
          const index = path.join(base, file);
          if (fs.existsSync(index)) return index;
        }
      }
      return null;
    },
  };
}

export default defineConfig({
  plugins: [resolveJsExtensions()],
  ssr: {
    // Force bpmn.io packages through Vite so extensionless ESM resolves.
    noExternal: true,
  },
  resolve: {
    alias: {
      preact: resolvePropertiesPanelPreact(),
      'preact/hooks': resolvePropertiesPanelPreact('hooks'),
      'preact/compat': resolvePropertiesPanelPreact('compat'),
      'preact/jsx-runtime': resolvePropertiesPanelPreact('jsx-runtime'),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['test/**/*.test.ts'],
    server: {
      deps: {
        // Inline everything so extensionless bpmn.io ESM goes through Vite.
        inline: [/.*/],
      },
    },
  },
});
