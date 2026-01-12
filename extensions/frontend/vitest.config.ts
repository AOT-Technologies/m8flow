import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
  },
  resolve: {
    alias: {
      '@m8flow': path.resolve(__dirname, './'),
      '@spiff': path.resolve(__dirname, '../../spiffworkflow-frontend/src'),
    },
  },
});
