import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  deleteTemplate,
  exportTemplate,
  fetchTemplates,
  restoreTemplate,
  type Template,
  type TemplatePagination,
} from '@/lib/templatesApi';
import { downloadBlob } from '@/lib/download';
import { getCurrentUser } from '@/lib/auth';
import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { CreateProcessModelFromTemplateDialog } from './components/CreateProcessModelFromTemplateDialog';
import { ImportTemplateDialog } from './components/ImportTemplateDialog';
import {
  TemplateDeleteConfirmDialog,
  TemplateRestoreConfirmDialog,
} from './components/TemplateGalleryConfirmDialogs';
import { TemplatesGalleryList, type VisibilityFilter } from './components/TemplatesGalleryList';
import type { TemplateGalleryMode } from './components/templateGalleryPermissions';

const PER_PAGE = 12;
/** Matches ProcessesModelsList's own ⌘K-search debounce intent — avoids
 * firing a server request per keystroke (this list is server-paginated/
 * -searched, unlike Processes' client-side filter, so debouncing here is
 * load-bearing, not just cosmetic). */
const SEARCH_DEBOUNCE_MS = 300;

/**
 * Templates gallery — wired to GET /v1.0/m8flow/templates (Template
 * modeler map, ticket 02 — .scratch/template-modeler/). Same tenant-gating
 * posture as ProcessesPage: super-admin must pick a concrete tenant, no
 * merged all-tenant catalog view, even though the backend itself would
 * technically allow one for an unscoped super-admin request — kept
 * consistent with this app's own established tenant-isolation convention
 * rather than relying on that backend leniency.
 */
export default function TemplatesPage() {
  const { scopedTenantId, isSuperAdmin, needsTenantForWrite } = useActiveTenant();
  const { canManageTenant, canManageProcesses } = useCapabilities();
  const navigate = useNavigate();
  const actor = {
    canManageTemplates: canManageProcesses && !isSuperAdmin,
    isSuperAdmin,
    canManageTenant: Boolean(canManageTenant) && !isSuperAdmin,
    currentUsername: getCurrentUser()?.username ?? null,
  };

  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [visibility, setVisibility] = useState<VisibilityFilter>('ALL');
  const [order, setOrder] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const [galleryMode, setGalleryMode] = useState<TemplateGalleryMode>('active');

  const [templates, setTemplates] = useState<Template[]>([]);
  const [pagination, setPagination] = useState<TemplatePagination | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumped after a successful delete/import to trigger a refetch — a
  // dependency, not a direct re-call, since the main fetch effect below
  // already owns loading/error state for the current filter combination.
  const [reloadKey, setReloadKey] = useState(0);
  // Ticket 04 (create/import/export/delete): errors from these actions are
  // reported separately from the list's own load `error` above, so a
  // failed delete doesn't get mistaken for "the list failed to load."
  const [actionError, setActionError] = useState<string | null>(null);
  const [useTemplateTarget, setUseTemplateTarget] = useState<Template | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Template | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<Template | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  // Debounce the raw input into the value that actually drives the fetch,
  // and reset to page 1 whenever the effective search term changes.
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    setPage(1);
  }, [visibility, order, galleryMode]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchTemplates({
      search: search || undefined,
      visibility: visibility === 'ALL' ? undefined : visibility,
      sortBy: 'created',
      order,
      page,
      perPage: PER_PAGE,
      tenantId: scopedTenantId ?? undefined,
      latestOnly: galleryMode === 'deleted' ? false : undefined,
      deletedOnly: galleryMode === 'deleted' ? true : undefined,
      includeDeleted: galleryMode === 'deleted' ? true : undefined,
    })
      .then(({ results, pagination: pg }) => {
        if (!cancelled) {
          setTemplates(results);
          setPagination(pg);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load templates');
          setTemplates([]);
          setPagination(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [scopedTenantId, search, visibility, order, page, reloadKey, galleryMode]);

  const handleExport = useCallback(async (template: Template) => {
    setActionError(null);
    try {
      const blob = await exportTemplate(template.id);
      downloadBlob(`${template.templateKey}-v${template.version}.zip`, blob);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to export template');
    }
  }, []);

  const handleDelete = useCallback((template: Template) => {
    setActionError(null);
    setDeleteTarget(template);
  }, []);

  const handleRestore = useCallback((template: Template) => {
    setActionError(null);
    setRestoreTarget(template);
  }, []);

  async function confirmDelete() {
    if (!deleteTarget) return;
    setActionBusy(true);
    setActionError(null);
    try {
      await deleteTemplate(deleteTarget.id);
      setDeleteTarget(null);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to delete template');
    } finally {
      setActionBusy(false);
    }
  }

  async function confirmRestore() {
    if (!restoreTarget) return;
    setActionBusy(true);
    setActionError(null);
    try {
      await restoreTemplate(restoreTarget.id);
      setRestoreTarget(null);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to restore template');
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <main className="flex-1 px-11 py-10">
      {actionError ? (
        <p className="mb-4 text-sm text-destructive" role="alert">
          {actionError}
        </p>
      ) : null}
      <TemplatesGalleryList
        templates={templates}
        loading={loading}
        error={error}
        search={searchInput}
        onSearchChange={setSearchInput}
        visibility={visibility}
        onVisibilityChange={setVisibility}
        order={order}
        onToggleOrder={() => setOrder((o) => (o === 'desc' ? 'asc' : 'desc'))}
        page={page}
        pageSize={PER_PAGE}
        totalCount={pagination?.total ?? templates.length}
        onPageChange={setPage}
        onOpenTemplate={(template) => navigate(`/templates/${template.id}`)}
        onUseTemplate={setUseTemplateTarget}
        onExportTemplate={handleExport}
        onDeleteTemplate={handleDelete}
        onRestoreTemplate={handleRestore}
        onImportClick={actor.canManageTemplates ? () => setImportOpen(true) : undefined}
        galleryMode={galleryMode}
        onGalleryModeChange={setGalleryMode}
        actor={actor}
        isSuperAdmin={isSuperAdmin}
        canUseTemplate={Boolean(canManageProcesses) && !needsTenantForWrite}
      />

      <TemplateDeleteConfirmDialog
        open={Boolean(deleteTarget)}
        templateName={deleteTarget?.name ?? ''}
        isPublished={Boolean(deleteTarget?.isPublished)}
        submitting={actionBusy}
        onCancel={() => { if (!actionBusy) setDeleteTarget(null); }}
        onConfirm={() => void confirmDelete()}
      />

      <TemplateRestoreConfirmDialog
        open={Boolean(restoreTarget)}
        templateName={restoreTarget?.name ?? ''}
        submitting={actionBusy}
        onCancel={() => { if (!actionBusy) setRestoreTarget(null); }}
        onConfirm={() => void confirmRestore()}
      />

      {useTemplateTarget ? (
        <CreateProcessModelFromTemplateDialog
          template={useTemplateTarget}
          open
          onClose={() => setUseTemplateTarget(null)}
          scopedTenantId={scopedTenantId}
          needsTenant={needsTenantForWrite}
          onCreated={(encodedProcessModelId) => {
            setUseTemplateTarget(null);
            navigate(`/processes/${encodedProcessModelId}`);
          }}
        />
      ) : null}

      <ImportTemplateDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={(templateId) => {
          setImportOpen(false);
          navigate(`/templates/${templateId}`);
        }}
      />
    </main>
  );
}
