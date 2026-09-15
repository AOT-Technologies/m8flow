/**
 * Static, dependency-free linter for the properties-panel "Launch Editor"
 * popup (EditorDialog). spiffworkflow-frontend's own script editor ships no
 * in-editor Python linting — it leans on Monaco's syntax highlighting plus
 * server-side unit tests. This adds the linting/format/validation the ticket
 * asked for, entirely client-side: no Pyodide, no backend round-trip.
 *
 * Scope is deliberately *syntactic*, not semantic: it catches the mistakes a
 * single pass over the text can prove (unbalanced brackets, unterminated
 * strings, tab/space indentation problems) rather than anything needing a
 * real Python parser or name resolution. Deeper semantic linting would need a
 * Pyodide/backend engine — a documented future step, not this pass.
 *
 * Diagnostics are language-agnostic here; EditorDialog turns them into Monaco
 * markers and a clickable problems list, and blocks Save while any `error`
 * remains (the "validation" gate).
 */
export type Severity = 'error' | 'warning';

export type Diagnostic = {
  /** 1-based line number (matches Monaco's marker coordinates). */
  line: number;
  /** 1-based start column. */
  column: number;
  /** 1-based end column (exclusive), for the squiggle's width. */
  endColumn: number;
  message: string;
  severity: Severity;
  /** Short rule id, shown in parentheses so the reason is self-explanatory. */
  rule: string;
};

export type EditorLanguage = 'python' | 'markdown' | 'json';

const OPENERS = '([{';
const CLOSERS: Record<string, string> = { ')': '(', ']': '[', '}': '{' };

/**
 * Single char-by-char pass that understands Python comments and string
 * literals (single/double, triple-quoted, escapes) so bracket matching and
 * unterminated-string detection ignore anything inside strings/comments.
 */
function scanPythonStructure(code: string): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const stack: Array<{ char: string; line: number; col: number }> = [];
  let line = 1;
  let col = 1;
  let i = 0;
  const n = code.length;

  const advance = (count: number) => {
    for (let k = 0; k < count && i < n; k += 1) {
      if (code[i] === '\n') {
        line += 1;
        col = 1;
      } else {
        col += 1;
      }
      i += 1;
    }
  };

  while (i < n) {
    const ch = code[i];

    if (ch === '#') {
      while (i < n && code[i] !== '\n') advance(1);
      continue;
    }

    if (ch === '"' || ch === "'") {
      const quote = ch;
      const startLine = line;
      const startCol = col;
      const isTriple = code.slice(i, i + 3) === quote.repeat(3);

      if (isTriple) {
        advance(3);
        let closed = false;
        while (i < n) {
          if (code[i] === '\\') {
            advance(2);
            continue;
          }
          if (code.slice(i, i + 3) === quote.repeat(3)) {
            advance(3);
            closed = true;
            break;
          }
          advance(1);
        }
        if (!closed) {
          diagnostics.push({
            line: startLine,
            column: startCol,
            endColumn: startCol + 3,
            severity: 'error',
            rule: 'unterminated-string',
            message: 'Unterminated triple-quoted string',
          });
        }
      } else {
        advance(1);
        let closed = false;
        while (i < n) {
          const c = code[i];
          if (c === '\\') {
            advance(2);
            continue;
          }
          if (c === '\n') break; // a plain string literal can't span a newline
          if (c === quote) {
            advance(1);
            closed = true;
            break;
          }
          advance(1);
        }
        if (!closed) {
          diagnostics.push({
            line: startLine,
            column: startCol,
            endColumn: col,
            severity: 'error',
            rule: 'unterminated-string',
            message: 'Unterminated string literal',
          });
        }
      }
      continue;
    }

    if (OPENERS.includes(ch)) {
      stack.push({ char: ch, line, col });
      advance(1);
      continue;
    }

    if (ch in CLOSERS) {
      const top = stack.pop();
      if (!top || top.char !== CLOSERS[ch]) {
        diagnostics.push({
          line,
          column: col,
          endColumn: col + 1,
          severity: 'error',
          rule: 'unbalanced-bracket',
          message: `Unmatched closing '${ch}'`,
        });
      }
      advance(1);
      continue;
    }

    advance(1);
  }

  stack.forEach((open) => {
    diagnostics.push({
      line: open.line,
      column: open.col,
      endColumn: open.col + 1,
      severity: 'error',
      rule: 'unbalanced-bracket',
      message: `Unclosed '${open.char}'`,
    });
  });

  return diagnostics;
}

