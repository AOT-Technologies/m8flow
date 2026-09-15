import { defineConfig, type Plugin } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';
import { visualizer } from 'rollup-plugin-visualizer';
import { compression } from 'vite-plugin-compression2';
import m8flowBpmnVitePlugin from 'm8flow-bpmn/vite';

const m8flowBpmn = m8flowBpmnVitePlugin();

/**
 * Break the HTML → CSS → font critical-request chain Lighthouse reports on
 * the production preview: the body/UI font (Poppins Regular — see
 * src/styles/aot-fonts.css) is discovered only after the render-blocking
 * stylesheet parses its @font-face. Preloading the hashed woff2 from
 * index.html lets the browser start that download in parallel with CSS.
 * Only the default weight/style is preloaded — the other Poppins weights,
 * Aron, and JetBrains Mono aren't needed for first paint and must not
 * compete with LCP. Same-origin assets, so no preconnect (Lighthouse also
 * reported no preconnect candidates).
 */
function preloadBodyFontPlugin(): Plugin {
  let base = '/';
  return {
    name: 'preload-body-font',
    configResolved(config) {
      base = config.base;
    },
    transformIndexHtml: {
      order: 'post',
      handler(html, ctx) {
        if (!ctx.bundle) return html;
        const font = Object.values(ctx.bundle).find(
          (item) =>
            item.type === 'asset' &&
            item.fileName.endsWith('.woff2') &&
            /Poppins-Regular/.test(item.fileName),
        );
        if (!font || font.type !== 'asset') return html;
        const href = `${base}${font.fileName}`.replace(/\/{2,}/g, '/');
        if (html.includes(`href="${href}"`)) return html;
        const tag = `    <link rel="preload" href="${href}" as="font" type="font/woff2" crossorigin>\n`;
        // After <title>, before Vite's script/stylesheet tags, so the font
        // request starts as soon as the document head is parsed — not after
        // the CSS file is discovered.
        return html.replace('</title>', `</title>\n${tag}`);
      },
    },
  };
}

// Load repo-root .env so the dev server picks up the same backend origin the
// rest of m8flow uses, without needing its own copy of shared config.
const repoRoot = path.resolve(__dirname, '..');
const rootEnv = loadEnv(process.env.NODE_ENV || 'development', repoRoot, '');

const backendPort = process.env.M8FLOW_BACKEND_PORT ?? rootEnv.M8FLOW_BACKEND_PORT ?? '6840';
const backendBaseUrl =
  process.env.VITE_BACKEND_BASE_URL ??
  rootEnv.M8FLOW_FRONTEND_BACKEND_BASE_URL ??
  `http://localhost:${backendPort}`;

