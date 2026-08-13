/**
 * Upstream ProcessModelEditDiagram creates its Pyodide worker with
 * `new URL('/src/workers/python.ts', import.meta.url)`. That absolute path
 * resolves under m8flow's `publicDir` and breaks the build. Rewrite it to a
 * path relative to the upstream file so Vite's worker plugin can bundle it.
 *
 * Lives here (not in an LGPL-owned override body) so we can keep the
 * `@spiff-core` re-export of EditDiagram.
 */
import type { Plugin } from 'vite';

const UPSTREAM_ABSOLUTE =
  "new URL('/src/workers/python.ts', import.meta.url)";
const RELATIVE_TO_VIEWS =
  "new URL('../workers/python.ts', import.meta.url)";

export function fixPythonWorkerUrl(): Plugin {
  return {
    name: 'fix-python-worker-url',
    enforce: 'pre',
    transform(code, id) {
      const normalized = id.replace(/\\/g, '/');
      if (!normalized.includes('/spiffworkflow-frontend/src/views/ProcessModelEditDiagram')) {
        return null;
      }
      if (!code.includes(UPSTREAM_ABSOLUTE)) {
        return null;
      }
      return {
        code: code.replaceAll(UPSTREAM_ABSOLUTE, RELATIVE_TO_VIEWS),
        map: null,
      };
    },
  };
}
