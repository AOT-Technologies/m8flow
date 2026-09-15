/**
 * Thin React host shell around `m8flow-bpmn/lib/Modeler` (camunda-bpmn-js
 * shaped). Engine modules, palette, zoom chrome, panel wiring, and CSS live
 * in the package. This file owns containers, Spiff→dialog/routing/HTTP
 * binding, panel toggle, and dirty/save UI.
 */
import { forwardRef, lazy, Suspense, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import Modeler from 'm8flow-bpmn/lib/Modeler';
import {
  CONNECTOR_PROFILES_REQUESTED,
  CONNECTOR_PROFILES_RETURNED,
} from 'm8flow-bpmn/lib/features/connectorProfileCatalog';

import { CallActivitySearchDialog } from './CallActivitySearchDialog';
import type { CallActivitySearchProcessModel, CallActivitySearchSession } from './CallActivitySearchDialog';
import type { EditorDialogSession } from './EditorDialog';
import type { FormSchemaEditorSession } from './FormSchemaEditor';
import type { DiagramCanvasHandle } from './DiagramCanvasHandle';
import { formSchemaBaseFromLabel, SCHEMA_SUFFIX } from './formSchemaFiles';
import {
  applyScriptUnitTestsToElement,
  readScriptUnitTests,
  type ScriptUnitTestCase,
} from '../scriptUnitTests';
import type { ScriptUnitTestRunResult } from '@/lib/api';

// Lazy — the "Launch Editor" popup pulls in Monaco (a large, independent
// library tree). Loading it only when a task's script/instructions editor is
// actually opened keeps it out of the initial BpmnCanvas chunk.
const EditorDialog = lazy(() =>
  import('./EditorDialog').then((module) => ({ default: module.EditorDialog })),
);
const FormSchemaEditor = lazy(() =>
  import('./FormSchemaEditor').then((module) => ({ default: module.FormSchemaEditor })),
);

// Human-readable headings for the script editors bpmn-js-spiffworkflow can
// launch (keyed by the `scriptType` it puts on the `spiff.script.edit` event).
const SCRIPT_EDITOR_TITLES: Record<string, string> = {
  'bpmn:script': 'Edit Script',
  'spiffworkflow:PreScript': 'Edit Pre-Script',
  'spiffworkflow:PostScript': 'Edit Post-Script',
};

// Walks a moddle element's own $parent chain up to bpmn:Definitions — same
// logic bpmn-js-spiffworkflow's own helpers.js getRoot() uses (mirrored, not
// imported). Used by the Data Store Reference wiring below (host Spiff answer).
function findDefinitionsRoot(businessObject: any): any {
  if (businessObject.$type === 'bpmn:Definitions') return businessObject;
  if (businessObject.$parent) return findDefinitionsRoot(businessObject.$parent);
  return null;
}

function findDeclaredDataStores(modeler: any): Array<{ id: string; name: string; clz: string; type: string }> {
  const canvas = modeler.get('canvas');
  const rootElement = canvas.getRootElement();
  const definitions = findDefinitionsRoot(rootElement.businessObject);
  const rootElements: any[] = definitions?.rootElements ?? [];
  return rootElements
    .filter((el) => el.$type === 'bpmn:DataStore')
    .map((ds) => ({ id: ds.id, name: ds.name || ds.id, clz: ds.name || ds.id, type: 'DataStore' }));
}

/** Minimal shape BpmnCanvas needs from a process model's file list — kept
 * this narrow (not api.ts's ProcessModelDetailFile) so this file stays
 * decoupled from the host page's API types. */
export type BpmnCanvasFile = { name: string };

export type BpmnCanvasProps = {
  xml: string;
  /** Fires whenever the diagram's dirty state changes (an edit after the
   * last load/save, or a return to the last-saved command-stack position
   * via undo). */
  onDirtyChange?: (dirty: boolean) => void;
  /** This diagram's own process model's files — answers the User Task
   * properties panel's JSON Schema Filename dropdown
   * (`spiff.json_schema_files.requested`), filtered to `*-schema.json` the
   * same way m8flow-frontend's TemplateFileDiagramPage does. */
  files?: BpmnCanvasFile[];
  /** Reads/writes a file by name in this same process model, for the JSON
   * Schema field's "Launch Editor" round trip (`spiff.file.edit`). Launch
   * Editor no-ops without read+write+create (no model context to persist
   * against). Empty filename is valid — it opens the create-files flow. */
  onReadFile?: (fileName: string) => Promise<string>;
  onWriteFile?: (fileName: string, content: string) => Promise<void>;
  onCreateFile?: (fileName: string, content: string) => Promise<void>;
  /** After Create Files, refresh this model's file list so the JSON Schema
   * Filename dropdown includes the new `*-schema.json`. */
  onFilesChanged?: () => void;
  /** Business Rule Task's "Launch Editor" (`spiff.dmn.edit`) — navigates to
   * the selected .dmn file's own modeler page. Fire-and-forget (the button
   * doesn't wait on a response event, per bpmn-js-spiffworkflow's own
   * SpiffExtensionLaunchButton: no `listenEvent` is configured for this one,
   * unlike the JSON Schema field's Launch Editor). No-ops if omitted. */
  onLaunchDmnEditor?: (fileName: string) => void;
  /** Every process model in this tenant — feeds Call Activity's "Search"
   * button (`spiff.callactivity.search`), which searches across models
   * (unlike JSON Schema/DMN, which only search *this* model's own files). */
  processModels?: CallActivitySearchProcessModel[];
  /** Call Activity's "Launch Editor" (`spiff.callactivity.edit`) — navigates
   * to the called process model's own modeler page. Also fire-and-forget,
   * same as onLaunchDmnEditor. */
  onLaunchCallActivityEditor?: (processModelId: string) => void;
  /** Service Task's connector operator dropdown (`spiff.service_tasks.requested`).
   * Unlike Phases 1-3's props (already-loaded data or a per-tenant list
   * fetched once up front), this is a genuine on-demand async fetch — the
   * connector catalog is only needed the first time a Service Task's group
   * is opened. */
  onFetchServiceTaskOperators?: () => Promise<BpmnCanvasServiceTaskOperator[]>;
  /** Service Task Config tab profile picker (`m8flow.connector_profiles.requested`).
   * Active profiles only (`include_inactive=false`). Viewer/reviewer can read. */
  onFetchConnectorProfiles?: (connectorType: string) => Promise<BpmnCanvasConnectorProfilePicker>;
  /**
   * Script-task Launch Editor unit-test Run. Ad-hoc body (current editor
   * script + JSON cases), not a stored `unit_test_id` — the diagram may be
   * unsaved. Omit on templates; pre/post editors never call this.
   */
  onRunScriptUnitTest?: (input: {
    python_script: string;
    input_json: Record<string, unknown>;
    expected_output_json: Record<string, unknown>;
  }) => Promise<ScriptUnitTestRunResult>;
};

export type BpmnCanvasServiceTaskOperator = {
  id: string;
  parameters: { id: string; type: string }[];
};

export type BpmnCanvasConnectorProfilePicker = {
  profiles: { profile_name: string; display_name: string }[];
  hiddenFieldIds: string[];
  supportsProfiles: boolean;
};

export const BpmnCanvas = forwardRef<DiagramCanvasHandle, BpmnCanvasProps>(function BpmnCanvas(
  {
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
  const canvasRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  // No type declarations ship for BpmnModeler + these constructor options
  // together (additionalModules/moddleExtensions are typed `any` upstream);
  // `any` here is the honest type, not a shortcut.
  const [modeler, setModeler] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  // Active "Launch Editor" popup session (script / instructions), or null when
  // no editor is open. Answers bpmn-js-spiffworkflow's `spiff.*.edit` events
  // with a Monaco modal (EditorDialog), mirroring spiffworkflow-frontend.
  const [editorSession, setEditorSession] = useState<EditorDialogSession | null>(null);
  // Active Call Activity "Search" popup, or null when closed — same pattern
  // as editorSession, answering spiff.callactivity.search.
  const [callActivitySearchSession, setCallActivitySearchSession] =
    useState<CallActivitySearchSession | null>(null);
  const [formEditorSession, setFormEditorSession] = useState<FormSchemaEditorSession | null>(null);
  // Dirty-tracking follows the standard diagram-js pattern: record the
  // command-stack index at the last load/save, and compare against the
  // current index (not just "has anything changed", so undo-back-to-saved
  // correctly reports clean again). A ref, not state — it's read inside an
  // event handler, not rendered.
  const savedStackIndexRef = useRef(-1);

  // The construction effect below has an empty dep array (see its own
  // comment for why), so it can't close over `files`/`onReadFile`/
  // `onWriteFile` directly — they'd be frozen at their first-render values.
  // A ref updated every render (same pattern as m8flow-frontend's
  // useDiagramModeler.ts callbacksRef) keeps the event listeners reading
  // live values without re-mounting the whole modeler on every prop change.
  const propsRef = useRef({
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
  });
  useEffect(() => {
    propsRef.current = {
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
    };
  });

  useImperativeHandle(ref, () => ({
    saveXML: async () => {
      if (!modeler) throw new Error('Modeler not ready');
      const baseline = modeler.get('commandStack')._stackIdx as number;
      const { xml: savedXml } = await modeler.saveXML({ format: true });
      return { xml: savedXml as string, baseline };
    },
    markSaved: (baseline) => {
      if (!modeler) return false;
      const savedIdx = typeof baseline === 'number' ? baseline : modeler.get('commandStack')._stackIdx;
      savedStackIndexRef.current = savedIdx;
      const stillDirty = modeler.get('commandStack')._stackIdx !== savedIdx;
      onDirtyChange?.(stillDirty);
      return stillDirty;
    },
  }), [modeler, onDirtyChange]);

  // Construction and import are deliberately two effects, not one: React 18
  // StrictMode's dev-mode double-invoke otherwise races an in-flight
  // importXML() against destroy(), crashing bpmn-js's own import pipeline.
  // See the recipe doc above for the full explanation.
  useEffect(() => {
    if (!canvasRef.current || !panelRef.current) return undefined;

    const instance = new (Modeler as any)({
      container: canvasRef.current,
      keyboard: { bindTo: document },
      propertiesPanel: { parent: panelRef.current },
    });

    // Answer the properties panel's "Launch Editor" buttons inline (docked
    // panel below the canvas) rather than as a popup. The buttons only
    // `eventBus.fire('spiff.script.edit' | 'spiff.markdown.edit')` and then
    // `eventBus.once()` on the matching `*.update`, so committing an edit is
    // just firing that update back on the event bus the button handed us.
    instance.on('spiff.script.edit', (event: any) => {
      const base = SCRIPT_EDITOR_TITLES[event.scriptType] ?? 'Edit Script';
      const name = event.element?.businessObject?.name;
      const run = propsRef.current.onRunScriptUnitTest;
      const isBpmnScript = event.scriptType === 'bpmn:script';
      const unitTests =
        isBpmnScript && run && event.element
          ? {
              cases: readScriptUnitTests(event.element),
              onCommit: (cases: ScriptUnitTestCase[]) => {
                applyScriptUnitTestsToElement({
                  element: event.element,
                  cases,
                  moddle: instance.get('moddle'),
                  modeling: instance.get('modeling'),
                });
              },
              onRun: run,
            }
          : undefined;
      setEditorSession({
        title: name ? `${base} — ${name}` : base,
        value: event.script ?? '',
        language: 'python',
        onSave: (value) =>
          event.eventBus.fire('spiff.script.update', { scriptType: event.scriptType, script: value }),
        unitTests,
      });
    });
    instance.on('spiff.markdown.edit', (event: any) => {
      setEditorSession({
        title: 'Edit Instructions',
        value: event.value ?? '',
        language: 'markdown',
        // bpmn-js-spiffworkflow's Launch button already `once`s
        // `spiff.markdown.update` and writes `spiffworkflow:InstructionsForEndUser`
        // (or GuestConfirmation) via setExtensionValue — the engine reads that
        // extension body. Fall back to the same event name the old canvas
        // hardcoded if listenEvent is missing.
        onSave: (value) =>
          event.eventBus.fire(event.listenEvent || 'spiff.markdown.update', { value }),
      });
    });

    // JSON Schema Filename dropdown (User Task "Web Form" group) — answered
    // from this diagram's own process model file list, filtered the same
    // way m8flow-frontend's TemplateFileDiagramPage.onJsonSchemaFilesRequested
    // does. No backend route needed: ProcessModelModelerPage already fetches
    // the model's file list for the breadcrumb and passes it straight through.
    instance.on('spiff.json_schema_files.requested', (event: any) => {
      const modelFiles = propsRef.current.files ?? [];
      const options = modelFiles
        .filter((f) => /[-.]schema\.json$/i.test(f.name))
        .map((f) => ({ label: f.name, value: f.name }));
      event.eventBus.fire('spiff.json_schema_files.returned', { options });
    });

    // Task Metadata Keys autocomplete — m8flow-frontend's own useDiagramModeler.ts
    // answers this from a TASK_METADATA app-config value that's unset in every
    // env/compose file in this repo, so in practice it always answers `null`
    // today. Mirroring that (not inventing a key list) lets
    // SpiffExtensionTaskMetadata.jsx fall back to whatever metadata keys
    // already exist in the diagram's own XML, same as production.
    instance.on('spiff.task_metadata_keys.requested', (event: any) => {
      event.eventBus.fire('spiff.task_metadata_keys.returned', { keys: null });
    });

    // "Launch Editor" next to the JSON Schema Filename field. Empty
    // filename is not a dead click: name the form from the selected user
    // task and create the companion files if they are missing, then open
    // the editor. A selected filename opens those companions.
    instance.on('spiff.file.edit', (event: any) => {
      const selectedFileName: string | undefined = event.value || undefined;
      const {
        onReadFile: read,
        onWriteFile: write,
        onCreateFile: create,
        onFilesChanged: filesChanged,
      } = propsRef.current;
      if (!read || !write || !create) return;

      const selected = instance.get('selection')?.get?.()?.[0];
      const label = selected?.businessObject?.name || selected?.id || 'form';
      const fileName = selectedFileName ?? `${formSchemaBaseFromLabel(label)}${SCHEMA_SUFFIX}`;

      setFormEditorSession({
        fileName,
        createIfMissing: !selectedFileName,
        onReadFile: read,
        onWriteFile: write,
        onCreateFile: create,
        onCommitted: (schemaFileName) => {
          if (event.listenEvent) {
            event.eventBus.fire(event.listenEvent, { value: schemaFileName });
          }
          filesChanged?.();
        },
      });
    });

    // Select Decision Table dropdown (Business Rule Task group) — same
    // file-list-filtering pattern as JSON Schema Filename above, filtered to
    // .dmn instead. No backend route needed, same reasoning as above.
    instance.on('spiff.dmn_files.requested', (event: any) => {
      const modelFiles = propsRef.current.files ?? [];
      const options = modelFiles
        .filter((f) => /\.dmn$/i.test(f.name))
        .map((f) => ({ label: f.name, value: f.name }));
      event.eventBus.fire('spiff.dmn_files.returned', { options });
    });

    // "Launch Editor" next to Select Decision Table — navigates to the
    // chosen .dmn file's own modeler page (DmnCanvas), reusing
    // ProcessModelModelerPage's existing file-extension routing rather than
    // an inline editor. Unlike spiff.file.edit above, this event carries no
    // listenEvent to fire back (confirmed in bpmn-js-spiffworkflow's own
    // SpiffExtensionLaunchButton source) — it's fire-and-forget by design.
    instance.on('spiff.dmn.edit', (event: any) => {
      const fileName: string | undefined = event.value || undefined;
      if (!fileName) return;
      propsRef.current.onLaunchDmnEditor?.(fileName);
    });

    // Call Activity's "Search" button — opens a picker over every process
    // model in this tenant (cross-model, unlike JSON Schema/DMN's per-model
    // file lists) and, on selection, fires the exact
    // `spiff.callactivity.update` round trip CallActivityPropertiesProvider's
    // own FindProcessButton already listens for. No reference implementation
    // to port here (m8flow-frontend's onSearchProcessModels is a no-op in
    // its one real consumer) — CallActivitySearchDialog is new.
    instance.on('spiff.callactivity.search', (event: any) => {
      const models = propsRef.current.processModels ?? [];
      setCallActivitySearchSession({
        processModels: models,
        initialQuery: event.processId || undefined,
        onSelect: (processModelId) => {
          event.eventBus.fire('spiff.callactivity.update', { element: event.element, value: processModelId });
        },
      });
    });

    // Call Activity's "Launch Editor" — navigates to the called process
    // model's own modeler page. Fire-and-forget, same as spiff.dmn.edit
    // (confirmed in CallActivityPropertiesProvider.js's own LaunchEditorButton:
    // no listenEvent is registered).
    instance.on('spiff.callactivity.edit', (event: any) => {
      const processModelId: string | undefined = event.processId || undefined;
      if (!processModelId) return;
      propsRef.current.onLaunchCallActivityEditor?.(processModelId);
    });

    // Service Task's connector operator dropdown. The Action tab (and, once
    // the catalog is known-non-empty, ServiceTaskOperatorSelect) fires
    // `spiff.service_tasks.requested`. Empty catalogs are cached by
    // `serviceTaskOperatorCatalog` so the vendor select is never mounted
    // against `[]` (it would ignore empty and re-request every render).
    // Source is `GET /connectors-grouped`, reshaped client-side into the
    // flat `{id, parameters}[]` shape the select expects.
    instance.on('spiff.service_tasks.requested', (event: any) => {
      const fetchOperators = propsRef.current.onFetchServiceTaskOperators;
      if (!fetchOperators) {
        event.eventBus.fire('spiff.service_tasks.returned', { serviceTaskOperators: [] });
        return;
      }
      fetchOperators()
        .then((serviceTaskOperators) => {
          event.eventBus.fire('spiff.service_tasks.returned', { serviceTaskOperators });
        })
        .catch((err: unknown) => {
          console.error('Failed to load service task operators:', err);
          event.eventBus.fire('spiff.service_tasks.returned', { serviceTaskOperators: [] });
        });
    });

    instance.on(
      CONNECTOR_PROFILES_REQUESTED,
      (event: { eventBus: { fire: (type: string, payload: unknown) => void }; connectorType?: string }) => {
        const connectorType = event.connectorType || '';
        const fetchProfiles = propsRef.current.onFetchConnectorProfiles;
        const empty = {
          connectorType,
          profiles: [],
          hiddenFieldIds: [],
          supportsProfiles: false,
        };
        if (!fetchProfiles || !connectorType) {
          event.eventBus.fire(CONNECTOR_PROFILES_RETURNED, empty);
          return;
        }
        fetchProfiles(connectorType)
          .then((payload) => {
            event.eventBus.fire(CONNECTOR_PROFILES_RETURNED, {
              connectorType,
              profiles: payload.profiles,
              hiddenFieldIds: payload.hiddenFieldIds,
              supportsProfiles: payload.supportsProfiles,
            });
          })
          .catch((err: unknown) => {
            console.error('Failed to load connector profiles:', err);
            event.eventBus.fire(CONNECTOR_PROFILES_RETURNED, empty);
          });
      },
    );

    // Data Store Reference's "Select DataSource" dropdown — self-contained
    // (see findDeclaredDataStores above), no props/backend call needed.
    instance.on('spiff.data_stores.requested', (event: any) => {
      event.eventBus.fire('spiff.data_stores.returned', { options: findDeclaredDataStores(instance) });
    });

    setModeler(instance);

    return () => instance.destroy();
  }, []);

  useEffect(() => {
    if (!modeler) return undefined;

    // Only start dirty-tracking once import settles — attaching before
    // would risk import's own internal command-stack activity (there isn't
    // any for a plain importXML, but this ordering is the safe default)
    // being misread as a user edit.
    const checkDirty = () => {
      onDirtyChange?.(modeler.get('commandStack')._stackIdx !== savedStackIndexRef.current);
    };

    modeler
      .importXML(xml)
      .then(() => {
        setError(null);
        savedStackIndexRef.current = modeler.get('commandStack')._stackIdx;
        onDirtyChange?.(false);
        modeler.on('commandStack.changed', checkDirty);
        // Best-effort cosmetic fit — needs both arguments, per the recipe;
        // omitting 'auto' throws a non-finite-scale error.
        try {
          modeler.get('canvas').zoom('fit-viewport', 'auto');
        } catch (zoomErr) {
          console.warn('zoom-to-fit failed (cosmetic only):', zoomErr);
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to render diagram');
      });

    return () => modeler.off('commandStack.changed', checkDirty);
  }, [modeler, xml, onDirtyChange]);

  return (
    <div className="relative flex size-full">
      {error ? (
        <p className="absolute inset-x-0 top-0 z-10 p-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <div className="m8flow-bpmn relative min-w-0 flex-1">
        <div ref={canvasRef} className="size-full" />
        <button
          type="button"
          title={panelOpen ? 'Hide properties panel' : 'Show properties panel'}
          onClick={() => setPanelOpen((open) => !open)}
          className="absolute top-5 right-5 z-10 flex size-9 items-center justify-center rounded-[10px] border border-border bg-card shadow-sm"
        >
          {panelOpen ? (
            <PanelRightClose className="size-[15px] text-muted-foreground" strokeWidth={2} />
          ) : (
            <PanelRightOpen className="size-[15px] text-muted-foreground" strokeWidth={2} />
          )}
        </button>
        {editorSession ? (
          <Suspense fallback={null}>
            <EditorDialog session={editorSession} onClose={() => setEditorSession(null)} />
          </Suspense>
        ) : null}
        {formEditorSession ? (
          <Suspense fallback={null}>
            <FormSchemaEditor session={formEditorSession} onClose={() => setFormEditorSession(null)} />
          </Suspense>
        ) : null}
        {callActivitySearchSession ? (
          <CallActivitySearchDialog
            session={callActivitySearchSession}
            onClose={() => setCallActivitySearchSession(null)}
          />
        ) : null}
      </div>
      <div
        ref={panelRef}
        className={panelOpen ? 'w-80 flex-none overflow-y-auto border-l border-border' : 'w-0 overflow-hidden'}
      />
    </div>
  );
});