// `npm run build:analyze` sets this so `dist/stats.html` (an interactive
// treemap of what's actually inside each output chunk) only gets generated
// on demand — a normal `npm run build` doesn't pay for it or leave it behind.
// See .scratch/m8flow-designer-optimization/issues/01-bundle-and-component-audit.md.
const shouldAnalyze = process.env.ANALYZE === 'true';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    ...m8flowBpmn.plugins,
    preloadBodyFontPlugin(),
    shouldAnalyze &&
      visualizer({
        filename: 'dist/stats.html',
        gzipSize: true,
        brotliSize: true,
        template: 'treemap',
      }),
    // Emit `.gz` and `.br` alongside every eligible build output file, so
    // `dist/` is directly deployable to a static host/CDN that can serve
    // pre-compressed assets (e.g. nginx `gzip_static`/`brotli_static`) without
    // compressing on the fly. The plugin's own default `include` only covers
    // html/xml/css/json/js/mjs/svg/yaml/yml/toml — broadened here to also
    // cover font formats, since "assets" per the map's destination means
    // more than just JS/CSS. `skipIfLargerOrEqual` (default true) already
    // skips emitting a variant that wouldn't actually shrink the file (e.g.
    // `.woff2`, which is already compressed), so it's safe to include those
    // extensions too rather than special-case them out.
    // See .scratch/m8flow-designer-optimization/issues/03-compressed-build-output.md.
    // Configuring a server to actually *serve* these files is out of scope
    // (m8flow-deployment's job, a different repo) — this only produces them.
    compression({
      algorithm: 'gzip',
      include: /\.(html|xml|css|json|js|mjs|svg|yaml|yml|toml|ttf|otf|eot)$/,
    }),
    compression({
      algorithm: 'brotliCompress',
      include: /\.(html|xml|css|json|js|mjs|svg|yaml|yml|toml|ttf|otf|eot)$/,
    }),
  ],
  resolve: {
    // Array form, not the plain-object shorthand: m8flowBpmn.resolve.alias
    // is itself array-form (see m8flow-bpmn/vite/index.js's own comment —
    // one of its entries needs an exact-match RegExp `find`, which only the
    // array form supports). Spreading an array into an object literal
    // (`{...m8flowBpmn.resolve.alias}`) would silently turn it into
    // numeric-index keys instead of alias entries.
    alias: [{ find: '@', replacement: path.resolve(__dirname, './src') }, ...m8flowBpmn.resolve.alias],
  },
  optimizeDeps: {
    ...m8flowBpmn.optimizeDeps,
  },
  server: {
    host: '0.0.0.0',
    port: Number(process.env.PORT ?? 6853),
    // Same pattern as m8flow-frontend: proxy API so Home fetches are same-origin
    // (avoids cross-port CORS + credentials issues). Login/logout still use the
    // absolute backend URL so Keycloak redirect_uri stays on :6840.
    proxy: {
      '/v1.0': {
        target: backendBaseUrl,
        changeOrigin: true,
        secure: false,
      },
    },
    fs: {
      allow: [path.resolve(__dirname), path.resolve(__dirname, '..', 'm8flow-bpmn')],
    },
  },
  define: {
    'import.meta.env.VITE_BACKEND_BASE_URL': JSON.stringify(backendBaseUrl),
    // Empty = same-origin relative paths through the Vite proxy above.
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(
      process.env.VITE_API_BASE_URL ?? '',
    ),
  },
  build: {
    rollupOptions: {
      output: {
        // Deliberately narrow — see
        // .scratch/m8flow-designer-optimization/issues/06-vendor-chunk-splitting-strategy.md.
        // Only pulls out dependencies that are (a) shared across chunks and
        // (b) change far less often than app code, so they benefit from a
        // long-term-cacheable chunk of their own separate from app code that
        // changes every release.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          // React itself: the one dependency truly shared by every chunk in
          // the app — main entry and every lazy route alike — and about as
          // stable as a dependency gets relative to this app's own code.
          if (/[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(id)) {
            return 'vendor-react';
          }
          // The app's own shadcn/UI primitive stack. Small today, but
          // tickets 08/09/11 (button/input/dialog/card consolidation) grow
          // its footprint across both the main entry and lazy routes —
          // splitting it out now means those tickets don't silently bloat
          // whichever chunk happens to import it first.
          if (
            /[\\/]node_modules[\\/](radix-ui|class-variance-authority|clsx|tailwind-merge|lucide-react)[\\/]/.test(
              id,
            )
          ) {
            return 'vendor-ui';
          }
          // Deliberately NOT grouped: bpmn-js, dmn-js, diagram-js,
          // bpmn-js-properties-panel, bpmn-js-spiffworkflow,
          // camunda-bpmn-moddle, bpmn-moddle, monaco-editor,
          // @monaco-editor/react, @bpmn-io/properties-panel. These are
          // already isolated into their own lazy chunks (BpmnCanvas/
          // DmnCanvas/properties-panel-fields/EditorDialog) purely by
          // dynamic-import boundaries (DiagramCanvas.tsx, BpmnCanvas.tsx) —
          // load-bearing isolation, not an accident: loading bpmn-js and
          // dmn-js together previously caused a real Preact/Inferno
          // virtual-DOM collision bug (see DiagramCanvas.tsx's own comment).
          // Any shared-vendor grouping across these libraries would need
          // re-verifying that isolation live in a browser, which this
          // session couldn't do — left alone rather than risked blind.
          return undefined;
        },
      },
    },
  },
  test: {
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    setupFiles: ['src/test/vitest.setup.ts'],
    environment: 'jsdom',
    globals: true,
    // Monaco resolves/runs only in a browser — swap both packages for light
    // stubs so EditorDialog is testable in jsdom (see src/test/monaco-*-stub).
    // `test.alias` matches plain string keys exactly (unlike Vite's own
    // `resolve.alias`, which prefix-matches `'foo'` against `'foo/bar'`) —
    // each deep subpath EditorDialog imports (tree-shaking monaco-editor down
    // to only python/markdown/json — see
    // .scratch/m8flow-designer-optimization/issues/04-tree-shake-monaco-languages.md)
    // needs its own explicit entry, or it falls through to the real package,
    // which fails to resolve/run outside a browser.
    alias: {
      'monaco-editor/esm/vs/editor/editor.api': path.resolve(
        __dirname,
        'src/test/monaco-editor-stub.ts',
      ),
      'monaco-editor/esm/vs/editor/editor.all': path.resolve(
        __dirname,
        'src/test/monaco-side-effect-stub.ts',
      ),
      'monaco-editor/esm/vs/basic-languages/python/python.contribution': path.resolve(
        __dirname,
        'src/test/monaco-side-effect-stub.ts',
      ),
      'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution': path.resolve(
        __dirname,
        'src/test/monaco-side-effect-stub.ts',
      ),
      'monaco-editor/esm/vs/language/json/monaco.contribution': path.resolve(
        __dirname,
        'src/test/monaco-side-effect-stub.ts',
      ),
      'monaco-editor': path.resolve(__dirname, 'src/test/monaco-editor-stub.ts'),
      '@monaco-editor/react': path.resolve(__dirname, 'src/test/monaco-react-stub.tsx'),
    },
  },
});
