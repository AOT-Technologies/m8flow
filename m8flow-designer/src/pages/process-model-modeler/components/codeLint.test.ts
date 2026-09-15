import { describe, expect, it } from 'vitest';

import { lintCode } from './codeLint';

const rules = (language: 'python' | 'markdown' | 'json', code: string) =>
  lintCode(language, code).map((diagnostic) => diagnostic.rule);

describe('lintCode — python', () => {
  it('accepts clean code with no diagnostics', () => {
    expect(lintCode('python', 'x = (1 + 2)\n')).toEqual([]);
  });

  it('flags an unclosed bracket at its opening position', () => {
    const diagnostics = lintCode('python', 'x = (1 + 2\n');
    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0]).toMatchObject({
      rule: 'unbalanced-bracket',
      severity: 'error',
      line: 1,
      column: 5,
    });
  });

  it('flags an unmatched closing bracket', () => {
    expect(rules('python', 'x = 1)\n')).toContain('unbalanced-bracket');
  });

  it('flags an unterminated string literal', () => {
    const diagnostics = lintCode('python', 'name = "abc\n');
    expect(diagnostics.some((d) => d.rule === 'unterminated-string' && d.severity === 'error')).toBe(
      true,
    );
  });

  it('ignores brackets and quotes inside strings and comments', () => {
    expect(lintCode('python', 'x = "(" + \'#)\'  # a ) comment\n')).toEqual([]);
  });

  it('handles triple-quoted strings spanning lines', () => {
    expect(lintCode('python', 'doc = """\nline (with) bracket\n"""\n')).toEqual([]);
    expect(rules('python', 'doc = """unterminated\n')).toContain('unterminated-string');
  });

  it('flags mixed tabs and spaces as an error', () => {
    expect(rules('python', 'if x:\n \t pass\n')).toContain('mixed-indentation');
  });

  it('warns on tab indentation and trailing whitespace', () => {
    expect(rules('python', 'if x:\n\tpass\n')).toContain('tab-indentation');
    expect(rules('python', 'x = 1   \n')).toContain('trailing-whitespace');
  });

  it('warns when the file has no trailing newline', () => {
    expect(rules('python', 'x = 1')).toContain('final-newline');
  });
});

describe('lintCode — markdown', () => {
  it('accepts a closed fenced code block', () => {
    expect(lintCode('markdown', '```\ncode\n```\n')).toEqual([]);
  });

  it('warns on an unclosed fenced code block', () => {
    expect(rules('markdown', '```\ncode\n')).toContain('unclosed-code-fence');
  });

  it('does not apply python rules to markdown (trailing spaces are allowed)', () => {
    expect(lintCode('markdown', 'line with trailing spaces  \n')).toEqual([]);
  });
});

describe('lintCode — json', () => {
  it('accepts an empty file', () => {
    expect(lintCode('json', '')).toEqual([]);
  });

  it('accepts valid JSON', () => {
    expect(lintCode('json', '{\n  "a": 1\n}\n')).toEqual([]);
  });

  it('flags invalid JSON with a line/column derived from the parse error', () => {
    const diagnostics = lintCode('json', '{\n  "a": 1,\n}\n');
    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0]).toMatchObject({ rule: 'invalid-json', severity: 'error' });
    expect(diagnostics[0].line).toBeGreaterThanOrEqual(1);
  });
});
