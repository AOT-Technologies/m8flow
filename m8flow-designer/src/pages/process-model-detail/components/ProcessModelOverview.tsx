import { Download, Folder, Pencil, Plus, Star, Trash2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useState, type FormEvent, type ReactNode } from 'react';

import {
  fetchProcessModelFileContent,
  type ProcessModelDetail,
  type ProcessModelDetailFile,
  type ProcessModelDetailInstance,
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
import { BackLink } from '@/components/library/breadcrumbs/Breadcrumbs';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Modal } from '@/components/library/modal/Modal';
import { Pill } from '@/components/library/pill/Pill';
import { processInstanceStatusToPillProps } from '@/components/library/pill/processInstanceStatusToPillProps';
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

/** Adapter passed to `BackLink`'s `LinkComponent` for client-side navigation
 * (component-adoption map, ticket 07). */
function RouterBackLink({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link to={href} className={className}>
      {children}
    </Link>
  );
}

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

const recentInstanceColumns: DataTableColumn<ProcessModelDetailInstance>[] = [
  {
    key: 'id',
    header: 'ID',
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
    header: 'Started by',
    width: 'minmax(120px,1fr)',
    className: 'truncate text-[13.5px] text-foreground',
    render: (row) => row.started_by || '—',
  },
  {
    key: 'start',
    header: 'Start',
    width: 'minmax(0,120px)',
    className: 'whitespace-nowrap text-[13px] text-muted-foreground',
    render: (row) => formatRelativeTime(row.start_in_seconds),
  },
  {
    key: 'duration',
    header: 'Duration',
    width: 'minmax(0,100px)',
    className: 'font-mono text-[13px] text-muted-foreground',
    render: (row) => formatDuration(row.duration_seconds),
  },
  {
    key: 'status',
    header: 'Status',
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
      return { ext: 'JSON', label: 'BPMN test' };
    }
    if (lower.includes('uischema')) {
      return { ext: 'JSON', label: 'UI schema' };
    }
    if (lower.includes('schema')) {
      return { ext: 'JSON', label: 'Form schema' };
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
  const kind = fileKind(file.name);
  const meta = `${kind.label} · ${formatBytes(file.size_bytes)} · updated ${formatRelativeTime(file.updated_at_in_seconds)}`;
  const iconTone = kind.ext === 'BPMN' ? 'bg-nav-active/15 text-info' : 'bg-muted text-muted-foreground';
  const modelerHref = `/processes/${encodeProcessModelId(modelId)}/modeler/${encodeURIComponent(file.name)}`;
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
        <div className="break-words text-[13.5px] text-foreground">{file.name}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{meta}</div>
      </div>
      {file.primary ? (
        <Pill tone="info" dot={false} className="shrink-0">
          Primary
        </Pill>
      ) : null}
      <div className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
        <Link
          to={modelerHref}
          title="Edit file"
          className="flex size-7 items-center justify-center rounded-md no-underline hover:bg-muted hover:text-info"
        >
          <Pencil className="size-4" strokeWidth={1.8} aria-hidden />
        </Link>
        <button
          type="button"
          title="Download file"
          onClick={() => void handleDownload()}
          className="flex size-7 items-center justify-center rounded-md hover:bg-muted hover:text-info"
        >
          <Download className="size-4" strokeWidth={1.8} aria-hidden />
        </button>
        {canPrimary ? (
          <button
            type="button"
            title="Set as primary"
            onClick={() => void onSetPrimary?.(file.name)}
            className="flex size-7 items-center justify-center rounded-md hover:bg-muted hover:text-info"
          >
            <Star className="size-4" strokeWidth={1.8} aria-hidden />
          </button>
        ) : null}
        {canManage && onDelete && !file.primary ? (
          <button
            type="button"
            title="Delete file"
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
  /** Same start permission as the processes list (`canManageProcesses`). */
  onStart?: () => Promise<void>;
  /** Catalog write: tenant-admin / editor; not super-admin. */
  onCopy?: (input: { id: string; display_name: string }) => Promise<{ id: string }>;
  /** POST /m8flow/templates: same catalog managers as Copy. Super-admin stays disabled. */
  onSaveAsTemplate?: (templateId: number) => void;
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
  onRunBpmnTests,
  onFetchScriptUnitTests,
  onCreateScriptUnitTest,
  onRunScriptUnitTest,
}: ProcessModelOverviewProps) {
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
      setDeleteError(err instanceof Error ? err.message : 'Failed to delete file');
    } finally {
      setDeleting(false);
    }
  }

  const groupHref = `/processes?group=${encodeURIComponent(detail.group_id)}`;
  const viewAllLabel = `View all ${detail.runs_30d}`;
  // "View all" pre-filters the shared Process Instances list to this
  // model's own display name — an approximate filter (substring match on
  // `search`, not a hard process-model-id constraint; see
  // ProcessInstancesPage's own doc comment), not a guarantee every result
  // belongs to this exact model. Accepted since the alternative was
  // teaching that page a dedicated process-model-id filter param for one
  // entry point.
  const viewAllHref = `/process-instances?search=${encodeURIComponent(detail.display_name)}`;
  const primaryFile = detail.files.find((f) => f.primary);
  const modelerHref = primaryFile
    ? `/processes/${encodeProcessModelId(detail.id)}/modeler/${encodeURIComponent(primaryFile.name)}`
    : null;

  return (
    <div data-testid="process-model-detail">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <BackLink href="/processes" LinkComponent={RouterBackLink} className="mb-1.5">
            All processes
          </BackLink>
          <h1 className="font-display text-[32px] font-semibold tracking-tight break-words text-foreground">
            {detail.display_name}
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {onStart ? (
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
              {starting ? 'Starting…' : 'Start process'}
            </Button>
          ) : (
            <Button type="button" disabled variant="pill" size="pill" className={inertBtn}>
              Start process
            </Button>
          )}
          {modelerHref ? (
            <Button asChild variant="pill-dark" size="pill">
              <Link to={modelerHref} className="no-underline">
                <Pencil className="size-[15px]" strokeWidth={2} aria-hidden />
                Open in modeler
              </Link>
            </Button>
          ) : (
            <Button type="button" disabled variant="pill-dark" size="pill" className={inertBtn}>
              <Pencil className="size-[15px]" strokeWidth={2} aria-hidden />
              Open in modeler
            </Button>
          )}
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
          />
        </div>
      </div>

      {startError ? (
        <p className="mb-3 text-sm text-destructive" role="alert">
          {startError}
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
        <KeyNumber label="Last run" value={formatRelativeTime(detail.last_run_in_seconds)} />
        <KeyNumber label="Running now" value={String(detail.running_now)} mono />
        <KeyNumber label="Runs 30d" value={String(detail.runs_30d)} mono />
        <KeyNumber label="Median time" value="—" mono placeholder />
        <KeyNumber label="Errors 30d" value="—" mono placeholder />
      </div>

      <div className="mb-[22px] grid grid-cols-1 gap-x-7 gap-y-3.5 rounded-[14px] border border-border bg-card px-[22px] py-[18px] shadow-xs sm:grid-cols-2">
        <Fact label="Group">
          <Link to={groupHref} className="min-w-0 break-words no-underline">
            {detail.group_display_name || detail.group_id}
          </Link>
        </Fact>
        <Fact label="Identifier">
          <span className="font-mono text-xs break-all">{detail.id}</span>
        </Fact>
      </div>

      <div className="mb-[18px] flex flex-wrap items-center gap-2">
        <a
          href="#instances"
          className="rounded-full border border-border px-3.5 py-1.5 text-[12.5px] font-semibold text-foreground no-underline"
        >
          Instances
        </a>
        <a
          href="#files"
          className="rounded-full border border-border px-3.5 py-1.5 text-[12.5px] font-semibold text-foreground no-underline"
        >
          Files ({detail.files.length})
        </a>
        <a
          href="#tests"
          className="rounded-full border border-border px-3.5 py-1.5 text-[12.5px] font-semibold text-foreground no-underline"
        >
          Tests
        </a>
      </div>

      <Card id="instances" variant="bordered" className="mb-[22px] overflow-x-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-[22px] py-4">
          <h2 className="text-[15px] font-semibold text-foreground">Recent instances</h2>
          <Link
            to={viewAllHref}
            className="text-[12.5px] font-semibold text-info no-underline hover:underline"
          >
            {viewAllLabel}
          </Link>
        </div>
        <DataTable
          columns={recentInstanceColumns}
          rows={detail.recent_instances}
          getRowKey={(row) => row.id}
          emptyState="No instances yet."
          minWidth="620px"
        />
      </Card>

      <Card id="files" variant="bordered" className="mb-[22px]">
        <div className="px-[22px] pt-4 pb-5">
          <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-[15px] font-semibold text-foreground">Files</h2>
              <p className="mt-0.5 text-[12.5px] text-muted-foreground">BPMN, form schema and UI schema</p>
            </div>
            {canManage && onAddFile ? (
              <Button
                type="button"
                variant="pill-outline"
                size="pill"
                className="gap-1.5 px-3.5 py-1.5 text-xs"
                onClick={() => setAddOpen(true)}
              >
                <Plus className="size-3.5" strokeWidth={2.2} aria-hidden />
                Add file
              </Button>
            ) : (
              <Button
                type="button"
                disabled
                variant="pill-outline"
                size="pill"
                className={cn(inertBtn, 'gap-1.5 px-3.5 py-1.5 text-xs')}
              >
                <Plus className="size-3.5" strokeWidth={2.2} aria-hidden />
                Add file
              </Button>
            )}
          </div>
          <div className="overflow-hidden rounded-xl border border-border">
            {detail.files.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13.5px] text-muted-foreground">No files yet.</p>
            ) : (
              detail.files.map((file) => (
                <FileRow
                  key={file.name}
                  file={file}
                  modelId={detail.id}
                  tenantId={tenantId}
                  canManage={canManage}
                  onSetPrimary={onSetPrimary}
                  onDelete={onDeleteFile ? (name) => { setDeleteError(null); setPendingDelete(name); } : undefined}
                />
              ))
            )}
          </div>
        </div>
      </Card>
      <ProcessModelTestsCard
        canManage={canManage}
        hasBpmnTests={detail.files.some((file) => /^test_.*\.json$/i.test(file.name))}
        onRunBpmnTests={onRunBpmnTests}
        onFetchScriptUnitTests={onFetchScriptUnitTests}
        onCreateScriptUnitTest={onCreateScriptUnitTest}
        onRunScriptUnitTest={onRunScriptUnitTest}
      />
      <Modal
        open={editOpen}
        onOpenChange={(next) => { if (!next) setEditOpen(false); }}
        title="Edit process model"
        footer={
          <>
            <Button type="button" variant="outline" onClick={() => setEditOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" form="edit-pm-identity-form" disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </>
        }
      >
        <p className="-mt-1 text-sm text-muted-foreground">
          Display name and description only. The identifier does not change.
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
              setEditError(err instanceof Error ? err.message : 'Failed to update process model');
            } finally {
              setSaving(false);
            }
          }}
        >
          <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
            Display name
            <Input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              aria-label="Process model display name"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
            Description
            <Input
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              aria-label="Process model description"
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
          defaultDisplayName={`${detail.display_name} (copy)`}
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
        title="Delete file"
        description={
          <>
            {pendingDelete ? `Delete ${pendingDelete}? This cannot be undone.` : 'Delete this file?'}
            {deleteError ? (
              <span className="mt-2 block text-destructive" role="alert">
                {deleteError}
              </span>
            ) : null}
          </>
        }
        confirmLabel={deleting ? 'Deleting…' : 'Delete'}
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
