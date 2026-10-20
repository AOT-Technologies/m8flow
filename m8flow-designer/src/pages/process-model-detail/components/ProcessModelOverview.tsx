import { ChevronLeft, Download, Eye, Folder, Pencil, Play, Plus, Send, Star, Trash2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import i18n from '@/i18n';

import {
  ApiError,
  fetchProcessModelFileContent,
  type ProcessModelDetail,
  type ProcessModelDetailFile,
  type ProcessModelDetailInstance,
  type ProcessModelStatus,
  type ProcessModelTestRunResult,
  type ScriptUnitTest,
  type ScriptUnitTestRunResult,
} from '@/lib/api';
import { startErrorMessage } from '@/lib/startProcessError';
import { AddProcessModelFileDialog, fileOpensInModeler } from './AddProcessModelFileDialog';
import { CopyProcessModelDialog } from './CopyProcessModelDialog';
import { HeaderActionsMenu } from './HeaderActionsMenu';
import {
  SaveAsTemplateDialog,
  isSupportedTemplateSourceFile,
  mimeForTemplateSourceFile,
  sortFilesPrimaryFirst,
} from './SaveAsTemplateDialog';
import { ProcessModelTestsCard } from './ProcessModelTestsCard';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Modal } from '@/components/library/modal/Modal';
import { Pill } from '@/components/library/pill/Pill';
import { processInstanceStatusToPillProps } from '@/components/library/pill/processInstanceStatusToPillProps';
import {
  normalizeProcessModelStatus,
  processModelStatusHint,
  processModelStatusToPillProps,
} from '@/components/library/pill/processModelStatusToPillProps';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { downloadTextFile } from '@/lib/download';
import { encodeProcessModelId } from '@/lib/processModelId';
import { formatRelativeTime } from '@/lib/relativeTime';
import { cn } from '@/lib/utils';

// This page's remaining placeholder actions (Open in modeler when no file
// exists yet) render `disabled` but are meant to *look* fully live, matching
// the mockup — not dimmed the way Button's own `disabled:opacity-50` otherwise
// renders every other disabled Button in the app. This override is the one
// deliberate exception to that rule.
const inertBtn = 'cursor-default select-none disabled:cursor-default disabled:opacity-100';

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) {
    return '—';
  }
  const n = Math.max(0, Math.floor(seconds));
  if (n < 60) {
    return `${n}s`;
  }
  const minutes = Math.floor(n / 60);
  const rem = n % 60;
  return rem ? `${minutes}m ${rem}s` : `${minutes}m`;
}

export function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  return `${Math.round(size / 1024)} KB`;
}

const recentInstanceColumns = (t: TFunction): DataTableColumn<ProcessModelDetailInstance>[] => [
  {
    key: 'id',
    header: t('processModelDetail.instances.columns.id'),
    width: 'minmax(70px,90px)',
    render: (row) => (
      <Link
        to={`/process-instances/${row.id}`}
        className="font-mono text-[13px] text-info no-underline hover:underline"
      >
        {row.id}
      </Link>
    ),
  },
  {
    key: 'started_by',
    header: t('processModelDetail.instances.columns.startedBy'),
    width: 'minmax(120px,1fr)',
    className: 'truncate text-[13.5px] text-foreground',
    render: (row) => row.started_by || '—',
  },
  {
    key: 'start',
    header: t('processModelDetail.instances.columns.start'),
    width: 'minmax(0,120px)',
    className: 'whitespace-nowrap text-[13px] text-muted-foreground',
    render: (row) => formatRelativeTime(row.started_at),
  },
  {
    key: 'duration',
    header: t('processModelDetail.instances.columns.duration'),
    width: 'minmax(0,100px)',
    className: 'font-mono text-[13px] text-muted-foreground',
    render: (row) => formatDuration(row.duration_seconds),
  },
  {
    key: 'status',
    header: t('common.status'),
    width: 'minmax(0,140px)',
    render: (row) => <Pill {...processInstanceStatusToPillProps(row.status)} />,
  },
];

