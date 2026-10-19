/**
 * Renders a task's `spiffworkflow:instructionsForEndUser` markdown (GFM) for
 * the end user. Raw HTML in the markdown is not rendered (react-markdown's
 * default), so instructions can't inject markup, and link/image URLs pass
 * through our own protocol allowlist (`safeUrl`).
 *
 * Plain `createElement`, not JSX: this package's Vite plugin points JSX at
 * Preact for bpmn-js-spiffworkflow, and the host supplies React (deduped via
 * m8flow-bpmn/vite).
 *
 * Host:
 *   import { InstructionsMarkdown } from 'm8flow-bpmn/lib/InstructionsMarkdown';
 *   <InstructionsMarkdown markdown={task.instructions} />
 */
import { createElement } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const REMARK_PLUGINS = [remarkGfm];
const SAFE_PROTOCOLS = new Set(['http:', 'https:', 'mailto:']);

/** Link/image URL policy, explicit rather than react-markdown's default: only
 * http(s), mailto and relative URLs survive; javascript:, data:, vbscript:,
 * etc. become ''. Uses the WHATWG URL parser (what the browser applies to the
 * href), so case tricks and stripped whitespace/control chars can't slip past. */
function safeUrl(url: string): string {
  try {
    return SAFE_PROTOCOLS.has(new URL(url, 'https://relative.invalid').protocol) ? url : '';
  } catch {
    return '';
  }
}

export function InstructionsMarkdown({ markdown }: { markdown: string }) {
  return createElement(Markdown, { remarkPlugins: REMARK_PLUGINS, urlTransform: safeUrl }, markdown);
}
