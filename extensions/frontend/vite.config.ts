import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import viteTsconfigPaths from 'vite-tsconfig-paths';
import svgr from 'vite-plugin-svgr';
import path from 'path';

const variant = process.env.VARIANT || 'm8flow';
const host = process.env.HOST ?? 'localhost';
const port = process.env.PORT ? parseInt(process.env.PORT, 10) : 7001;

/**
 * M8Flow Extensions Vite Configuration
 * 
 * This configuration creates a standalone extensions package that wraps
 * the upstream SpiffWorkflow frontend without modifying it.
 */
export default defineConfig({
  base: '/',
  root: __dirname,
  plugins: [
    // Use React plugin since we're importing React-based upstream app
    react(),
    viteTsconfigPaths(),
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
  resolve: {
    alias: {
      // Point to upstream source (read-only)
      '@spiff': path.resolve(__dirname, '../../spiffworkflow-frontend/src'),
      // Point to extensions (our code)
      '@m8flow': path.resolve(__dirname, './'),
      // Inferno alias for production builds
      inferno:
        process.env.NODE_ENV !== 'production'
          ? 'inferno/dist/index.dev.esm.js'
          : 'inferno/dist/index.esm.js',
    },
    preserveSymlinks: true,
    // Ensure we can resolve modules from upstream node_modules
    dedupe: ['react', 'react-dom', '@emotion/react', '@emotion/styled'],
    // Also look in upstream node_modules
    modules: [
      path.resolve(__dirname, 'node_modules'),
      path.resolve(__dirname, '../../spiffworkflow-frontend/node_modules'),
      'node_modules',
    ],
  },
  define: {
    'import.meta.env.M8FLOW_VARIANT': JSON.stringify(variant),
  },
  server: {
    open: false,
    host: '0.0.0.0', // Allow external access
    port,
    strictPort: false, // Try next port if current is busy
    // Allow serving files from upstream spiffworkflow-frontend directory
    fs: {
      allow: [
        __dirname, // extensions/frontend
        path.resolve(__dirname, '../../spiffworkflow-frontend'), // upstream directory
      ],
    },
    // Proxy API calls to backend
    proxy: {
      '/v1.0': {
        target: 'http://localhost:7000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    host,
    port,
  },
  css: {
    preprocessorOptions: {
      scss: {
        silenceDeprecations: ['mixed-decls'],
      },
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: path.resolve(__dirname, `index.${variant}.html`),
    },
  },
});
