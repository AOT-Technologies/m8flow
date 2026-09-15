import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { StorybookConfig } from '@storybook/react-vite';
import tailwindcss from '@tailwindcss/vite';

const dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Deliberately its own Vite config, not a `viteFinal` merge of the app's
 * `../vite.config.ts`. That config wires in the m8flow-bpmn plugin, the
 * backend dev-server proxy, gzip/brotli compression, and manual vendor
 * chunking — all production/app-runtime concerns Storybook has no use for
 * and shouldn't pull in. Only the two things component stories actually
 * need are added here: the `@` alias (matches `tsconfig.json`) and the
 * Tailwind v4 plugin (so `src/styles/index.css`'s `@import 'tailwindcss'`
 * resolves). See m8flow-designer-component-library map, ticket 01 —
 * isolation from the production build is load-bearing, not incidental.
 */
const config: StorybookConfig = {
  stories: ['../src/components/{ui,library}/**/*.stories.@(ts|tsx)'],
  addons: [],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  viteFinal: async (viteConfig) => {
    viteConfig.plugins = [...(viteConfig.plugins ?? []), tailwindcss()];
    // `resolve.alias` may already be array-form here (Storybook's own Vite
    // builder sets some aliases that way) — spreading an array into an
    // object literal silently turns it into numeric-index keys instead of
    // alias entries, exactly the pitfall the app's own `vite.config.ts`
    // flags in its own alias comment. Append instead of clobbering, and
    // normalize object-form to array-form so both shapes merge safely.
    const existingAlias = viteConfig.resolve?.alias;
    const appAlias = { find: '@', replacement: path.resolve(dirname, '../src') };
    viteConfig.resolve = {
      ...viteConfig.resolve,
      alias: Array.isArray(existingAlias)
        ? [...existingAlias, appAlias]
        : [
            ...Object.entries(existingAlias ?? {}).map(([find, replacement]) => ({
              find,
              replacement: replacement as string,
            })),
            appAlias,
          ],
    };
    return viteConfig;
  },
};

export default config;
