// @vitest-environment node

import { loadConfigFromFile } from 'vite';
import { describe, expect, it } from 'vitest';

describe('Vite API version build configuration', () => {
  it('injects M8FLOW_API_VERSION into the designer client bundle', async () => {
    const originalEnvironment = {
      VITEST: process.env.VITEST,
      VITE_API_VERSION: process.env.VITE_API_VERSION,
      M8FLOW_API_VERSION: process.env.M8FLOW_API_VERSION,
    };

    try {
      // Exercise the production branch of vite.config.ts, which loads the
      // repo-root environment and maps M8FLOW_API_VERSION to the Vite define.
      process.env.VITEST = '';
      delete process.env.VITE_API_VERSION;
      process.env.M8FLOW_API_VERSION = '2.0';

      const loaded = await loadConfigFromFile(
        { command: 'build', mode: 'production' },
        'vite.config.ts',
        process.cwd(),
      );

      expect(loaded?.config.define?.['import.meta.env.VITE_API_VERSION']).toBe('"2.0"');
    } finally {
      for (const [key, value] of Object.entries(originalEnvironment)) {
        if (value === undefined) {
          delete process.env[key];
        } else {
          process.env[key] = value;
        }
      }
    }
  }, 15_000);
});
