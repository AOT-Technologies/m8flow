import preact from '@preact/preset-vite';
import { defineConfig, loadEnv } from 'vite';
import viteTsconfigPaths from 'vite-tsconfig-paths';
import svgr from 'vite-plugin-svgr';
import path from 'path';
import { overrideResolver } from './vite-plugin-override-resolver';

// Load repo root .env so MULTI_TENANT_ON is available even when npm start is run without sourcing .env
const repoRoot = path.resolve(__dirname, '../..');
const rootEnv = loadEnv(process.env.NODE_ENV || 'development', repoRoot, '');
if (rootEnv.MULTI_TENANT_ON !== undefined && process.env.VITE_MULTI_TENANT_ON === undefined) {
  process.env.VITE_MULTI_TENANT_ON = rootEnv.MULTI_TENANT_ON;
}

const host = process.env.HOST ?? 'localhost';
const port = process.env.PORT ? parseInt(process.env.PORT, 10) : 8001; // Match start_dev.sh FRONTEND_PORT
const backendPort = process.env.BACKEND_PORT ? parseInt(process.env.BACKEND_PORT, 10) : 8000; // Match start_dev.sh backend port

const multiTenantOn =
  rootEnv.MULTI_TENANT_ON ?? process.env.VITE_MULTI_TENANT_ON ?? 'false';

export default defineConfig({
  base: '/',
  publicDir: path.resolve(__dirname, '../../spiffworkflow-frontend/public'),
  define: {
    'import.meta.env.VITE_MULTI_TENANT_ON': JSON.stringify(multiTenantOn),
  },
  test: {
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    setupFiles: ['src/test/vitest.setup.ts'],
    globals: true,
    environment: 'jsdom',
  },
  plugins: [
    // Override resolver - must be first to check extensions before core
    overrideResolver(),
    // Use real React in tests to avoid ref type mismatch with @testing-library/react
    ...(process.env.VITEST ? [] : [preact({ devToolsEnabled: false })]),
    // viteTsconfigPaths(),
    svgr({
      svgrOptions: {
        exportType: 'default',
        ref: true,
        svgo: false,
        titleProp: true,
      },
      include: '**/*.svg',
    }),
  ],
  server: {
    open: false,
    host,
    port,
    // Allow serving files from upstream frontend (e.g. @spiffworkflow-frontend deps resolving to its node_modules)
    fs: {
      allow: [path.resolve(__dirname, '../..')],
    },
    // Proxy API requests to backend to avoid CORS issues
    proxy: {
      '/v1.0': {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
        secure: false,
        // Preserve the original path
        rewrite: (path) => path,
      },
      // Also proxy /api if backend uses that prefix
      '/api': {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path,
      },
    },
  },
  preview: {
    host,
    port,
  },
  resolve: {
    alias: {
      inferno:
        process.env.NODE_ENV !== 'production'
          ? 'inferno/dist/index.dev.esm.js'
          : 'inferno/dist/index.esm.js',
      // Alias to spiffworkflow-frontend source (go up 2 levels from extensions/frontend)
      '@spiffworkflow-frontend': path.resolve(__dirname, '../../spiffworkflow-frontend/src'),
      // Alias to spiffworkflow-frontend assets
      '@spiffworkflow-frontend-assets': path.resolve(__dirname, '../../spiffworkflow-frontend/src/assets'),
    },
    preserveSymlinks: true,
  },
  css: {
    preprocessorOptions: {
      scss: {
        silenceDeprecations: ['mixed-decls', 'if-function'],
        // Allow SASS to find modules in extensions/frontend/node_modules
        loadPaths: [
          path.resolve(__dirname, './node_modules'),
        ],
      },
    },
  },
});