function lintPythonLines(code: string): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const lines = code.split('\n');

  lines.forEach((text, idx) => {
    const lineNo = idx + 1;
    const indent = /^[ \t]*/.exec(text)?.[0] ?? '';

    if (indent.includes('\t') && indent.includes(' ')) {
      diagnostics.push({
        line: lineNo,
        column: 1,
        endColumn: indent.length + 1,
        severity: 'error',
        rule: 'mixed-indentation',
        message: 'Mixed tabs and spaces in indentation',
      });
    } else if (indent.includes('\t')) {
      diagnostics.push({
        line: lineNo,
        column: 1,
        endColumn: indent.length + 1,
        severity: 'warning',
        rule: 'tab-indentation',
        message: 'Indentation uses tabs; prefer 4 spaces',
      });
    }

    if (text.trim() !== '' && /[ \t]+$/.test(text)) {
      const trimmedLength = text.replace(/[ \t]+$/, '').length;
      diagnostics.push({
        line: lineNo,
        column: trimmedLength + 1,
        endColumn: text.length + 1,
        severity: 'warning',
        rule: 'trailing-whitespace',
        message: 'Trailing whitespace',
      });
    }
  });

  if (code.length > 0 && !code.endsWith('\n')) {
    const lastLine = lines.length;
    const lastLen = lines[lastLine - 1]?.length ?? 0;
    diagnostics.push({
      line: lastLine,
      column: lastLen + 1,
      endColumn: lastLen + 2,
      severity: 'warning',
      rule: 'final-newline',
      message: 'No newline at end of file',
    });
  }

  return diagnostics;
}

function lintMarkdown(code: string): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const lines = code.split('\n');
  let fenceOpenLine = -1;

  lines.forEach((text, idx) => {
    if (/^\s*```/.test(text)) {
      fenceOpenLine = fenceOpenLine === -1 ? idx + 1 : -1;
    }
  });

  if (fenceOpenLine !== -1) {
    diagnostics.push({
      line: fenceOpenLine,
      column: 1,
      endColumn: 4,
      severity: 'warning',
      rule: 'unclosed-code-fence',
      message: 'Unclosed fenced code block (```)',
    });
  }

  return diagnostics;
}

/**
 * V8's JSON.parse error message carries a 0-based character `position`
 * (`"Unexpected token } in JSON at position 42"`) but not a line/column —
 * derive both by counting newlines in `code` up to that offset, the same
 * coordinate space Monaco's markers (and this file's other diagnostics) use.
 */
function positionToLineColumn(code: string, position: number): { line: number; column: number } {
  const upTo = code.slice(0, position);
  const lines = upTo.split('\n');
  return { line: lines.length, column: lines[lines.length - 1].length + 1 };
}

function lintJson(code: string): Diagnostic[] {
  if (code.trim() === '') return [];

  try {
    JSON.parse(code);
    return [];
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Invalid JSON';
    const positionMatch = /position (\d+)/.exec(message);
    const { line, column } = positionMatch
      ? positionToLineColumn(code, Number(positionMatch[1]))
      : { line: 1, column: 1 };

    return [
      {
        line,
        column,
        endColumn: column + 1,
        severity: 'error',
        rule: 'invalid-json',
        message,
      },
    ];
  }
}

/** Lints `code` for the given language, sorted by line then column. */
export function lintCode(language: EditorLanguage, code: string): Diagnostic[] {
  let diagnostics: Diagnostic[];
  if (language === 'python') {
    diagnostics = [...scanPythonStructure(code), ...lintPythonLines(code)];
  } else if (language === 'json') {
    diagnostics = lintJson(code);
  } else {
    diagnostics = lintMarkdown(code);
  }

  return diagnostics.sort((a, b) => a.line - b.line || a.column - b.column);
}
