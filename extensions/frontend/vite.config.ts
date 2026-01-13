import preact from '@preact/preset-vite';
import { defineConfig } from 'vite';
import viteTsconfigPaths from 'vite-tsconfig-paths';
import svgr from 'vite-plugin-svgr';
import path from 'path';
import { overrideResolver } from './vite-plugin-override-resolver';

const host = process.env.HOST ?? 'localhost';
const port = process.env.PORT ? parseInt(process.env.PORT, 10) : 7001; // Same port as core
const backendPort = process.env.BACKEND_PORT ? parseInt(process.env.BACKEND_PORT, 10) : 7000; // Backend port (default: 7000)

export default defineConfig({
  base: '/',
  plugins: [
    // Override resolver - must be first to check extensions before core
    overrideResolver(),
    preact({ devToolsEnabled: false }),
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
        silenceDeprecations: ['mixed-decls'],
        // Allow SASS to find modules in extensions/frontend/node_modules
        loadPaths: [
          path.resolve(__dirname, './node_modules'),
        ],
      },
    },
  },
});
