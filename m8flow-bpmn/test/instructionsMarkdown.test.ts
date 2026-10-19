import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { InstructionsMarkdown } from '../lib/InstructionsMarkdown';

const render = (markdown?: string | null) => renderToStaticMarkup(createElement(InstructionsMarkdown, { markdown }));

describe('InstructionsMarkdown', () => {
  it.each([null, undefined, ''])('renders nothing for %s', (markdown) => {
    expect(render(markdown)).toBe('');
  });

  it('renders bold, italic and bullet lists', () => {
    const html = render('A **Manual Task** and *Continue*:\n\n* one\n* two');
    expect(html).toContain('<strong>Manual Task</strong>');
    expect(html).toContain('<em>Continue</em>');
    expect(html.match(/<li>/g)).toHaveLength(2);
  });

  it('does not render raw HTML', () => {
    expect(render('hi <script>alert(1)</script>')).not.toContain('<script>');
  });

  it.each([
    '[x](javascript:alert(1))',
    '[x](JaVaScRiPt:alert(1))',
    '[x](data:text/html,hi)',
    '[x](vbscript:msgbox)',
    '![x](javascript:alert(1))',
  ])('drops unsafe URL protocols: %s', (markdown) => {
    expect(render(markdown)).not.toMatch(/javascript:|data:|vbscript:/i);
  });

  it('applies our allowlist, not react-markdown default (which allows irc:)', () => {
    expect(render('[x](irc://host/chan)')).not.toContain('irc:');
  });

  it.each(['https://example.com', 'mailto:a@b.co', '/relative', '#anchor'])(
    'keeps safe link %s',
    (url) => {
      expect(render(`[x](${url})`)).toContain(`href="${url}"`);
    },
  );
});
