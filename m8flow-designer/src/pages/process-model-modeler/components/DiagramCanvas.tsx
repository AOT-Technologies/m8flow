import { forwardRef, lazy, Suspense } from 'react';

import type { BpmnCanvasFile, BpmnCanvasConnectorProfilePicker, BpmnCanvasServiceTaskOperator } from './BpmnCanvas';
import type { CallActivitySearchProcessModel } from './CallActivitySearchDialog';
import { isFormSchemaFile } from './formSchemaFiles';
import type { DiagramCanvasHandle } from './DiagramCanvasHandle';
import type { ScriptUnitTestRunResult } from '@/lib/api';

// Lazy, not static, imports: BpmnCanvas and DmnCanvas pull in bpmn-js and
// dmn-js respectively — two large, independent library trees that were
// previously *both* eagerly bundled and loaded together regardless of which
// file type was actually open (confirmed live: opening a .bpmn file still
// fetched dmn-js's own Modeler chunk). That's not just dead weight —
// dmn-js bundles its own copy of Inferno, and having it loaded alongside
// bpmn-js-properties-panel's Preact-based rendering on the same page is
// what caused a real, reproducible bug: clicking a properties-panel
// section header to expand it crashed with `Cannot add property __, object
// is not extensible` (two virtual-DOM libraries' internal DOM-node markers
// colliding) — confirmed fixed by no longer loading the other library's
// chunk for the file type not in use. TextFileCanvas is lazy for the same
// reason: opening a BPMN file must not pull Monaco.
const BpmnCanvas = lazy(() =>
  import('./BpmnCanvas').then((module) => ({ default: module.BpmnCanvas })),
);
const DmnCanvas = lazy(() => import('./DmnCanvas').then((module) => ({ default: module.DmnCanvas })));
const TextFileCanvas = lazy(() =>
  import('./TextFileCanvas').then((module) => ({ default: module.TextFileCanvas })),
);
const FormSchemaCanvas = lazy(() =>
  import('./FormSchemaCanvas').then((module) => ({ default: module.FormSchemaCanvas })),
);

/** Which canvas hosts a process-modeler file. JSON and markdown must not go
 * through BpmnCanvas.importXML — they are text, not BPMN. Form-schema
 * companions share FormSchemaEditor with User Task Launch Editor. */
export function modelerCanvasKind(fileName: string): 'bpmn' | 'dmn' | 'form' | 'text' {
  const lower = fileName.toLowerCase();
  if (lower.endsWith('.dmn')) return 'dmn';
  if (isFormSchemaFile(fileName)) return 'form';
  if (lower.endsWith('.json') || lower.endsWith('.md')) return 'text';
  return 'bpmn';
}

export type DiagramCanvasProps = {
  fileName: string;
  xml: string;
  onDirtyChange?: (dirty: boolean) => void;
  /** BPMN-only (DmnCanvas doesn't use these yet) — see BpmnCanvasProps. */
  files?: BpmnCanvasFile[];
  onReadFile?: (fileName: string) => Promise<string>;
  onWriteFile?: (fileName: string, content: string) => Promise<void>;
  onCreateFile?: (fileName: string, content: string) => Promise<void>;
  onFilesChanged?: () => void;
  onLaunchDmnEditor?: (fileName: string) => void;
  processModels?: CallActivitySearchProcessModel[];
  onLaunchCallActivityEditor?: (processModelId: string) => void;
  onFetchServiceTaskOperators?: () => Promise<BpmnCanvasServiceTaskOperator[]>;
  onFetchConnectorProfiles?: (connectorType: string) => Promise<BpmnCanvasConnectorProfilePicker>;
  onRunScriptUnitTest?: (input: {
    python_script: string;
    input_json: Record<string, unknown>;
    expected_output_json: Record<string, unknown>;
  }) => Promise<ScriptUnitTestRunResult>;
};

/** Dispatches to the BPMN, DMN, form-schema, or text canvas by file type. */
export const DiagramCanvas = forwardRef<DiagramCanvasHandle, DiagramCanvasProps>(
  function DiagramCanvas(
    {
      fileName,
      xml,
      onDirtyChange,
      files,
      onReadFile,
      onWriteFile,
      onCreateFile,
      onFilesChanged,
      onLaunchDmnEditor,
      processModels,
      onLaunchCallActivityEditor,
      onFetchServiceTaskOperators,
      onFetchConnectorProfiles,
      onRunScriptUnitTest,
    },
    ref,
  ) {
    const kind = modelerCanvasKind(fileName);
    const formIo = onReadFile && onWriteFile && onCreateFile;
    return (
      <Suspense fallback={null}>
        {kind === 'dmn' ? (
          <DmnCanvas ref={ref} xml={xml} onDirtyChange={onDirtyChange} />
        ) : kind === 'form' && formIo ? (
          <FormSchemaCanvas
            ref={ref}
            fileName={fileName}
            onDirtyChange={onDirtyChange}
            onReadFile={onReadFile}
            onWriteFile={onWriteFile}
            onCreateFile={onCreateFile}
          />
        ) : kind === 'text' || kind === 'form' ? (
          <TextFileCanvas ref={ref} fileName={fileName} xml={xml} onDirtyChange={onDirtyChange} />
        ) : (
          <BpmnCanvas
            ref={ref}
            xml={xml}
            onDirtyChange={onDirtyChange}
            files={files}
            onReadFile={onReadFile}
            onWriteFile={onWriteFile}
            onCreateFile={onCreateFile}
            onFilesChanged={onFilesChanged}
            onLaunchDmnEditor={onLaunchDmnEditor}
            processModels={processModels}
            onLaunchCallActivityEditor={onLaunchCallActivityEditor}
            onFetchServiceTaskOperators={onFetchServiceTaskOperators}
            onFetchConnectorProfiles={onFetchConnectorProfiles}
            onRunScriptUnitTest={onRunScriptUnitTest}
          />
        )}
      </Suspense>
    );
  },
);
