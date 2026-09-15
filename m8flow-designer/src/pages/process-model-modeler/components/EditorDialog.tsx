import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Wand2, X } from 'lucide-react';
import Editor, { loader } from '@monaco-editor/react';
import { Button } from '@/components/ui/button';
// `monaco-editor`'s default entry point (`editor.main.js`, what a bare
// `import * as monaco from 'monaco-editor'` resolves to) eagerly registers
// *every* bundled language — all ~90 basic languages plus the four "rich"
// languages (css/html/json/typescript) — regardless of which ones an app
// actually uses. `EditorLanguage` below is only 'python' | 'markdown' |
// 'json', so that barrel was responsible for the large majority of this
// app's single biggest chunk (see
// .scratch/m8flow-designer-optimization/assets/01-audit-findings.md,
// Finding 1: EditorDialog was 3.25 MB raw / 833 KB gzip).
//
// `editor.api` is the same core editor API surface (createMonacoBaseAPI +
// createMonacoEditorAPI + createMonacoLanguagesAPI) with zero languages
// registered — confirmed identical typings too (monaco-editor's own
// package.json "typings" field points at this exact same .d.ts either way,
// so no type-usage below needs to change). `editor.all` pulls in the
// language-independent editing UX (find/replace, folding, bracket matching,
// multicursor, hover, comment-toggling, etc.) that a full-featured code
// editor is expected to have — without it, the editor would still render
// and accept typing, but lose most of those affordances. Only the 3
// languages actually used get their own contribution import: python/
// markdown are lightweight "basic languages" (tokenizer only, no worker —
// see the loader.config comment below); json is a "rich" language with its
// own worker (jsonMode chunk, ~41 KB raw) — its worker isn't relied on here
// (codeLint.ts's JSON validation is our own `JSON.parse`-based linter, not
// Monaco's), it's imported purely for syntax highlighting/bracket-matching,
// same behavior as before.
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import 'monaco-editor/esm/vs/editor/editor.all';
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution';
import 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution';
import 'monaco-editor/esm/vs/language/json/monaco.contribution';

import type { ScriptUnitTestRunResult } from '@/lib/api';
import { lintCode, type Diagnostic, type EditorLanguage } from './codeLint';
import { formatCode } from './codeFormat';
import { ScriptUnitTestsPanel } from './ScriptUnitTestsPanel';
import type { ScriptUnitTestCase } from '../scriptUnitTests';

/**
 * Modal "Launch Editor" popup for the properties panel's task editors, built
 * to mirror spiffworkflow-frontend's script/markdown Dialogs: a Monaco editor
 * in a centered modal. bpmn-js-spiffworkflow's "Launch Editor" buttons only
 * `eventBus.fire('spiff.script.edit' | 'spiff.markdown.edit')` and wait for a
 * matching `*.update`; BpmnCanvas opens this dialog to answer them.
 *
 * Point Monaco at the locally-bundled `monaco-editor` (not the CDN) — same as
 * spiff's `loader.config({ monaco })`, so the editor works offline. No web
 * worker setup is needed: python/markdown have no Monaco language worker
 * (they tokenize on the main thread), and our linting is our own code, so the
 * marker/validation path never depends on a worker.
 *
 * Beyond spiff this adds linting (codeLint.ts) shown as Monaco markers + a
 * clickable problems list, a Format action (codeFormat.ts), and a Save that
 * is gated while any error-severity problem remains — the "validation" step.
 */
loader.config({ monaco });

export type EditorDialogSession = {
  /** Heading (e.g. "Edit Script — Approve request"). */
  title: string;
  /** Value pulled from the diagram when the editor was launched. */
  value: string;
  language: EditorLanguage;
  /** Commits the edited value back to the diagram (fires the modeler's `*.update`). */
  onSave: (value: string) => void;
  /**
   * Script-task Launch Editor only (`bpmn:script`). Pre/post and instructions
   * omit this — the old canvas did not test those from the dialog. Script
   * assist stays out.
   */
  unitTests?: {
    cases: ScriptUnitTestCase[];
    onCommit: (cases: ScriptUnitTestCase[]) => void;
    onRun: (input: {
      python_script: string;
      input_json: Record<string, unknown>;
      expected_output_json: Record<string, unknown>;
    }) => Promise<ScriptUnitTestRunResult>;
  };
};

