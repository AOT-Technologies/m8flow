/**
 * Renders a task's `spiffworkflow:instructionsForEndUser` markdown (GFM) for
 * the end user. Raw HTML in the markdown is not rendered (react-markdown's
 * default), so instructions can't inject markup.
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

export function InstructionsMarkdown({ markdown }: { markdown: string }) {
  return createElement(Markdown, { remarkPlugins: REMARK_PLUGINS }, markdown);
}
