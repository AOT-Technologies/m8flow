import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { InstructionsMarkdown } from '../lib/InstructionsMarkdown';

const render = (markdown: string) => renderToStaticMarkup(createElement(InstructionsMarkdown, { markdown }));

describe('InstructionsMarkdown', () => {
  it('renders bold, italic and bullet lists', () => {
    const html = render('A **Manual Task** and *Continue*:\n\n* one\n* two');
    expect(html).toContain('<strong>Manual Task</strong>');
    expect(html).toContain('<em>Continue</em>');
    expect(html.match(/<li>/g)).toHaveLength(2);
  });

  it('does not render raw HTML', () => {
    expect(render('hi <script>alert(1)</script>')).not.toContain('<script>');
  });
});