export function fileKind(name: string): { ext: string; label: string } {
  const lower = name.toLowerCase();
  if (lower.endsWith('.bpmn')) {
    return { ext: 'BPMN', label: 'BPMN' };
  }
  if (lower.endsWith('.dmn')) {
    return { ext: 'DMN', label: 'DMN' };
  }
  if (lower.endsWith('.md')) {
    return { ext: 'MD', label: 'Markdown' };
  }
  if (lower.endsWith('.json')) {
    if (/^test_/.test(lower)) {
      return { ext: 'JSON', label: i18n.t('processModelDetail.files.kind.bpmnTest') };
    }
    if (lower.includes('uischema')) {
      return { ext: 'JSON', label: i18n.t('processModelDetail.files.kind.uiSchema') };
    }
    if (lower.includes('schema')) {
      return { ext: 'JSON', label: i18n.t('processModelDetail.files.kind.formSchema') };
    }
    return { ext: 'JSON', label: 'JSON' };
  }
  const dot = name.lastIndexOf('.');
  const ext = dot >= 0 ? name.slice(dot + 1).toUpperCase() : 'FILE';
  return { ext, label: ext };
}

function FileRow({
  file,
  modelId,
  tenantId,
  canManage,
  onSetPrimary,
  onDelete,
}: {
  file: ProcessModelDetailFile;
  modelId: string;
  tenantId?: string | null;
  canManage: boolean;
  onSetPrimary?: (fileName: string) => Promise<void>;
  // Wider than `onSetPrimary`'s type on purpose: unlike `onSetPrimary`
  // (which performs the API call directly), the caller below uses this to
  // open the confirm-delete dialog synchronously — the actual async
  // `onDeleteFile` call happens later, from that dialog's own confirm
  // button, not from here. The call site already discards the return value
  // (`void onDelete(file.name)`), so `void | Promise<void>` describes what
  // callers actually do without forcing every caller to wrap a sync
  // handler in an async no-op just to satisfy the type.
  onDelete?: (fileName: string) => void | Promise<void>;
}) {
  const { t } = useTranslation();
  const kind = fileKind(file.name);
  const meta = t('processModelDetail.files.meta', {
    kind: kind.label,
    size: formatBytes(file.size_bytes),
    updated: formatRelativeTime(file.updated_at),
  });
  const iconTone = kind.ext === 'BPMN' ? 'bg-nav-active/15 text-info' : 'bg-muted text-muted-foreground';
  const modelerHref = `/processes/${encodeProcessModelId(modelId)}/modeler/${encodeURIComponent(file.name)}`;
  // Same destination as the pencil/eye icon — the modeler is read-only for
  // users without manage rights, so the verb is the only thing that differs.
  const openFileNamed = canManage
    ? t('processModelDetail.files.editFileNamed', { name: file.name })
    : t('processModelDetail.files.viewFileNamed', { name: file.name });
  const openFile = canManage ? t('processModelDetail.files.editFile') : t('processModelDetail.files.viewFile');
  const canPrimary = canManage && Boolean(onSetPrimary) && kind.ext === 'BPMN' && !file.primary;

  async function handleDownload() {
    const content = await fetchProcessModelFileContent(encodeProcessModelId(modelId), file.name, tenantId);
    downloadTextFile(file.name, content);
  }

  return (
    <div className="flex items-center gap-3.5 border-b border-border px-4 py-3.5 last:border-b-0">
      <div
        className={cn(
          'flex size-8 shrink-0 items-center justify-center rounded-lg font-mono text-[9.5px] font-bold',
          iconTone,
        )}
      >
        {kind.ext}
      </div>
      <div className="min-w-0 flex-1">
        <Link
          to={modelerHref}
          title={openFileNamed}
          className="block break-words text-[13.5px] text-foreground no-underline hover:text-info hover:underline"
        >
          {file.name}
        </Link>
        <div className="mt-0.5 text-xs text-muted-foreground">{meta}</div>
      </div>
      {file.primary ? (
        <Pill tone="info" dot={false} className="shrink-0">
          {t('processModelDetail.files.primary')}
        </Pill>
      ) : null}
      <div className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
        {canManage ? (
          <Link
            to={modelerHref}
            title={openFile}
            className="flex size-7 items-center justify-center rounded-md no-underline hover:bg-muted hover:text-info"
          >
            <Pencil className="size-4" strokeWidth={1.8} aria-hidden />
          </Link>
        ) : (
          <Link
            to={modelerHref}
            title={openFile}
            aria-label={openFile}
            className="flex size-7 items-center justify-center rounded-md no-underline hover:bg-muted hover:text-info"
          >
            <Eye className="size-4" strokeWidth={1.8} aria-hidden />
          </Link>
        )}
        <button
          type="button"
          title={t('processModelDetail.files.download')}
          onClick={() => void handleDownload()}
          className="flex size-7 items-center justify-center rounded-md hover:bg-muted hover:text-info"
        >
          <Download className="size-4" strokeWidth={1.8} aria-hidden />
        </button>
        {canPrimary ? (
          <button
            type="button"
            title={t('processModelDetail.files.setPrimary')}
            onClick={() => void onSetPrimary?.(file.name)}
            className="flex size-7 items-center justify-center rounded-md hover:bg-muted hover:text-info"
          >
            <Star className="size-4" strokeWidth={1.8} aria-hidden />
          </button>
        ) : null}
        {canManage && onDelete && !file.primary ? (
          <button
            type="button"
            title={t('processModelDetail.files.delete')}
            onClick={() => void onDelete(file.name)}
            className="flex size-7 items-center justify-center rounded-md hover:bg-muted hover:text-destructive"
          >
            <Trash2 className="size-4" strokeWidth={1.8} aria-hidden />
          </button>
        ) : null}
      </div>
    </div>
  );
}

