import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Wand2, X } from 'lucide-react';
import Editor, { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api';
import 'monaco-editor/esm/vs/editor/editor.all';

import { Button } from '@/components/ui/button';
import { SchemaForm, type JsonSchema, type UiSchema } from '@/components/SchemaForm';

import { lintCode, type Diagnostic } from './codeLint';
import { formatCode } from './codeFormat';
import type { DiagramCanvasHandle } from './DiagramCanvasHandle';
import {
  EMPTY_JSON,
  formSchemaFileNamesFrom,
  formSchemaOpenFileContent,
  formSchemaTabForFile,
  schemaBaseName,
  type FormSchemaFileNames,
} from './formSchemaFiles';
import { FORM_SCHEMA_EXAMPLES, insertExample } from './formSchemaExamples';
import { M8FLOW_JSON_LANGUAGE, registerM8flowJsonLanguage } from './m8flowJsonLanguage';

loader.config({ monaco });

export type FormSchemaEditorSession = {
  /** Schema filename to open. Launch Editor always supplies one — either the
   * selected dropdown value, or a name derived from the user task. */
  fileName: string;
  /** When true (no schema was selected yet), a missing file is created
   * instead of shown as an error, and the filename is bound onto the task. */
  createIfMissing?: boolean;
  onReadFile: (fileName: string) => Promise<string>;
  onWriteFile: (fileName: string, content: string) => Promise<void>;
  onCreateFile: (fileName: string, content: string) => Promise<void>;
  onCommitted: (schemaFileName: string) => void;
};

export type FormSchemaEditorProps = {
  session: FormSchemaEditorSession;
  /** Modal is Launch Editor (overlay, debounce save). Page is the
   * `/modeler/*-schema.json` canvas (fills the route, page Save flushes). */
  variant?: 'modal' | 'page';
  onClose?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
};

type EditorTab = 'schema' | 'ui' | 'data' | 'examples';

const TABS: { id: EditorTab; label: string }[] = [
  { id: 'schema', label: 'JSON Schema' },
  { id: 'ui', label: 'UI Settings' },
  { id: 'data', label: 'Data View' },
  { id: 'examples', label: 'Examples' },
];

const JSON_SCHEMA_LEARN_MORE = 'https://json-schema.org/learn/getting-started-step-by-step';
const UI_SETTINGS_LEARN_MORE = 'https://rjsf-team.github.io/react-jsonschema-form/docs/';

const SAVE_DEBOUNCE_MS = 500;
const MARKER_OWNER = 'm8flow-form-json-lint';

function parseObject(text: string): Record<string, unknown> | null {
  try {
    const value = JSON.parse(text) as unknown;
    return value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function isNotFound(err: unknown): boolean {
  return typeof err === 'object' && err !== null && 'status' in err && (err as { status: number }).status === 404;
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

function FormJsonPane({
  label,
  fileName,
  description,
  learnMoreHref,
  learnMoreLabel,
  value,
  onChange,
}: {
  label: string;
  fileName: string;
  description: string;
  learnMoreHref?: string;
  learnMoreLabel?: string;
  value: string;
  onChange: (next: string) => void;
}) {
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof monaco | null>(null);
  const diagnostics = useMemo(() => lintCode('json', value), [value]);
  const errorCount = diagnostics.filter((diagnostic) => diagnostic.severity === 'error').length;
  const warningCount = diagnostics.length - errorCount;

  useEffect(() => {
    const editor = editorRef.current;
    const monacoApi = monacoRef.current;
    const model = editor?.getModel();
    if (editor && monacoApi && model) {
      monacoApi.editor.setModelMarkers(model, MARKER_OWNER, toMarkers(diagnostics));
    }
  }, [diagnostics]);

  registerM8flowJsonLanguage();

  const handleMount = (editor: monaco.editor.IStandaloneCodeEditor, monacoApi: typeof monaco) => {
    editorRef.current = editor;
    monacoRef.current = monacoApi;
    const model = editor.getModel();
    if (model) {
      monacoApi.editor.setModelMarkers(model, MARKER_OWNER, toMarkers(lintCode('json', value)));
    }
  };

  const handleFormat = () => {
    const formatted = formatCode('json', value);
    onChange(formatted);
    editorRef.current?.setValue(formatted);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <p className="flex-none px-4 pt-3 text-xs leading-relaxed text-muted-foreground">
        {description}{' '}
        {learnMoreHref && learnMoreLabel ? (
          <>
            <a
              href={learnMoreHref}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-foreground underline-offset-2 hover:underline"
            >
              {learnMoreLabel}
            </a>
            .
          </>
        ) : null}
      </p>
      <p className="flex-none px-4 pt-1 font-mono text-[11px] text-muted-foreground">{fileName}</p>
      <div className="flex flex-none items-center justify-between gap-3 px-4 py-2">
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
          language={M8FLOW_JSON_LANGUAGE}
          value={value}
          onChange={(next) => onChange(next ?? '')}
          onMount={handleMount}
          height="100%"
          options={{
            ariaLabel: `${label} editor`,
            glyphMargin: false,
            folding: true,
            lineNumbersMinChars: 2,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            fontSize: 13,
            tabSize: 2,
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
}

function ExamplesPane({
  onInsert,
}: {
  onInsert: (id: string) => void;
}) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
      <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
        If you are looking for a place to start, try adding these example fields to your form and
        changing them to meet your needs.
      </p>
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="py-2 pr-3 font-medium">Name</th>
            <th className="py-2 pr-3 font-medium">Description</th>
            <th className="py-2 font-medium">Insert</th>
          </tr>
        </thead>
        <tbody>
          {FORM_SCHEMA_EXAMPLES.map((example) => (
            <tr key={example.id} className="border-b border-border align-top">
              <td className="py-2 pr-3 font-medium text-foreground">{example.title}</td>
              <td className="py-2 pr-3 text-muted-foreground">{example.description}</td>
              <td className="py-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => onInsert(example.id)}
                >
                  Load
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const FormSchemaEditor = forwardRef<DiagramCanvasHandle, FormSchemaEditorProps>(
  function FormSchemaEditor(
    { session, variant = 'modal', onClose, onDirtyChange },
    ref,
  ) {
  const isPage = variant === 'page';
  const [baseName, setBaseName] = useState(schemaBaseName(session.fileName));
  const [names, setNames] = useState<FormSchemaFileNames | null>(
    formSchemaFileNamesFrom(session.fileName),
  );
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [tab, setTab] = useState<EditorTab>(formSchemaTabForFile(session.fileName));
  const [strSchema, setStrSchema] = useState('');
  const [strUi, setStrUi] = useState('');
  const [strData, setStrData] = useState('');
  const skipNextSave = useRef(true);
  const namesRef = useRef(names);
  const strSchemaRef = useRef(strSchema);
  const strUiRef = useRef(strUi);
  const strDataRef = useRef(strData);
  const savedSchemaRef = useRef('');
  const savedUiRef = useRef('');
  const savedDataRef = useRef('');
  namesRef.current = names;
  strSchemaRef.current = strSchema;
  strUiRef.current = strUi;
  strDataRef.current = strData;

  const snapshotSaved = (schema: string, ui: string, example: string) => {
    savedSchemaRef.current = schema;
    savedUiRef.current = ui;
    savedDataRef.current = example;
  };

  useImperativeHandle(
    ref,
    () => ({
      saveXML: async () => {
        const files = namesRef.current;
        const schema = strSchemaRef.current;
        const ui = strUiRef.current;
        const example = strDataRef.current;
        const baseline = { schema, ui, example };
        if (files) {
          await Promise.all([
            session.onWriteFile(files.schema, schema),
            session.onWriteFile(files.ui, ui),
            session.onWriteFile(files.example, example),
          ]);
          return {
            xml: formSchemaOpenFileContent(session.fileName, files, { schema, ui, example }),
            baseline,
          };
        }
        return { xml: schema, baseline };
      },
      markSaved: (baseline) => {
        const snap =
          baseline && typeof baseline === 'object' && 'schema' in baseline
            ? baseline
            : {
                schema: strSchemaRef.current,
                ui: strUiRef.current,
                example: strDataRef.current,
              };
        snapshotSaved(snap.schema, snap.ui, snap.example);
        const stillDirty =
          strSchemaRef.current !== snap.schema ||
          strUiRef.current !== snap.ui ||
          strDataRef.current !== snap.example;
        onDirtyChange?.(stillDirty);
        return stillDirty;
      },
    }),
    [session, onDirtyChange],
  );

  useEffect(() => {
    const files = formSchemaFileNamesFrom(session.fileName);
    let cancelled = false;

    async function openOrCreate() {
      try {
        const [schema, ui, example] = await Promise.all([
          session.onReadFile(files.schema),
          session.onReadFile(files.ui).catch(() => EMPTY_JSON),
          session.onReadFile(files.example).catch(() => EMPTY_JSON),
        ]);
        if (cancelled) return;
        skipNextSave.current = true;
        setNames(files);
        setBaseName(schemaBaseName(session.fileName));
        setTab(formSchemaTabForFile(session.fileName));
        setStrSchema(schema);
        setStrUi(ui);
        setStrData(example);
        snapshotSaved(schema, ui, example);
        setLoaded(true);
        onDirtyChange?.(false);
        if (session.createIfMissing) session.onCommitted(files.schema);
      } catch (err: unknown) {
        if (cancelled) return;
        if (!session.createIfMissing || !isNotFound(err)) {
          setLoadError(err instanceof Error ? err.message : 'Failed to load JSON schema file');
          return;
        }
        try {
          await session.onCreateFile(files.schema, EMPTY_JSON);
          await session.onCreateFile(files.ui, EMPTY_JSON);
          await session.onCreateFile(files.example, EMPTY_JSON);
          if (cancelled) return;
          skipNextSave.current = true;
          setNames(files);
          setBaseName(schemaBaseName(session.fileName));
          setTab(formSchemaTabForFile(session.fileName));
          setStrSchema(EMPTY_JSON);
          setStrUi(EMPTY_JSON);
          setStrData(EMPTY_JSON);
          snapshotSaved(EMPTY_JSON, EMPTY_JSON, EMPTY_JSON);
          setLoaded(true);
          onDirtyChange?.(false);
          session.onCommitted(files.schema);
        } catch (createErr: unknown) {
          if (cancelled) return;
          setLoadError(
            createErr instanceof Error ? createErr.message : 'Failed to create form files',
          );
        }
      }
    }

    void openOrCreate();
    return () => {
      cancelled = true;
    };
  }, [session]);

  useEffect(() => {
    if (!isPage || !loaded) return;
    const dirty =
      strSchema !== savedSchemaRef.current ||
      strUi !== savedUiRef.current ||
      strData !== savedDataRef.current;
    onDirtyChange?.(dirty);
  }, [isPage, loaded, strSchema, strUi, strData, onDirtyChange]);

  const flushModalWrites = useCallback(() => {
    const files = namesRef.current;
    if (!files || !loaded) return;
    const writes = [
      session.onWriteFile(files.schema, strSchemaRef.current),
      session.onWriteFile(files.ui, strUiRef.current),
      session.onWriteFile(files.example, strDataRef.current),
    ];
    void Promise.all(writes)
      .then(() => setSaveError(null))
      .catch((err: unknown) => {
        setSaveError(err instanceof Error ? err.message : 'Failed to save form files');
      });
  }, [loaded, session]);

  const pendingModalSaveRef = useRef(false);

  useEffect(() => {
    if (isPage || !names || !loaded) return undefined;
    if (skipNextSave.current) {
      skipNextSave.current = false;
      return undefined;
    }
    pendingModalSaveRef.current = true;
    const timer = window.setTimeout(() => {
      pendingModalSaveRef.current = false;
      flushModalWrites();
    }, SAVE_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      if (pendingModalSaveRef.current) {
        pendingModalSaveRef.current = false;
        flushModalWrites();
      }
    };
  }, [isPage, names, loaded, flushModalWrites, strSchema, strUi, strData]);

  const handleClose = useCallback(() => {
    if (pendingModalSaveRef.current) {
      pendingModalSaveRef.current = false;
      flushModalWrites();
    }
    onClose?.();
  }, [flushModalWrites, onClose]);

  useEffect(() => {
    if (isPage || !onClose) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isPage, onClose, handleClose]);

  const schemaObj = useMemo(() => parseObject(strSchema) as JsonSchema | null, [strSchema]);
  const uiObj = useMemo(() => parseObject(strUi) as UiSchema, [strUi]);
  const dataObj = useMemo(() => parseObject(strData), [strData]);
  const previewError = loaded
    ? !schemaObj
      ? 'Please check the JSON Schema for errors.'
      : !parseObject(strUi)
        ? 'Please check the UI Settings for errors.'
        : !dataObj
          ? 'Please check the Data View for errors.'
          : null
    : null;

  const handlePreviewChange = (next: Record<string, unknown>) => {
    setStrData(`${JSON.stringify(next, null, 2)}\n`);
  };

  const handleInsertExample = (id: string) => {
    const example = FORM_SCHEMA_EXAMPLES.find((item) => item.id === id);
    if (!example) return;
    const next = insertExample({ schema: strSchema, ui: strUi, data: strData }, example);
    skipNextSave.current = false;
    setStrSchema(next.schema);
    setStrUi(next.ui);
    setStrData(next.data);
    setTab('schema');
  };

  return (
    <div
      className={
        isPage
          ? 'flex size-full min-h-0 flex-col bg-card'
          : 'fixed inset-0 z-[1000] flex items-center justify-center bg-black/40 p-6'
      }
      role={isPage ? 'region' : 'dialog'}
      aria-modal={isPage ? undefined : true}
      aria-label="Edit JSON Schema"
    >
      <div
        className={
          isPage
            ? 'flex size-full min-h-0 flex-col overflow-hidden'
            : 'flex h-[85vh] w-full max-w-[1200px] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl'
        }
      >
        <div className="flex flex-none items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold text-foreground">
            Edit JSON Schema{baseName ? ` — ${baseName}` : ''}
          </h2>
          {!isPage && onClose ? (
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
          ) : null}
        </div>

        {!loaded ? (
          <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6">
            {loadError ? (
              <p className="text-sm text-destructive" role="alert">
                {loadError}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">Loading form schema…</p>
            )}
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="grid min-h-0 flex-1 grid-cols-1 divide-y divide-border md:grid-cols-2 md:divide-x md:divide-y-0">
              <div className="flex min-h-0 flex-col">
                <div className="flex flex-none gap-1 border-b border-border px-3 pt-2" role="tablist">
                  {TABS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      role="tab"
                      aria-selected={tab === item.id}
                      onClick={() => setTab(item.id)}
                      className={`rounded-t-md px-3 py-1.5 text-xs font-medium ${
                        tab === item.id
                          ? 'bg-muted text-foreground'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
                {tab === 'schema' ? (
                  <FormJsonPane
                    label="JSON Schema"
                    fileName={names?.schema ?? ''}
                    description="The JSON Schema describes the structure of the data you want to collect, and what validation rules should be applied to each field."
                    learnMoreHref={JSON_SCHEMA_LEARN_MORE}
                    learnMoreLabel="Read more"
                    value={strSchema}
                    onChange={setStrSchema}
                  />
                ) : null}
                {tab === 'ui' ? (
                  <FormJsonPane
                    label="UI Settings"
                    fileName={names?.ui ?? ''}
                    description="These UI Settings augment the JSON Schema, specifying how the web form should be displayed."
                    learnMoreHref={UI_SETTINGS_LEARN_MORE}
                    learnMoreLabel="Learn more"
                    value={strUi}
                    onChange={setStrUi}
                  />
                ) : null}
                {tab === 'data' ? (
                  <FormJsonPane
                    label="Data View"
                    fileName={names?.example ?? ''}
                    description="Data entered in the form to the right will appear below in the same way it will be provided in the Task Data. In order to initialize a form in the Workflow with preconfigured values or set up options for dynamic Dropdown lists, this data must be made available as Task Data variables."
                    value={strData}
                    onChange={setStrData}
                  />
                ) : null}
                {tab === 'examples' ? <ExamplesPane onInsert={handleInsertExample} /> : null}
              </div>
              <div className="flex min-h-0 flex-col overflow-y-auto p-5">
                <h3 className="mb-3 text-sm font-semibold text-foreground">Form preview</h3>
                {previewError ? (
                  <p className="text-sm text-destructive" role="alert">
                    {previewError}
                  </p>
                ) : schemaObj && dataObj ? (
                  <SchemaForm
                    schema={schemaObj}
                    uiSchema={uiObj}
                    value={dataObj}
                    onChange={handlePreviewChange}
                  />
                ) : null}
              </div>
            </div>
            {saveError ? (
              <p className="flex-none border-t border-border px-5 py-2 text-sm text-destructive" role="alert">
                {saveError}
              </p>
            ) : null}
            {!isPage && onClose ? (
              <div className="flex flex-none justify-start border-t border-border px-5 py-3">
                <Button type="button" variant="pill-cancel" size="pill" onClick={handleClose}>
                  Close
                </Button>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
});