export type EditorDialogProps = {
  session: EditorDialogSession;
  onClose: () => void;
};

const MARKER_OWNER = 'm8flow-lint';

function toMarkers(diagnostics: Diagnostic[]): monaco.editor.IMarkerData[] {
  return diagnostics.map((diagnostic) => ({
    startLineNumber: diagnostic.line,
    startColumn: diagnostic.column,
    endLineNumber: diagnostic.line,
    endColumn: diagnostic.endColumn,
    message: `${diagnostic.message} (${diagnostic.rule})`,
    severity:
      diagnostic.severity === 'error' ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
  }));
}

export function EditorDialog({ session, onClose }: EditorDialogProps) {
  const [draft, setDraft] = useState(session.value);
  const [tab, setTab] = useState<'script' | 'tests'>('script');
  const [unitTestCases, setUnitTestCases] = useState<ScriptUnitTestCase[]>(
    session.unitTests?.cases ?? [],
  );
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof monaco | null>(null);

  // Re-seed whenever a new launch happens (fresh session object per launch).
  useEffect(() => {
    setDraft(session.value);
    setTab('script');
    setUnitTestCases(session.unitTests?.cases ?? []);
  }, [session]);

  const diagnostics = useMemo(() => lintCode(session.language, draft), [session.language, draft]);
  const errorCount = diagnostics.filter((diagnostic) => diagnostic.severity === 'error').length;
  const warningCount = diagnostics.length - errorCount;
  const canSave = errorCount === 0;

  // Keep Monaco's squiggles in sync with the linter.
  useEffect(() => {
    const editor = editorRef.current;
    const monacoApi = monacoRef.current;
    const model = editor?.getModel();
    if (editor && monacoApi && model) {
      monacoApi.editor.setModelMarkers(model, MARKER_OWNER, toMarkers(diagnostics));
    }
  }, [diagnostics]);

  // Close on Escape (matches modal expectations).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const handleMount = (editor: monaco.editor.IStandaloneCodeEditor, monacoApi: typeof monaco) => {
    editorRef.current = editor;
    monacoRef.current = monacoApi;
    const model = editor.getModel();
    if (model) {
      monacoApi.editor.setModelMarkers(model, MARKER_OWNER, toMarkers(lintCode(session.language, draft)));
    }
  };

  const handleFormat = () => {
    const formatted = formatCode(session.language, draft);
    setDraft(formatted);
    editorRef.current?.setValue(formatted);
  };

  const handleSave = () => {
    if (!canSave) return;
    session.unitTests?.onCommit(unitTestCases);
    session.onSave(draft);
    onClose();
  };

  const goToDiagnostic = (diagnostic: Diagnostic) => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.revealLineInCenter(diagnostic.line);
    editor.setPosition({ lineNumber: diagnostic.line, column: diagnostic.column });
    editor.focus();
  };

  return (
    <div
      // z-index must clear bpmn-js's context pad / palette (diagram-js uses up
      // to z-index 200), which otherwise renders in front of the modal.
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 p-6"
      role="dialog"
      aria-modal="true"
      aria-label={session.title}
    >
      <div className="flex h-[80vh] w-full max-w-[1100px] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex flex-none items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold text-foreground">{session.title}</h2>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            title="Close editor"
            aria-label="Close editor"
            className="rounded-md text-muted-foreground"
          >
            <X className="size-4" strokeWidth={2} />
          </Button>
        </div>

        {session.unitTests ? (
          <div role="tablist" aria-label="Script editor sections" className="flex flex-none gap-1 border-b border-border px-5">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'script'}
              className={`border-b-2 px-3 py-2 text-xs font-medium ${
                tab === 'script'
                  ? 'border-foreground text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => setTab('script')}
            >
              Script
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'tests'}
              className={`border-b-2 px-3 py-2 text-xs font-medium ${
                tab === 'tests'
                  ? 'border-foreground text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
              onClick={() => setTab('tests')}
            >
              Unit tests
            </button>
          </div>
        ) : null}

        {tab === 'script' ? (
        <>
        <div className="flex flex-none items-center justify-between gap-3 border-b border-border px-5 py-2">
          {/* Not converted to Button: no existing variant matches without a
              style compromise (border + no background + rounded-md, vs.
              every Button variant either adding a background or a different
              radius), and this shape isn't duplicated elsewhere — see this
              ticket's resolution. */}
          <button
            type="button"
            onClick={handleFormat}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted"
          >
            <Wand2 className="size-3.5" strokeWidth={2} />
            Format
          </button>
          <span
            role="status"
            className={`inline-flex items-center gap-1.5 text-xs font-medium ${
              errorCount > 0
                ? 'text-destructive'
                : warningCount > 0
                  ? 'text-amber-600'
                  : 'text-muted-foreground'
            }`}
          >
            {errorCount > 0 ? (
              <AlertCircle className="size-3.5" strokeWidth={2} />
            ) : warningCount > 0 ? (
              <AlertTriangle className="size-3.5" strokeWidth={2} />
            ) : (
              <CheckCircle2 className="size-3.5" strokeWidth={2} />
            )}
            {diagnostics.length === 0
              ? 'No problems'
              : `${errorCount} error${errorCount === 1 ? '' : 's'}, ${warningCount} warning${
                  warningCount === 1 ? '' : 's'
                }`}
          </span>
        </div>

        <div className="min-h-0 flex-1">
          <Editor
            language={session.language}
            value={draft}
            onChange={(value) => setDraft(value ?? '')}
            onMount={handleMount}
            height="100%"
            options={{
              glyphMargin: false,
              folding: session.language !== 'python',
              lineNumbersMinChars: 2,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              fontSize: 13,
              tabSize: 4,
              renderWhitespace: 'trailing',
            }}
          />
        </div>

        {diagnostics.length > 0 ? (
          <ul className="max-h-32 flex-none divide-y divide-border overflow-y-auto border-t border-border text-xs">
            {diagnostics.map((diagnostic, index) => (
              <li key={`${diagnostic.line}-${diagnostic.column}-${diagnostic.rule}-${index}`}>
                <button
                  type="button"
                  onClick={() => goToDiagnostic(diagnostic)}
                  className="flex w-full items-center gap-2 px-5 py-1.5 text-left hover:bg-muted"
                >
                  {diagnostic.severity === 'error' ? (
                    <AlertCircle className="size-3.5 flex-none text-destructive" strokeWidth={2} />
                  ) : (
                    <AlertTriangle className="size-3.5 flex-none text-amber-600" strokeWidth={2} />
                  )}
                  <span className="font-mono text-muted-foreground">Ln {diagnostic.line}</span>
                  <span className="text-foreground">{diagnostic.message}</span>
                  <span className="text-muted-foreground">({diagnostic.rule})</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        </>
        ) : session.unitTests ? (
          <ScriptUnitTestsPanel
            pythonScript={draft}
            cases={unitTestCases}
            onCasesChange={setUnitTestCases}
            onRun={session.unitTests.onRun}
          />
        ) : null}

        <div className="flex flex-none items-center justify-between gap-2 border-t border-border px-5 py-3">
          <span className="text-xs text-destructive">
            {canSave ? '' : `Fix ${errorCount} error${errorCount === 1 ? '' : 's'} before saving.`}
          </span>
          <div className="flex gap-2">
            <Button type="button" variant="pill-cancel" size="pill" onClick={onClose}>
              Cancel
            </Button>
            <Button type="button" variant="pill-info" size="pill" onClick={handleSave} disabled={!canSave}>
              Save
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