export type ProcessModelOverviewProps = {
  detail: ProcessModelDetail;
  /** Needed for each file row's Download fetch — same tenant scope as the
   * detail fetch itself (super-admin's selected tenant, or null for
   * regular users whose tenant is cookie-scoped server-side). */
  tenantId?: string | null;
  canManage?: boolean;
  onUpdateIdentity?: (patch: { display_name: string; description: string }) => Promise<void>;
  onAddFile?: (input: { file_name: string; content?: string }) => Promise<void>;
  onDeleteFile?: (fileName: string) => Promise<void>;
  onSetPrimary?: (fileName: string) => Promise<void>;
  /** Direct permission-check result for starting a process instance. */
  onStart?: () => Promise<void>;
  /** Catalog write: tenant-admin / editor; not super-admin. */
  onCopy?: (input: { id: string; display_name: string }) => Promise<{ id: string }>;
  /** POST /m8flow/templates: same catalog managers as Copy. Super-admin stays disabled. */
  onSaveAsTemplate?: (templateId: number) => void;
  /** Publish lifecycle transition (M8F-508). Same catalog-write gate as Copy.
   * Should reject (throw) on failure so the reason can be surfaced. */
  onChangeStatus?: (status: ProcessModelStatus) => Promise<void>;
  onRunBpmnTests?: () => Promise<ProcessModelTestRunResult>;
  onFetchScriptUnitTests?: () => Promise<ScriptUnitTest[]>;
  onCreateScriptUnitTest?: (input: {
    bpmn_task_identifier: string;
    input_json: Record<string, unknown>;
    expected_output_json: Record<string, unknown>;
  }) => Promise<{ id: string }>;
  onRunScriptUnitTest?: (input: { unit_test_id: string }) => Promise<ScriptUnitTestRunResult>;
};

/**
 * Process-model overview layout matching Processes.dc.html inModel.
 * Live fields come from the detail API; mockup-only extras are omitted or
 * placeholder. Header Copy / Edit identity live in the overflow menu when
 * wired; Save as template is live for catalog managers (not super-admin);
 * Start is live when `onStart` is provided (same gate as the processes list).
 * Tests are live for catalog managers.
 */
