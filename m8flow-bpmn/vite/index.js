/**
 * Vite plugin for hosts that mount m8flow-bpmn with the properties panel /
 * bpmn-js-spiffworkflow. Owns the Preact single-instance aliases and the
 * Spiff JSX transform (ticket 12).
 *
 * Plain JS so Vite can import this from vite.config without a TS loader.
 */
import path from 'node:path';
import { createRequire } from 'node:module';
import { transform } from 'esbuild';

const require = createRequire(import.meta.url);

function propertiesPanelRoot() {
  return path.dirname(require.resolve('@bpmn-io/properties-panel/package.json'));
}

function resolvePropertiesPanelPreact(...segments) {
  return path.join(propertiesPanelRoot(), 'preact', ...segments);
}

function spiffworkflowPreactJsxPlugin() {
  const SPIFFWORKFLOW_JSX = /node_modules\/bpmn-js-spiffworkflow\/.*\.jsx$/;
  return {
    name: 'm8flow-bpmn-spiffworkflow-preact-jsx',
    enforce: 'pre',
    async transform(code, id) {
      if (!SPIFFWORKFLOW_JSX.test(id)) return null;
      const result = await transform(code, {
        loader: 'jsx',
        jsx: 'automatic',
        jsxImportSource: 'preact',
        sourcefile: id,
        sourcemap: true,
      });
      return { code: result.code, map: result.map };
    },
  };
}

/**
 * @param {{ alias?: Record<string, string> }} [options]
 * @returns {{
 *   plugins: import('vite').Plugin[],
 *   resolve: { alias: Array<{ find: string | RegExp, replacement: string }> },
 *   optimizeDeps: import('vite').DepOptimizationOptions,
 * }}
 */
export default function m8flowBpmnVitePlugin(options = {}) {
  const preactRoot = resolvePropertiesPanelPreact();
  // Array form, not the plain-object shorthand: the `@bpmn-io/properties-panel`
  // entry below needs an exact-match RegExp (see its own comment), which only
  // the array form supports. Vite honors this shape in both normal dev-server
  // resolution *and* the esbuild-based optimizeDeps pre-bundling scan — a
  // plain resolveId plugin hook was tried here first and only covered the
  // former, leaving bpmn-js-properties-panel's pre-bundled chunk (built by
  // the latter) with its own separate, un-aliased copy. Host `options.alias`
  // entries go first so they still take priority on a key collision,
  // matching the old object-spread-last-wins order. Consuming hosts must
  // spread this array into their own `resolve.alias` array (see
  // m8flow-designer's vite.config.ts) — a plain-object spread (`{...this}`)
  // would turn it into numeric-index keys instead.
  const hostAliasEntries = Object.entries(options.alias ?? {}).map(([find, replacement]) => ({
    find,
    replacement,
  }));
  return {
    plugins: [spiffworkflowPreactJsxPlugin()],
    resolve: {
      alias: [
        ...hostAliasEntries,
        { find: 'preact', replacement: preactRoot },
        { find: 'preact/hooks', replacement: resolvePropertiesPanelPreact('hooks') },
        { find: 'preact/compat', replacement: resolvePropertiesPanelPreact('compat') },
        { find: 'preact/jsx-runtime', replacement: resolvePropertiesPanelPreact('jsx-runtime') },
        // `classnames` is a CommonJS dep of @bpmn-io/properties-panel, and it
        // lives only in this package's nested node_modules (not the host's).
        // Without an absolute alias the host can't resolve the bare
        // specifier, so `optimizeDeps.include: ['classnames']` below
        // silently no-ops and Vite serves the raw CJS file — which then
        // throws at runtime with "does not provide an export named
        // 'default'" the moment the properties panel loads. Alias it to
        // this package's own copy so it resolves consistently and gets
        // pre-bundled with CJS→ESM interop.
        { find: 'classnames', replacement: require.resolve('classnames') },
        // Same nested-node_modules problem as `classnames`, but with a
        // second-order effect: bpmn-js-spiffworkflow's own .jsx fields
        // (transformed on-the-fly by spiffworkflowPreactJsxPlugin above, not
        // visible to Vite's dependency scanner) import TextFieldEntry/
        // useError/etc. directly from `@bpmn-io/properties-panel`. Before
        // this alias, that bare specifier resolved two different ways: the
        // dependency scanner found bpmn-js-properties-panel's own import of
        // it and inlined a copy into that package's pre-bundled chunk, while
        // bpmn-js-spiffworkflow's un-scanned .jsx import of the same
        // specifier was resolved fresh (per-file) and served raw — two
        // separate module instances of the same preact-hooks-backed code,
        // i.e. two separate copies of Preact's internal "current component"
        // hook state. Confirmed live as `TypeError: Cannot read properties
        // of undefined (reading 'context')` inside `useError` the moment any
        // field entry (e.g. a User Task's Name field) mounts. Aliasing the
        // bare specifier to one absolute file makes both paths resolve
        // identically, so both the scanner and the raw per-file resolution
        // land on the same instance. Exact-match RegExp, not a plain string:
        // a string find here would prefix-match (and so also silently
        // rewrite) deep imports like
        // `@bpmn-io/properties-panel/assets/properties-panel.css`
        // (lib/Modeler.ts's own CSS import) — confirmed live as a 500 "Does
        // the file exist?" error before switching to a RegExp find here.
        {
          find: /^@bpmn-io\/properties-panel$/,
          replacement: path.join(propertiesPanelRoot(), 'dist', 'index.esm.js'),
        },
      ],
    },
    optimizeDeps: {
      include: ['classnames', '@bpmn-io/properties-panel'],
      exclude: ['m8flow-bpmn'],
      esbuildOptions: {
        jsx: 'automatic',
        jsxImportSource: 'preact',
      },
    },
  };
}
