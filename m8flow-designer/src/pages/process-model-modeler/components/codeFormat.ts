/**
 * Safe, deterministic auto-format for the "Launch Editor" popup's Format
 * button. Pairs with codeLint.ts — it fixes the whitespace/format-class
 * warnings the linter raises, without reordering or rewriting code (no real
 * Black/Prettier — that would need a WASM/backend engine; this is the safe
 * client-side subset).
 */
import type { EditorLanguage } from './codeLint';

function formatPython(code: string): string {
  if (code.trim() === '') return '';

  const withSpaces = code.replace(/\t/g, '    '); // tabs → 4 spaces
  const trimmed = withSpaces
    .split('\n')
    .map((line) => line.replace(/[ \t]+$/, '')) // strip trailing whitespace
    .join('\n');
  const collapsed = trimmed.replace(/\n{3,}/g, '\n\n'); // at most one blank line run

  return `${collapsed.replace(/\n+$/, '')}\n`; // exactly one trailing newline
}

function formatMarkdown(code: string): string {
  if (code.trim() === '') return '';

  // Markdown keeps trailing spaces (they encode hard line breaks) and tabs
  // (code blocks) — only blank-line runs and the final newline are normalized.
  const collapsed = code.replace(/\n{3,}/g, '\n\n');
  return `${collapsed.replace(/\n+$/, '')}\n`;
}

function formatJson(code: string): string {
  if (code.trim() === '') return '';
  try {
    // Invalid JSON is left untouched — codeLint.ts's `invalid-json` diagnostic
    // already surfaces the problem, and EditorDialog blocks Save on it; this
    // just avoids silently discarding whatever the user typed.
    return `${JSON.stringify(JSON.parse(code), null, 2)}\n`;
  } catch {
    return code;
  }
}

export function formatCode(language: EditorLanguage, code: string): string {
  if (language === 'python') return formatPython(code);
  if (language === 'json') return formatJson(code);
  return formatMarkdown(code);
}
