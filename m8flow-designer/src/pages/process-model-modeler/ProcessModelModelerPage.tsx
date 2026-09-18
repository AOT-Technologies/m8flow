import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Link,
  useBeforeUnload,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';

import {
  ApiError,
  createProcessModelFile,
  deleteProcessModelFile,
  fetchConnectorsGrouped,
  fetchProcessModelDetail,
  fetchProcessModelFileContent,
  fetchProcessModels,
  saveProcessModelFileContent,
  updateProcessModel,
  runScriptUnitTest,
  type ProcessModelDetailFile,
} from '@/lib/api';
import { Breadcrumbs, type BreadcrumbLinkProps } from '@/components/library/breadcrumbs/Breadcrumbs';
import { DiagramCanvas } from './components/DiagramCanvas';
import type { DiagramCanvasHandle } from './components/DiagramCanvasHandle';
import type { CallActivitySearchProcessModel } from './components/CallActivitySearchDialog';
import { flattenConnectorGroupsToOperators } from './serviceTaskOperators';
import { fetchConnectorProfilesForPicker } from '@/lib/connectorsApi';
import { DeleteFileDialog, UnsavedChangesDialog, ViewXmlDialog } from './components/ModelerFileDialogs';
import { NotPrimaryBanner } from './components/ModelerBanners';
import { ModelerFileToolbar, type ModelerSavePhase } from './components/ModelerFileToolbar';
import { AddProcessModelFileDialog, fileOpensInModeler } from '@/pages/process-model-detail/components/AddProcessModelFileDialog';
import { downloadTextFile } from '@/lib/download';
import { encodeProcessModelId } from '@/lib/processModelId';
import { useActiveTenant, useCapabilities } from '@/components/session/hooks';

/** Save/dirty state machine (decided on the manual-save ticket, HITL): the
 * Save button and the SavedStatusPill are never shown together — 'dirty'
 * shows the button, everything else shows the pill. 'error' is a brief
 * flash before automatically reverting to 'dirty' (the save didn't
 * actually succeed, so the diagram is still unsaved) rather than a
 * persistent state. */
type SavePhase = ModelerSavePhase;

const ERROR_FLASH_MS = 2500;

/** Adapter passed to `Breadcrumbs`' `LinkComponent` for client-side
 * navigation (component-adoption map, ticket 08). */
function RouterBreadcrumbLink({ href, className, children }: BreadcrumbLinkProps) {
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}

/**
 * Process Modeler — one file inside a process model per URL.
 * Fetches GET /v1.0/m8flow/process-models/{id}/files/{fileName} and mounts
 * BpmnCanvas (.bpmn), DmnCanvas (.dmn), or TextFileCanvas (.json / .md).
 * Manual save (Cmd/Ctrl+S or the Save button) PUTs the current contents
 * back; the RBAC gap logged on the backend-endpoints ticket (a .bpmn save
 * needs m8flow-bpmn-core's V1 "admin" role, not just the editor group) is
 * deliberately not special-cased here — it surfaces as the same generic
 * "Save failed" flash as any other error (decided, not an oversight).
 */