export function ProcessModelOverview({
  detail,
  tenantId,
  canManage = false,
  onUpdateIdentity,
  onAddFile,
  onDeleteFile,
  onSetPrimary,
  onStart,
  onCopy,
  onSaveAsTemplate,
  onChangeStatus,
  onRunBpmnTests,
  onFetchScriptUnitTests,
  onCreateScriptUnitTest,
  onRunScriptUnitTest,
}: ProcessModelOverviewProps) {
  const { t } = useTranslation();
  const canEditModel = canManage;
  const navigate = useNavigate();
  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState(detail.display_name);
  const [editDescription, setEditDescription] = useState(detail.description);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [changingStatus, setChangingStatus] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);
  const [saveAsTemplateOpen, setSaveAsTemplateOpen] = useState(false);

  async function handleDeleteFile() {
    if (!pendingDelete || !onDeleteFile) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await onDeleteFile(pendingDelete);
      setPendingDelete(null);
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : t('processModelDetail.files.deleteFailed'));
    } finally {
      setDeleting(false);
    }
  }

  const groupHref = `/processes?group=${encodeURIComponent(detail.group_id)}`;
  const viewAllLabel = t('processModelDetail.instances.viewAll', { total: detail.runs_30d });
  // "View all" pre-filters the shared Process Instances list to this
  // model's own display name — an approximate filter (substring match on
  // `search`, not a hard process-model-id constraint; see
  // ProcessInstancesPage's own doc comment), not a guarantee every result
  // belongs to this exact model. Accepted since the alternative was
  // teaching that page a dedicated process-model-id filter param for one
  // entry point.
  async function changeStatus(status: ProcessModelStatus) {
    if (!onChangeStatus || changingStatus) return;
    setChangingStatus(true);
    setStatusError(null);
    try {
      await onChangeStatus(status);
    } catch (err: unknown) {
      const reason =
        err instanceof ApiError && err.serverMessage
          ? err.serverMessage
          : err instanceof Error
            ? err.message
            : t('processModelDetail.header.statusUpdateFailed');
      setStatusError(reason);
    } finally {
      setChangingStatus(false);
    }
  }

  const status = normalizeProcessModelStatus(detail.status);
  const isPublished = status === 'published';
  const viewAllHref = `/process-instances?search=${encodeURIComponent(detail.display_name)}`;
  const primaryFile = detail.files.find((f) => f.primary);
  const modelerHref = canEditModel && primaryFile
    ? `/processes/${encodeProcessModelId(detail.id)}/modeler/${encodeURIComponent(primaryFile.name)}`
    : null;

  return (
    <div data-testid="process-model-detail">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mb-1.5 rounded-full font-semibold"
            onClick={() => navigate('/processes')}
          >
            <ChevronLeft className="size-3.5" strokeWidth={2} aria-hidden />
            {t('processModelDetail.allProcesses')}
          </Button>
          <h1 className="font-display text-[32px] font-semibold tracking-tight break-words text-foreground">
            {detail.display_name}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2.5" data-testid="process-model-status">
            <Pill {...processModelStatusToPillProps(detail.status)} />
            <span className="text-[13px] text-muted-foreground">
              {processModelStatusHint(detail.status)}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Lifecycle decides the primary action: an unpublished model gets
              Publish (Resume when paused), a published one gets Start. Start
              is never shown for draft/paused -- workflow.start refuses them
              with a 409. */}
          {modelerHref ? (
            <Button asChild variant={isPublished ? 'pill-dark' : 'pill-outline'} size="pill">
              <Link to={modelerHref} className="no-underline">
                <Pencil className="size-[15px]" strokeWidth={2} aria-hidden />
                {isPublished ? t('processModelDetail.header.editInModeler') : t('processModelDetail.header.openInModeler')}
              </Link>
            </Button>
          ) : canEditModel ? (
            <Button type="button" disabled variant="pill-outline" size="pill" className={inertBtn}>
              <Pencil className="size-[15px]" strokeWidth={2} aria-hidden />
              {t('processModelDetail.header.openInModeler')}
            </Button>
          ) : null}
          {!isPublished && onChangeStatus ? (
            <Button
              type="button"
              variant="pill"
              size="pill"
              disabled={changingStatus}
              onClick={() => void changeStatus('published')}
            >
              <Send className="size-[15px]" strokeWidth={2} aria-hidden />
              {changingStatus
                ? status === 'paused'
                  ? t('processModelDetail.header.resuming')
                  : t('processModelDetail.header.publishing')
                : status === 'paused'
                  ? t('processModelDetail.header.resume')
                  : t('processModelDetail.header.publish')}
            </Button>
          ) : null}
          {isPublished && onStart ? (
            <Button
              type="button"
              variant="pill"
              size="pill"
              disabled={starting}
              onClick={async () => {
                setStarting(true);
                setStartError(null);
                try {
                  await onStart();
                } catch (err: unknown) {
                  setStartError(startErrorMessage(err, detail.display_name));
                } finally {
                  setStarting(false);
                }
              }}
            >
              <Play className="size-[15px]" strokeWidth={2} aria-hidden />
              {starting ? t('processModelDetail.header.starting') : t('processModelDetail.header.startProcess')}
            </Button>
          ) : null}
          <HeaderActionsMenu
            onEditIdentity={
              canManage && onUpdateIdentity
                ? () => {
                    setEditName(detail.display_name);
                    setEditDescription(detail.description);
                    setEditError(null);
                    setEditOpen(true);
                  }
                : undefined
            }
            onCopy={onCopy ? () => setCopyOpen(true) : undefined}
            onSaveAsTemplate={onSaveAsTemplate ? () => setSaveAsTemplateOpen(true) : undefined}
            status={status}
            onChangeStatus={onChangeStatus ? changeStatus : undefined}
          />
        </div>
      </div>

      {startError ? (
        <p className="mb-3 text-sm text-destructive" role="alert">
          {startError}
        </p>
      ) : null}

      {statusError ? (
        <p className="mb-3 text-sm text-destructive" role="alert">
          {statusError}
        </p>
      ) : null}

      <div className="mb-3 flex flex-wrap items-center gap-x-3.5 gap-y-2.5">
        <Link
          to={groupHref}
          className="inline-flex max-w-full items-center gap-1.5 text-[12.5px] text-info no-underline"
        >
          <Folder className="size-3.5 shrink-0" strokeWidth={1.8} />
          <span className="min-w-0 truncate">{detail.group_display_name || detail.group_id}</span>
        </Link>
      </div>

      {detail.description ? (
        <p className="mb-[18px] max-w-[820px] text-[14.5px] leading-normal text-muted-foreground">
          {detail.description}
        </p>
      ) : null}

      <div
        className="mb-[18px] grid min-w-0 grid-cols-2 overflow-hidden rounded-[14px] border border-border sm:grid-cols-3 lg:grid-cols-5"
        style={{ gap: 1, background: 'var(--border)' }}
      >
        <KeyNumber label={t('processModelDetail.stats.lastRun')} value={formatRelativeTime(detail.last_run_at)} />
        <KeyNumber label={t('processModelDetail.stats.runningNow')} value={String(detail.running_now)} mono />
        <KeyNumber label={t('processModelDetail.stats.runs30d')} value={String(detail.runs_30d)} mono />
        <KeyNumber label={t('processModelDetail.stats.medianTime')} value="—" mono placeholder />
        <KeyNumber label={t('processModelDetail.stats.errors30d')} value="—" mono placeholder />
      </div>

      <div className="mb-[22px] grid grid-cols-1 gap-x-7 gap-y-3.5 rounded-[14px] border border-border bg-card px-[22px] py-[18px] shadow-xs sm:grid-cols-2">
        <Fact label={t('processModelDetail.facts.group')}>
          <Link to={groupHref} className="min-w-0 break-words no-underline">
            {detail.group_display_name || detail.group_id}
          </Link>
        </Fact>
        <Fact label={t('processModelDetail.facts.identifier')}>
          <span className="font-mono text-xs break-all">{detail.id}</span>
        </Fact>
      </div>

      <div className="mb-[18px] flex flex-wrap items-center gap-2">
        <a
          href="#instances"
          className="rounded-full border border-border px-3.5 py-1.5 text-[12.5px] font-semibold text-foreground no-underline"
        >
          {t('processModelDetail.nav.instances')}
        </a>
        <a
          href="#files"
          className="rounded-full border border-border px-3.5 py-1.5 text-[12.5px] font-semibold text-foreground no-underline"
        >
          {t('processModelDetail.nav.files', { total: detail.files.length })}
        </a>
        {canManage ? (
          <a
            href="#tests"
            className="rounded-full border border-border px-3.5 py-1.5 text-[12.5px] font-semibold text-foreground no-underline"
          >
            {t('processModelDetail.nav.tests')}
          </a>
        ) : null}
      </div>

      <Card id="instances" variant="bordered" className="mb-[22px] overflow-x-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-[22px] py-4">
          <h2 className="text-[15px] font-semibold text-foreground">{t('processModelDetail.instances.title')}</h2>
          <Link
            to={viewAllHref}
            className="text-[12.5px] font-semibold text-info no-underline hover:underline"
          >
            {viewAllLabel}
          </Link>
        </div>
        <DataTable
          columns={recentInstanceColumns(t)}
          rows={detail.recent_instances}
          getRowKey={(row) => row.id}
          emptyState={t('processModelDetail.instances.empty')}
          minWidth="620px"
        />
      </Card>

      <Card id="files" variant="bordered" className="mb-[22px]">
        <div className="px-[22px] pt-4 pb-5">
          <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-[15px] font-semibold text-foreground">{t('processModelDetail.files.title')}</h2>
              <p className="mt-0.5 text-[12.5px] text-muted-foreground">{t('processModelDetail.files.subtitle')}</p>
            </div>
            {canManage && onAddFile ? (
              <Button
                type="button"
                variant="pill-outline"
                size="pill"
                onClick={() => setAddOpen(true)}
              >
                <Plus className="size-4" strokeWidth={2} aria-hidden />
                {t('processModelDetail.files.addFile')}
              </Button>
            ) : null}
          </div>
          <div className="overflow-hidden rounded-xl border border-border">
            {detail.files.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13.5px] text-muted-foreground">{t('processModelDetail.files.empty')}</p>
            ) : (
              detail.files.map((file) => (
                <FileRow
                  key={file.name}
                  file={file}
                  modelId={detail.id}
                  tenantId={tenantId}
                  canManage={canEditModel}
                  onSetPrimary={onSetPrimary}
                  onDelete={onDeleteFile ? (name) => { setDeleteError(null); setPendingDelete(name); } : undefined}
                />
              ))
            )}
          </div>
        </div>
      </Card>
      {onRunBpmnTests || onFetchScriptUnitTests || onCreateScriptUnitTest || onRunScriptUnitTest ? (
        <ProcessModelTestsCard
          hasBpmnTests={detail.files.some((file) => /^test_.*\.json$/i.test(file.name))}
          onRunBpmnTests={onRunBpmnTests}
          onFetchScriptUnitTests={onFetchScriptUnitTests}
          onCreateScriptUnitTest={onCreateScriptUnitTest}
          onRunScriptUnitTest={onRunScriptUnitTest}
        />
      ) : null}
      <Modal
        open={editOpen}
        onOpenChange={(next) => { if (!next) setEditOpen(false); }}
        title={t('processModelDetail.editIdentity.title')}
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => setEditOpen(false)} disabled={saving}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" form="edit-pm-identity-form" disabled={saving}>
              {saving ? t('processModelDetail.editIdentity.saving') : t('processModelDetail.editIdentity.save')}
            </Button>
          </>
        }
      >
        <p className="-mt-1 text-sm text-muted-foreground">
          {t('processModelDetail.editIdentity.hint')}
        </p>
        <form
          id="edit-pm-identity-form"
          className="flex flex-col gap-4"
          onSubmit={async (event: FormEvent) => {
            event.preventDefault();
            if (!onUpdateIdentity) return;
            setSaving(true);
            setEditError(null);
            try {
              await onUpdateIdentity({
                display_name: editName.trim(),
                description: editDescription.trim(),
              });
              setEditOpen(false);
            } catch (err: unknown) {
              setEditError(err instanceof Error ? err.message : t('processModelDetail.editIdentity.failed'));
            } finally {
              setSaving(false);
            }
          }}
        >
          <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
            {t('processModelDetail.displayName')}
            <Input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              aria-label={t('processModelDetail.editIdentity.displayNameAria')}
            />
          </label>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
            {t('common.description')}
            <Input
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              aria-label={t('processModelDetail.editIdentity.descriptionAria')}
            />
          </label>
          {editError ? (
            <p className="text-sm text-destructive" role="alert">
              {editError}
            </p>
          ) : null}
        </form>
      </Modal>
      {onCopy ? (
        <CopyProcessModelDialog
          open={copyOpen}
          onClose={() => setCopyOpen(false)}
          defaultLeaf={`${detail.id.split('/').pop() || 'model'}-copy`}
          defaultDisplayName={t('processModelDetail.copy.defaultDisplayName', { name: detail.display_name })}
          onCopy={onCopy}
          onCopied={() => setCopyOpen(false)}
        />
      ) : null}
      {onSaveAsTemplate ? (
        <SaveAsTemplateDialog
          open={saveAsTemplateOpen}
          onClose={() => setSaveAsTemplateOpen(false)}
          defaultName={detail.display_name}
          getFiles={async () => {
            const supported = detail.files.filter((file) => isSupportedTemplateSourceFile(file.name));
            const packed = await Promise.all(
              supported.map(async (file) => {
                const text = await fetchProcessModelFileContent(
                  encodeProcessModelId(detail.id),
                  file.name,
                  tenantId,
                );
                return {
                  name: file.name,
                  content: new Blob([text], { type: mimeForTemplateSourceFile(file.name) }),
                };
              }),
            );
            const primaryName = detail.files.find((file) => file.primary)?.name ?? '';
            return sortFilesPrimaryFirst(packed, primaryName);
          }}
          onCreated={(templateId) => {
            setSaveAsTemplateOpen(false);
            onSaveAsTemplate(templateId);
          }}
        />
      ) : null}
      {canManage && onAddFile ? (
        <AddProcessModelFileDialog
          open={addOpen}
          onClose={() => setAddOpen(false)}
          existingNames={detail.files.map((f) => f.name)}
          onCreate={onAddFile}
          onCreated={(fileName) => {
            setAddOpen(false);
            if (fileOpensInModeler(fileName)) {
              navigate(
                `/processes/${encodeProcessModelId(detail.id)}/modeler/${encodeURIComponent(fileName)}`,
              );
            }
          }}
        />
      ) : null}
      <ConfirmDialog
        open={pendingDelete != null}
        onOpenChange={(next) => {
          if (!next && !deleting) {
            setPendingDelete(null);
            setDeleteError(null);
          }
        }}
        title={t('processModelDetail.files.delete')}
        description={
          <>
            {pendingDelete
              ? t('processModelDetail.files.deleteConfirm', { name: pendingDelete })
              : t('processModelDetail.files.deleteConfirmGeneric')}
            {deleteError ? (
              <span className="mt-2 block text-destructive" role="alert">
                {deleteError}
              </span>
            ) : null}
          </>
        }
        confirmLabel={deleting ? t('processModelDetail.files.deleting') : t('common.delete')}
        pending={deleting}
        onConfirm={() => void handleDeleteFile()}
      />
    </div>
  );
}

function KeyNumber({
  label,
  value,
  mono,
  placeholder,
}: {
  label: string;
  value: string;
  mono?: boolean;
  placeholder?: boolean;
}) {
  return (
    <div className="bg-card px-[18px] py-3.5">
      <div className="text-[11px] tracking-[0.05em] text-muted-foreground uppercase">{label}</div>
      <div
        className={cn(
          'mt-1.5 text-base font-semibold whitespace-nowrap',
          mono && 'font-mono font-bold',
          placeholder ? 'text-muted-foreground' : 'text-foreground',
        )}
      >
        {value}
      </div>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 gap-2.5 text-[13px]">
      <span className="w-[78px] shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}
