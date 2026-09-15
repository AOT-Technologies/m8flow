import { describe, expect, it } from 'vitest';

import { formatCode } from './codeFormat';

describe('formatCode — python', () => {
  it('converts tabs to four spaces', () => {
    expect(formatCode('python', 'if x:\n\tpass\n')).toBe('if x:\n    pass\n');
  });

  it('strips trailing whitespace and adds a single final newline', () => {
    expect(formatCode('python', 'x = 1   ')).toBe('x = 1\n');
  });

  it('collapses runs of blank lines to a single blank line', () => {
    expect(formatCode('python', 'a = 1\n\n\n\nb = 2\n')).toBe('a = 1\n\nb = 2\n');
  });

  it('returns an empty string for whitespace-only input', () => {
    expect(formatCode('python', '   \n\n')).toBe('');
  });
});

describe('formatCode — markdown', () => {
  it('preserves trailing spaces (hard line breaks) and tabs', () => {
    expect(formatCode('markdown', 'line one  \n\tcode\n')).toBe('line one  \n\tcode\n');
  });

  it('collapses blank-line runs and normalizes the final newline', () => {
    expect(formatCode('markdown', '# Title\n\n\n\ntext')).toBe('# Title\n\ntext\n');
  });

  it('returns an empty string for whitespace-only input', () => {
    expect(formatCode('markdown', '  \n')).toBe('');
  });
});

describe('formatCode — json', () => {
  it('pretty-prints with two-space indentation', () => {
    expect(formatCode('json', '{"a":1,"b":[2,3]}')).toBe('{\n  "a": 1,\n  "b": [\n    2,\n    3\n  ]\n}\n');
  });

  it('leaves invalid JSON untouched (lintCode surfaces the error instead)', () => {
    expect(formatCode('json', '{ not json')).toBe('{ not json');
  });

  it('returns an empty string for whitespace-only input', () => {
    expect(formatCode('json', '   \n')).toBe('');
  });
});