export default function ProcessModelModelerPage() {
  const { processModelId, fileName } = useParams<{
    processModelId: string;
    fileName: string;
  }>();
  const navigate = useNavigate();
  const { scopedTenantId, needsTenantForWrite } = useActiveTenant();
  const [searchParams] = useSearchParams();
  // Navigation into the modeler always carries the model's own tenant under
  // All Tenants (model ids collide across tenants), so editing works once
  // arrived from a row; saving without any tenant stays disabled below.
  const tenantId = searchParams.get('tenantId') || scopedTenantId;
  const { canManageProcesses } = useCapabilities();
  // M8F-479: super-admin may edit catalog files when a concrete tenant is selected.
  /** Tenant the backend resolved this model to, for All-Tenants navigation
   * that arrived without an explicit ?tenantId. */
  const [resolvedTenantId, setResolvedTenantId] = useState<string | null>(null);
  const effectiveTenantId = tenantId || resolvedTenantId;
  // A regular user has no sidebar scope (their tenant is the cookie), so only
  // an All-Tenants super-admin with no resolved tenant is blocked from saving.
  const needsTenantToWrite = needsTenantForWrite && !effectiveTenantId;
  const canManageCatalog = Boolean(canManageProcesses) && !needsTenantToWrite;
  const modifiedId = processModelId ?? '';
  const file = fileName ?? '';
  const canvasRef = useRef<DiagramCanvasHandle>(null);

  const [xml, setXml] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(modifiedId) && Boolean(file));
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savePhase, setSavePhase] = useState<SavePhase>('saved');
  // Breadcrumb group label (header-chrome ticket, HITL): `fetchProcessModelDetail`
  // is the same detail call ProcessModelOverview already uses — reused here
  // rather than `fetchProcessGroups`'s list-and-find, since the model's own
  // detail response already carries its group's id/display name directly.
  // Falls back to the raw group id (the first `:`-segment of `modifiedId`)
  // until the fetch resolves, or forever if it fails — a label-only lookup
  // isn't worth a visible error state.
  const [groupInfo, setGroupInfo] = useState<{ id: string; displayName: string } | null>(null);
  // This model's own files (Task Configuration Parity plan, Phase 1) — feeds
  // BpmnCanvas's JSON Schema Filename dropdown. Same fetch as groupInfo above
  // (ProcessModelDetailResponse carries both), so no extra request.
  const [modelFiles, setModelFiles] = useState<ProcessModelDetailFile[]>([]);
  // Every process model in this tenant (Task Configuration Parity plan,
  // Phase 3) — feeds Call Activity's "Search" picker. Cross-model, so a
  // separate fetch from modelFiles above (which is scoped to *this* model).
  const [processModels, setProcessModels] = useState<CallActivitySearchProcessModel[]>([]);
  const [newFileOpen, setNewFileOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [viewXmlOpen, setViewXmlOpen] = useState(false);
  const [viewXml, setViewXml] = useState<string | null>(null);
  const [viewXmlError, setViewXmlError] = useState<string | null>(null);
  const [leaveTo, setLeaveTo] = useState<string | null>(null);
  const [settingPrimary, setSettingPrimary] = useState(false);

  useEffect(() => {
    if (!modifiedId || !file) {
      setXml(null);
      setLoading(false);
      setNotFound(!modifiedId || !file);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    setError(null);

    fetchProcessModelFileContent(modifiedId, file, tenantId)
      .then((content) => {
        if (!cancelled) {
          setXml(content);
          setSavePhase('saved');
        }
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }
        setXml(null);
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
          setError(null);
          return;
        }
        setNotFound(false);
        setError(err instanceof Error ? err.message : 'Failed to load file');
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [modifiedId, file, tenantId]);

  useEffect(() => {
    if (!modifiedId) {
      setGroupInfo(null);
      setModelFiles([]);
      return undefined;
    }

    let cancelled = false;
    fetchProcessModelDetail(modifiedId, tenantId)
      .then((detail) => {
        if (!cancelled) {
          setGroupInfo({ id: detail.group_id, displayName: detail.group_display_name });
          setModelFiles(detail.files);
          // Under All Tenants the backend resolves the owning tenant for us;
          // keep it so saves target that tenant instead of failing closed.
          setResolvedTenantId(detail.tenant_id ?? null);
        }
      })
      .catch(() => {
        // Breadcrumb degrades to the raw group id below, and the JSON Schema
        // dropdown degrades to empty — neither is worth a visible error for
        // what's otherwise a background enrichment fetch.
      });

    return () => {
      cancelled = true;
    };
  }, [modifiedId, tenantId]);

  useEffect(() => {
    let cancelled = false;
    fetchProcessModels(tenantId)
      .then((models) => {
        if (!cancelled) {
          setProcessModels(
            // fetchProcessModels' own `id` is `/`-separated (the raw API/disk
            // form, per lib/processModelId.ts's own doc comment) — encode to
            // `:` before handing it to the search dialog, since it becomes
            // both the bpmn:calledElement value (typed into "Process ID") and
            // the argument handleLaunchCallActivityEditor below passes to
            // fetchProcessModelDetail, which expects the `:` route form.
            models.map((m) => ({
              id: encodeProcessModelId(m.id),
              displayName: m.display_name,
              groupDisplayName: m.group_display_name,
            })),
          );
        }
      })
      .catch(() => {
        // Search picker degrades to an empty result list — not worth a
        // visible error for what's otherwise a background enrichment fetch.
      });

    return () => {
      cancelled = true;
    };
  }, [tenantId]);

  // Call Activity's "Launch Editor" (Task Configuration Parity plan, Phase
  // 3) — resolves the called process model's *primary* file (same lookup
  // ProcessModelOverview.tsx already uses for its own "Open in modeler"
  // link) and navigates there.
  const handleLaunchCallActivityEditor = useCallback(
    async (calledProcessModelId: string) => {
      try {
        const detail = await fetchProcessModelDetail(calledProcessModelId, tenantId);
        const primaryFile = detail.files.find((f) => f.primary);
        if (!primaryFile) return;
        navigate(`/processes/${encodeProcessModelId(detail.id)}/modeler/${encodeURIComponent(primaryFile.name)}`);
      } catch (err) {
        console.error('Failed to open called process model:', err);
      }
    },
    [navigate, tenantId],
  );

  // Service Task's connector operator dropdown (Task Configuration Parity
  // plan, Phase 4). Spike outcome: m8flow-frontend's own `/service-tasks`
  // call has no matching backend route; `GET /connectors-grouped` is the
  // real, working source (same one the Connectors page itself uses) —
  // flattened here from "grouped by connector" into the flat
  // `{id, parameters}[]` shape bpmn-js-spiffworkflow's
  // ServiceTaskOperatorSelect expects.
  const handleFetchServiceTaskOperators = useCallback(async () => {
    return flattenConnectorGroupsToOperators(await fetchConnectorsGrouped());
  }, []);

  const handleFetchConnectorProfiles = useCallback(
    (connectorType: string) => fetchConnectorProfilesForPicker(connectorType, tenantId),
    [tenantId],
  );

  const handleRunScriptUnitTest = useCallback(
    (input: {
      python_script: string;
      input_json: Record<string, unknown>;
      expected_output_json: Record<string, unknown>;
    }) => runScriptUnitTest(modifiedId, input, effectiveTenantId),
    [modifiedId, effectiveTenantId],
  );

  // JSON Schema "Launch Editor" (User Task Web Form). Create Files writes
  // *-schema.json / *-uischema.json / *-exampledata.json via POST; later
  // edits PUT the same files. After create, the listenEvent binds the
  // schema filename onto the selected task.
  const handleReadModelFile = useCallback(
    (name: string) => fetchProcessModelFileContent(modifiedId, name, tenantId),
    [modifiedId, tenantId],
  );
  const handleWriteModelFile = useCallback(
    async (name: string, content: string) => {
      await saveProcessModelFileContent(modifiedId, name, content, effectiveTenantId);
    },
    [modifiedId, effectiveTenantId],
  );
  const handleCreateModelFile = useCallback(
    async (name: string, content: string) => {
      await createProcessModelFile(modifiedId, { file_name: name, content }, effectiveTenantId);
    },
    [modifiedId, effectiveTenantId],
  );
  const handleFormFilesChanged = useCallback(() => {
    void fetchProcessModelDetail(modifiedId, tenantId)
      .then((detail) => {
        setGroupInfo({ id: detail.group_id, displayName: detail.group_display_name });
        setModelFiles(detail.files);
      })
      .catch(() => {
        // Dropdown refresh is best-effort — the new filename is already
        // written onto the task via the Launch Editor listenEvent.
      });
  }, [modifiedId, tenantId]);

  // Business Rule Task's "Launch Editor" (Task Configuration Parity plan,
  // Phase 2) — navigates to the chosen .dmn file's own modeler page, reusing
  // this same route (DiagramCanvas dispatches to DmnCanvas by extension).
  // m8flow-frontend's own onLaunchDmnEditor is a no-op today (its one real
  // consumer, TemplateFileDiagramPage, never wires anything real here) —
  // this is a genuine improvement, not a straight port.
  const handleLaunchDmnEditor = useCallback(
    (name: string) => {
      navigate(`/processes/${modifiedId}/modeler/${encodeURIComponent(name)}`);
    },
    [navigate, modifiedId],
  );

  const handleDirtyChange = useCallback((dirty: boolean) => {
    // Only 'saved' <-> 'dirty' react to canvas edits/undo; 'saving' and the
    // brief 'error' flash own the pill until they resolve on their own.
    setSavePhase((phase) => {
      if (phase === 'saving' || phase === 'error') return phase;
      return dirty ? 'dirty' : 'saved';
    });
  }, []);

  const handleSave = useCallback(async () => {
    if (!canManageCatalog || !canvasRef.current) return;
    setSavePhase('saving');
    try {
      const { xml, baseline } = await canvasRef.current.saveXML();
      await saveProcessModelFileContent(modifiedId, file, xml, effectiveTenantId);
      const stillDirty = canvasRef.current.markSaved(baseline);
      setSavePhase(stillDirty ? 'dirty' : 'saved');
    } catch {
      setSavePhase('error');
      setTimeout(() => setSavePhase('dirty'), ERROR_FLASH_MS);
    }
  }, [modifiedId, file, effectiveTenantId, canManageCatalog]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        if (savePhase === 'dirty') {
          void handleSave();
        }
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [savePhase, handleSave]);

  async function handleDownload() {
    if (!canvasRef.current) return;
    const { xml } = await canvasRef.current.saveXML();
    downloadTextFile(file || 'diagram.bpmn', xml);
  }

  const fileLower = file.toLowerCase();
  const isBpmn = fileLower.endsWith('.bpmn');
  const isDiagram = isBpmn || fileLower.endsWith('.dmn');
  const currentFileMeta = modelFiles.find((entry) => entry.name === file);
  // Before the detail list arrives, assume primary so Delete does not flash
  // on the seed BPMN. Once the list is known, a file missing from it (just
  // created, list not yet refreshed) is not primary.
  const isPrimary = currentFileMeta ? currentFileMeta.primary : modelFiles.length === 0;
  // M8F-510: a .bpmn that is not primary is still not what the process runs --
  // the toolbar's "Set as primary" button was the only hint, and testers read
  // the "Saved" pill as proof their upload had taken effect instead.
  const primaryFileName = modelFiles.find((entry) => entry.primary)?.name;
  const showNotPrimary = isBpmn && !isPrimary && Boolean(primaryFileName);

  const allowLeaveRef = useRef(false);
  const dirty = savePhase === 'dirty';
  useBeforeUnload(
    useCallback(
      (event) => {
        if (dirty) event.preventDefault();
      },
      [dirty],
    ),
  );
  // BrowserRouter is not a data router, so useBlocker cannot run here. Capture
  // in-app <a href> clicks while dirty and confirm before navigate(); tab close
  // is covered by useBeforeUnload above.
  useEffect(() => {
    if (!dirty) return undefined;
    function onClick(event: MouseEvent) {
      if (allowLeaveRef.current || event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element | null)?.closest('a[href]');
      if (!(anchor instanceof HTMLAnchorElement)) return;
      const href = anchor.getAttribute('href');
      if (!href || href.startsWith('mailto:') || href.startsWith('tel:')) return;
      const url = new URL(href, window.location.origin);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      event.preventDefault();
      event.stopPropagation();
      setLeaveTo(`${url.pathname}${url.search}${url.hash}`);
    }
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [dirty]);

  async function handleViewXml() {
    setViewXmlOpen(true);
    setViewXml(null);
    setViewXmlError(null);
    try {
      const current = canvasRef.current ? (await canvasRef.current.saveXML()).xml : xml;
      setViewXml(current ?? '');
    } catch (err) {
      setViewXmlError(err instanceof Error ? err.message : 'Failed to export XML');
    }
  }

  async function handleSetPrimary() {
    setSettingPrimary(true);
    try {
      await updateProcessModel(modifiedId, { primary_file_name: file }, effectiveTenantId);
      try {
        const detail = await fetchProcessModelDetail(modifiedId, tenantId);
        setGroupInfo({ id: detail.group_id, displayName: detail.group_display_name });
        setModelFiles(detail.files);
      } catch {
        // Primary is already written; the star just won't hide until next load.
      }
    } finally {
      setSettingPrimary(false);
    }
  }

  async function handleConfirmDelete() {
    setDeleting(true);
    try {
      await deleteProcessModelFile(modifiedId, file, effectiveTenantId);
      allowLeaveRef.current = true;
      setSavePhase('saved');
      setDeleteOpen(false);
      navigate(`/processes/${modifiedId}`);
    } catch {
      setDeleting(false);
    }
  }

  // Mockup fidelity decision (HITL, header-chrome ticket): the mockup's
  // three-crumb breadcrumb (Process Groups / Group / file) has no crumb at
  // all for "this model's own detail page" — the group crumb, linking to
  // the group-filtered process list, is the closest equivalent. This trades
  // one click for two to get back to the model detail page (Group list →
  // find the model → open it) versus the old single "← group:model" link
  // straight there. A deliberate fidelity tradeoff, not an oversight.
  const groupId = groupInfo?.id ?? modifiedId.split(':')[0] ?? '';
  const groupLabel = groupInfo?.displayName || groupId || 'Process group';

  return (
    <div className="flex min-h-screen flex-1 flex-col">
      <header className="flex flex-none items-center justify-between gap-3 border-b border-border px-6 py-3">
        <Breadcrumbs
          className="min-w-0 overflow-hidden text-[13.5px] text-muted-foreground"
          LinkComponent={RouterBreadcrumbLink}
          linkClassName="text-info font-normal"
          lastClassName="min-w-0 truncate font-mono"
          items={[
            { label: 'Process Groups', href: '/processes' },
            {
              label: groupLabel,
              href: groupId ? `/processes?group=${encodeURIComponent(groupId)}` : '/processes',
            },
            { label: file },
          ]}
        />
        <ModelerFileToolbar
          savePhase={savePhase}
          fileLoaded={xml != null}
          canManage={canManageCatalog}
          isPrimary={isPrimary}
          isBpmn={isBpmn}
          isDiagram={isDiagram}
          onSave={() => void handleSave()}
          onDownload={() => void handleDownload()}
          onNewFile={() => setNewFileOpen(true)}
          onDelete={() => setDeleteOpen(true)}
          onSetPrimary={() => void handleSetPrimary()}
          onViewXml={() => void handleViewXml()}
        />
      </header>

      {/* `isolate` (M8F-524): diagram-js draws its context pad at z-index 100
          and its popup menus at 200 (diagram-js.css). Without a stacking
          context here they compete in the root layer and paint over the
          app's z-50 Radix dialogs — see the per-dialog `z-[1000]` escapes in
          EditorDialog and CallActivitySearchDialog, which this makes
          unnecessary for any new dialog. `isolation` creates a stacking
          context but not a containing block, so the popup's `position: fixed`
          still positions against the viewport. */}
      <main className="isolate flex min-h-0 flex-1 flex-col">
        {xml != null && showNotPrimary ? (
          <div className="flex-none px-6 pt-3">
            <NotPrimaryBanner
              primaryFileName={primaryFileName as string}
              onSetPrimary={canManageCatalog ? () => void handleSetPrimary() : undefined}
              submitting={settingPrimary}
            />
          </div>
        ) : null}
        <div className="flex min-h-0 flex-1 flex-col">
          {loading ? (
            <p className="p-6 text-sm text-muted-foreground" aria-busy="true">
              Loading file…
            </p>
          ) : notFound ? (
            <p className="p-6 text-sm text-muted-foreground" role="status">
              File not found.
            </p>
          ) : error ? (
            <p className="p-6 text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : xml != null ? (
            <DiagramCanvas
              readOnly={!canManageCatalog}
              ref={canvasRef}
              fileName={file}
              xml={xml}
              onDirtyChange={handleDirtyChange}
              files={modelFiles}
              onReadFile={handleReadModelFile}
              onWriteFile={handleWriteModelFile}
              onCreateFile={handleCreateModelFile}
              onFilesChanged={handleFormFilesChanged}
              onLaunchDmnEditor={handleLaunchDmnEditor}
              processModels={processModels}
              onLaunchCallActivityEditor={handleLaunchCallActivityEditor}
              onFetchServiceTaskOperators={handleFetchServiceTaskOperators}
              onFetchConnectorProfiles={handleFetchConnectorProfiles}
              onRunScriptUnitTest={handleRunScriptUnitTest}
            />
          ) : null}
        </div>
      </main>
      <UnsavedChangesDialog
        open={leaveTo != null}
        onStay={() => setLeaveTo(null)}
        onLeave={() => {
          const to = leaveTo;
          allowLeaveRef.current = true;
          setLeaveTo(null);
          if (to) navigate(to);
        }}
      />
      <DeleteFileDialog
        open={deleteOpen}
        fileName={file}
        submitting={deleting}
        onCancel={() => { if (!deleting) setDeleteOpen(false); }}
        onConfirm={() => void handleConfirmDelete()}
      />
      <ViewXmlDialog
        open={viewXmlOpen}
        fileName={file}
        xml={viewXml}
        error={viewXmlError}
        onClose={() => setViewXmlOpen(false)}
      />
      {canManageCatalog ? (
        <AddProcessModelFileDialog
          open={newFileOpen}
          onClose={() => setNewFileOpen(false)}
          existingNames={modelFiles.map((entry) => entry.name)}
          onCreate={async (input) => {
            await createProcessModelFile(modifiedId, input, effectiveTenantId);
          }}
          onCreated={(fileName) => {
            setNewFileOpen(false);
            setModelFiles((prev) =>
              prev.some((entry) => entry.name === fileName)
                ? prev
                : [
                    ...prev,
                    {
                      name: fileName,
                      size_bytes: 0,
                      updated_at_in_seconds: 0,
                      primary: false,
                    },
                  ],
            );
            void fetchProcessModelDetail(modifiedId, tenantId)
              .then((detail) => {
                setGroupInfo({ id: detail.group_id, displayName: detail.group_display_name });
                setModelFiles(detail.files);
              })
              .catch(() => {
                // Delete/primary chrome falls back from the optimistic list.
              });
            if (fileOpensInModeler(fileName)) {
              navigate(`/processes/${modifiedId}/modeler/${encodeURIComponent(fileName)}`);
            } else {
              navigate(`/processes/${modifiedId}`);
            }
          }}
        />
      ) : null}
    </div>
  );
}
