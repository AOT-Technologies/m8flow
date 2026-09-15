/**
 * Monaco host for process-modeler files that are not BPMN or DMN — JSON and
 * markdown today. Implements DiagramCanvasHandle so the page-level Save /
 * Download / dirty / Cmd+S chrome works the same as BpmnCanvas / DmnCanvas.
 *
 * JSON highlighting uses the custom `m8flow-json` tokenizer (not Monaco's
 * built-in `json` language) — the json worker crashes under Vite. Form-schema
 * companions (`*-schema.json` and siblings) use FormSchemaCanvas instead;
 * this canvas is generic `/modeler/*.json` and `/modeler/*.md`.
 */
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Wand2 } from 'lucide-react';
import Editor, { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import 'monaco-editor/esm/vs/editor/editor.all';
import 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution';

import { lintCode, type Diagnostic, type EditorLanguage } from './codeLint';
import { formatCode } from './codeFormat';
import type { DiagramCanvasHandle } from './DiagramCanvasHandle';
import { M8FLOW_JSON_LANGUAGE, registerM8flowJsonLanguage } from './m8flowJsonLanguage';

loader.config({ monaco });

export type TextFileCanvasProps = {
  fileName: string;
  xml: string;
  onDirtyChange?: (dirty: boolean) => void;
};

const MARKER_OWNER = 'm8flow-text-file-lint';

function lintLanguageForFile(fileName: string): EditorLanguage | null {
  const lower = fileName.toLowerCase();
  if (lower.endsWith('.md')) return 'markdown';
  if (lower.endsWith('.json')) return 'json';
  return null;
}

function editorLanguageForFile(fileName: string): string {
  const lower = fileName.toLowerCase();
  if (lower.endsWith('.md')) return 'markdown';
  if (lower.endsWith('.json')) return M8FLOW_JSON_LANGUAGE;
  return 'plaintext';
}

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

export const TextFileCanvas = forwardRef<DiagramCanvasHandle, TextFileCanvasProps>(
  function TextFileCanvas({ fileName, xml, onDirtyChange }, ref) {
    const [value, setValue] = useState(xml);
    const valueRef = useRef(xml);
    const savedRef = useRef(xml);
    const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
    const monacoRef = useRef<typeof monaco | null>(null);

    const lintLanguage = lintLanguageForFile(fileName);
    const diagnostics = useMemo(
      () => (lintLanguage ? lintCode(lintLanguage, value) : []),
      [lintLanguage, value],
    );
    const errorCount = diagnostics.filter((diagnostic) => diagnostic.severity === 'error').length;
    const warningCount = diagnostics.length - errorCount;

    useImperativeHandle(
      ref,
      () => ({
        saveXML: async () => {
          const xml = valueRef.current;
          return { xml, baseline: xml };
        },
        markSaved: (baseline) => {
          const saved = typeof baseline === 'string' ? baseline : valueRef.current;
          savedRef.current = saved;
          const stillDirty = valueRef.current !== saved;
          onDirtyChange?.(stillDirty);
          return stillDirty;
        },
      }),
      [onDirtyChange],
    );

    useEffect(() => {
      valueRef.current = xml;
      savedRef.current = xml;
      setValue(xml);
      onDirtyChange?.(false);
    }, [xml, onDirtyChange]);

    useEffect(() => {
      const editor = editorRef.current;
      const monacoApi = monacoRef.current;
      const model = editor?.getModel();
      if (editor && monacoApi && model) {
        monacoApi.editor.setModelMarkers(model, MARKER_OWNER, toMarkers(diagnostics));
      }
    }, [diagnostics]);

    const handleChange = (next: string) => {
      valueRef.current = next;
      setValue(next);
      onDirtyChange?.(next !== savedRef.current);
    };

    const handleMount = (editor: monaco.editor.IStandaloneCodeEditor, monacoApi: typeof monaco) => {
      editorRef.current = editor;
      monacoRef.current = monacoApi;
      registerM8flowJsonLanguage();
      const model = editor.getModel();
      if (model) {
        monacoApi.editor.setModelMarkers(model, MARKER_OWNER, toMarkers(diagnostics));
      }
    };

    const handleFormat = () => {
      if (!lintLanguage) return;
      const formatted = formatCode(lintLanguage, value);
      handleChange(formatted);
      editorRef.current?.setValue(formatted);
    };

    registerM8flowJsonLanguage();

    return (
      <div className="flex size-full min-h-0 flex-col">
        {lintLanguage ? (
          <div className="flex flex-none items-center justify-between gap-3 border-b border-border px-4 py-2">
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
        ) : null}
        <div className="min-h-0 flex-1">
          <Editor
            language={editorLanguageForFile(fileName)}
            value={value}
            onChange={(next) => handleChange(next ?? '')}
            onMount={handleMount}
            height="100%"
            options={{
              ariaLabel: 'File editor',
              glyphMargin: false,
              folding: true,
              lineNumbersMinChars: 2,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              fontSize: 13,
              tabSize: lintLanguage === 'json' ? 2 : 4,
              renderWhitespace: 'trailing',
            }}
          />
        </div>
        {diagnostics.length > 0 ? (
          <ul className="max-h-24 flex-none divide-y divide-border overflow-y-auto border-t border-border text-xs">
            {diagnostics.map((diagnostic, index) => (
              <li key={`${diagnostic.line}-${diagnostic.column}-${diagnostic.rule}-${index}`}>
                <p className="flex items-center gap-2 px-4 py-1.5">
                  {diagnostic.severity === 'error' ? (
                    <AlertCircle className="size-3.5 flex-none text-destructive" strokeWidth={2} />
                  ) : (
                    <AlertTriangle className="size-3.5 flex-none text-amber-600" strokeWidth={2} />
                  )}
                  <span>
                    Line {diagnostic.line}: {diagnostic.message}
                  </span>
                </p>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  },
);
