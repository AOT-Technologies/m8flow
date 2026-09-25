import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from 'react';
import {
  CircleSlash,
  ExternalLink,
  Folder,
  PauseCircle,
  Plus,
  Send,
  Trash2,
} from 'lucide-react';

import {
  ApiError,
  type ProcessModelListItem,
  type ProcessModelStatus,
} from '@/lib/api';
import { ActionMenu } from '@/components/library/action-menu/ActionMenu';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { EmptyState } from '@/components/library/empty-state/EmptyState';
import { Pill } from '@/components/library/pill/Pill';
import {
  normalizeProcessModelStatus,
  processModelStatusToPillProps,
} from '@/components/library/pill/processModelStatusToPillProps';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { SortDropdown } from '@/components/library/sort-dropdown/SortDropdown';
import type { ProcessInstanceOwnerOption } from '@/lib/processInstancesApi';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { formatRelativeTime } from '@/lib/relativeTime';
import { cn } from '@/lib/utils';

const SORT_OPTIONS = [
  { value: 'desc', label: 'Newest first' },
  { value: 'asc', label: 'Oldest first' },
];

const STATUS_FILTER_OPTIONS = [
  { value: 'all', label: 'Any status' },
  { value: 'published', label: 'Published' },
  { value: 'draft', label: 'Draft' },
  { value: 'paused', label: 'Paused' },
];

// Process-model rows do not currently expose an owner field. The owner
// dropdown therefore uses stable ids supplied by the owner-options endpoint.
const OWNER_FILTER_OPTIONS = [{ value: 'all', label: 'All owners' }];

type StatusFilter = 'all' | ProcessModelStatus;

export type ProcessesModelsListProps = {
  models: ProcessModelListItem[];
  loading?: boolean;
  error?: string | null;
  /** Active group filter id from `?group=`; null = all groups. */
  groupFilter?: string | null;
  /** Label for the scope pill (group display name or id). */
  scopeLabel?: string;
  /** Process initiators with stable ids and display usernames. */
  owners?: ProcessInstanceOwnerOption[];
  ownerFilter?: string;
  onOwnerFilterChange?: (value: string) => void;
  /** Total models before client search (for empty-state copy). */
  totalUnfilteredCount?: number;
  onBrowseGroups?: () => void;
  onClearGroupFilter?: () => void;
  onOpenModel?: (model: ProcessModelListItem) => void;
  onFilterByGroup?: (groupId: string) => void;
  /** Starts an instance from the model; parent handles navigation. */
  onStartModel?: (model: ProcessModelListItem) => void;
  /** Deletes the model. Should reject (throw) on failure so the confirmation
   * dialog can surface the reason (e.g. a 409 when instances still exist). */
  onDeleteModel?: (model: ProcessModelListItem) => Promise<void> | void;
  /** Opens the create dialog. Absent for viewers / super-admin. */
  onCreateModel?: () => void;
  /** Omitted without catalog write. Opens the group picker on its create form. */
  onCreateGroup?: () => void;
  /** All-Tenants super-admin view: adds a Tenant column so rows from
   * different tenants (which can share a model id) stay distinguishable. */
  showTenant?: boolean;
  /** Moves a model through the publish lifecycle. Absent for users who can't
   * manage processes, so they see no action that would 403. Should reject
   * (throw) on failure so the row can surface the reason. */
  onChangeModelStatus?: (
    model: ProcessModelListItem,
    status: ProcessModelStatus,
  ) => Promise<void> | void;
};

type SortDir = 'desc' | 'asc';

/**
 * Processes models list — matches Processes.dc.html list surface.
 * Presentational: parent owns fetch, tenant gating, and navigation.
 */
export function ProcessesModelsList({
  models,
  loading = false,
  error = null,
  groupFilter = null,
  scopeLabel = 'All groups',
  owners = [],
  ownerFilter = 'all',
  onOwnerFilterChange,
  totalUnfilteredCount,
  onBrowseGroups,
  onClearGroupFilter,
  onOpenModel,
  onFilterByGroup,
  onStartModel,
  onDeleteModel,
  onCreateModel,
  onCreateGroup,
  showTenant = false,
  onChangeModelStatus,
}: ProcessesModelsListProps) {
  const [search, setSearch] = useState('');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [statusError, setStatusError] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Delete confirmation dialog state.
  const [deleteTarget, setDeleteTarget] = useState<ProcessModelListItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function confirmDelete() {
    if (!deleteTarget || !onDeleteModel) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await onDeleteModel(deleteTarget);
      setDeleteTarget(null);
    } catch (err: unknown) {
      // A 409 means the model still has instances (the backend's block) —
      // give that its own message rather than a generic failure.
      if (err instanceof ApiError && err.status === 409) {
        setDeleteError(
          'This process model still has process instances and can’t be deleted. ' +
            'Remove or finish its instances first.',
        );
      } else {
        setDeleteError(err instanceof Error ? err.message : 'Failed to delete process model');
      }
    } finally {
      setDeleting(false);
    }
  }

  useEffect(() => {
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  async function changeStatus(model: ProcessModelListItem, status: ProcessModelStatus) {
    if (!onChangeModelStatus) return;
    setStatusError(null);
    try {
      await onChangeModelStatus(model, status);
    } catch (err: unknown) {
      const reason =
        err instanceof ApiError && err.serverMessage
          ? err.serverMessage
          : err instanceof Error
            ? err.message
            : 'Failed to update status';
      setStatusError(`${model.display_name}: ${reason}`);
    }
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = models;
    if (statusFilter !== 'all') {
      rows = rows.filter((m) => normalizeProcessModelStatus(m.status) === statusFilter);
    }
    if (q) {
      rows = rows.filter(
        (m) =>
          m.display_name.toLowerCase().includes(q) ||
          m.id.toLowerCase().includes(q) ||
          m.group_display_name.toLowerCase().includes(q) ||
          m.group_id.toLowerCase().includes(q),
      );
    }
    const sorted = [...rows].sort((a, b) => {
      const aVal = a.last_run_in_seconds ?? -1;
      const bVal = b.last_run_in_seconds ?? -1;
      return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
    });
    return sorted;
  }, [models, search, sortDir, statusFilter]);

  // Counts come off the already-fetched list rather than a second endpoint.
  const statusCounts = useMemo(() => {
    const counts = { all: models.length, published: 0, draft: 0, paused: 0 };
    for (const model of models) {
      const status = normalizeProcessModelStatus(model.status);
      if (status === 'published') counts.published += 1;
      else if (status === 'paused') counts.paused += 1;
      else counts.draft += 1;
    }
    return counts as Record<StatusFilter, number>;
  }, [models]);

  const resultCount = `${filtered.length} model${filtered.length === 1 ? '' : 's'}`;
  const totalForEmpty = totalUnfilteredCount ?? models.length;
  const groupFilterOn = Boolean(groupFilter);
  const isEmpty = !loading && !error && filtered.length === 0;

  function stopRowNav(event: MouseEvent) {
    event.stopPropagation();
  }

  function onSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setSearch('');
      searchRef.current?.blur();
    }
  }

  const columns: DataTableColumn<ProcessModelListItem>[] = [
    ...(showTenant
      ? [
          {
            key: 'tenant',
            header: 'Tenant',
            width: '140px',
            className: 'truncate text-[13px] text-muted-foreground',
            render: (model: ProcessModelListItem) =>
              model.tenant_name || model.tenant_id || '—',
          } as DataTableColumn<ProcessModelListItem>,
        ]
      : []),
    {
      key: 'model',
      header: 'Process model',
      width: 'minmax(220px,2.4fr)',
      render: (model) => (
        <div className="min-w-0">
          <div className="line-clamp-2 text-[14.5px] leading-snug font-semibold text-foreground">
            {model.display_name}
          </div>
          <button
            type="button"
            onClick={(e) => {
              stopRowNav(e);
              onFilterByGroup?.(model.group_id);
            }}
            className="mt-1 flex max-w-full items-center gap-1.5 text-left text-[12.5px] text-muted-foreground"
          >
            <Folder className="size-3.5 shrink-0" strokeWidth={1.8} />
            <span className="truncate">{model.group_display_name || model.group_id}</span>
          </button>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: 'minmax(0,140px)',
      render: (model) => <Pill {...processModelStatusToPillProps(model.status)} />,
    },
    {
      key: 'runs30d',
      header: 'Runs 30d',
      width: 'minmax(0,90px)',
      className: 'font-mono text-[13px] text-muted-foreground',
      render: (model) => model.runs_30d,
    },
    {
      key: 'lastRun',
      header: 'Last run',
      width: 'minmax(0,130px)',
      className: 'whitespace-nowrap text-[13px] text-muted-foreground',
      render: (model) => formatRelativeTime(model.last_run_in_seconds),
    },
    {
      key: 'actions',
      header: 'Actions',
      width: 'minmax(0,190px)',
      className: 'text-right',
      render: (model) => (
        <div
          className="flex items-center justify-end gap-2"
          onClick={stopRowNav}
          onKeyDown={(e) => e.stopPropagation()}
        >
          {/* Start is only rendered for users who can manage processes
              (parent passes onStartModel); others don't see it rather
              than get a button that 403s. Draft and paused models are not
              startable at all (workflow.start refuses with a 409), so the
              button is hidden there too rather than offering a dead action. */}
          {onStartModel && normalizeProcessModelStatus(model.status) === 'published' ? (
            <Button
              type="button"
              variant="pill"
              size="pill"
              onClick={() => onStartModel(model)}
              className="px-3.5 py-1.5 text-[11.5px] shadow-none"
            >
              Start
            </Button>
          ) : null}
          <Button
            type="button"
            variant="pill-outline"
            size="pill"
            onClick={() => onOpenModel?.(model)}
            className="border px-3.5 py-1.5 text-[11.5px]"
          >
            Open
          </Button>
          <ActionMenu
            triggerLabel="More actions"
            items={[
              {
                label: 'Open',
                icon: <ExternalLink className="size-3.5" />,
                onSelect: () => onOpenModel?.(model),
              },
              // Lifecycle actions offer only the transitions the backend
              // accepts from the current status — draft has no Pause, since
              // pausing something never published is refused with a 400.
              ...(onChangeModelStatus && normalizeProcessModelStatus(model.status) !== 'published'
                ? [
                    {
                      label:
                        normalizeProcessModelStatus(model.status) === 'paused'
                          ? 'Resume'
                          : 'Publish',
                      icon: <Send className="size-3.5" />,
                      onSelect: () => void changeStatus(model, 'published'),
                    },
                  ]
                : []),
              ...(onChangeModelStatus && normalizeProcessModelStatus(model.status) === 'published'
                ? [
                    {
                      label: 'Pause',
                      icon: <PauseCircle className="size-3.5" />,
                      onSelect: () => void changeStatus(model, 'paused'),
                    },
                  ]
                : []),
              ...(onChangeModelStatus && normalizeProcessModelStatus(model.status) !== 'draft'
                ? [
                    {
                      label: 'Unpublish',
                      icon: <CircleSlash className="size-3.5" />,
                      onSelect: () => void changeStatus(model, 'draft'),
                    },
                  ]
                : []),
              ...(onDeleteModel
                ? [
                    {
                      label: 'Delete',
                      icon: <Trash2 className="size-3.5" />,
                      destructive: true,
                      onSelect: () => setDeleteTarget(model),
                    },
                  ]
                : []),
            ]}
          />
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[32px] font-semibold tracking-tight text-foreground">Processes</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {/* No "Browse groups" button — the "Showing [scope] ▾" pill below opens
              the same picker. Creating a group is a different matter (M8F-530
              #6): the pill reads as a filter, so the only path to New group was
              one people did not find. */}
          {onCreateGroup ? (
            <Button
              type="button"
              variant="pill-outline"
              size="pill"
              onClick={onCreateGroup}
              className="gap-2"
              data-testid="processes-new-group-button"
            >
              <Plus className="size-[15px]" strokeWidth={2.2} />
              New process group
            </Button>
          ) : null}
          {onCreateModel ? (
            <Button type="button" variant="pill" size="pill" onClick={onCreateModel} className="gap-2">
              <Plus className="size-[15px]" strokeWidth={2.2} />
              New process model
            </Button>
          ) : null}
        </div>
      </div>

      <div className="mt-1.5 mb-[22px] flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <span>Showing</span>
        <button
          type="button"
          onClick={onBrowseGroups}
          className={cn(
            'inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1.5 text-[13.5px] font-semibold text-foreground',
            groupFilterOn
              ? 'border-nav-active/40 bg-nav-active/15'
              : 'border-border bg-card',
          )}
        >
          <Folder className="size-3.5 shrink-0" strokeWidth={1.8} />
          <span className="min-w-0 truncate">{scopeLabel}</span>
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="shrink-0"
            aria-hidden
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
        {groupFilterOn ? (
          <button
            type="button"
            onClick={onClearGroupFilter}
            className="px-1 text-[13px] text-info"
          >
            Clear
          </button>
        ) : null}
      </div>

      <div className="pb-14">
        <div className="mb-[18px] flex flex-wrap items-center gap-2.5">
          <SearchBar
            ref={searchRef}
            type="search"
            value={search}
            onChange={setSearch}
            onKeyDown={onSearchKeyDown}
            placeholder="Search process models"
            aria-label="Search process models"
            className="max-w-[420px] min-w-0 flex-1"
          />

          {/* Counts come from the already-fetched rows, so the status filter
              needs no extra request. Owner options come from the existing
              tenant-scoped process-instance owners endpoint. */}
          <SortDropdown
            options={STATUS_FILTER_OPTIONS.map((option) => ({
              ...option,
              label: `${option.label} ${statusCounts[option.value as StatusFilter] ?? 0}`,
            }))}
            value={statusFilter}
            onChange={(value) => setStatusFilter(value as StatusFilter)}
            label="Status"
            className="min-w-0"
          />
          <SortDropdown
            label="Owner"
            options={[
              ...OWNER_FILTER_OPTIONS,
              ...owners.map((owner) => ({ value: String(owner.id), label: owner.username })),
            ]}
            value={ownerFilter}
            onChange={(value) => onOwnerFilterChange?.(value)}
            className="min-w-0"
          />

          <SortDropdown
            options={SORT_OPTIONS}
            value={sortDir}
            onChange={(value) => setSortDir(value as SortDir)}
            className="min-w-0"
          />

          <div className="ml-auto whitespace-nowrap text-[13px] text-muted-foreground">
            {loading ? 'Loading…' : resultCount}
          </div>
        </div>

        {error ? (
          <p className="mb-4 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {statusError ? (
          <p className="mb-4 text-sm text-destructive" role="alert">
            {statusError}
          </p>
        ) : null}

        <Card variant="bordered" className="overflow-x-auto">
          {loading ? (
            <div className="px-[22px] py-8 text-sm text-muted-foreground">Loading process models…</div>
          ) : isEmpty ? (
            <EmptyState
              title={groupFilterOn ? 'No models in this group' : 'No process models'}
              description={
                groupFilterOn
                  ? `Create a model here, or clear the filter to see all ${totalForEmpty} models.`
                  : search.trim()
                    ? 'Try a different search, or clear the search box.'
                    : 'No models are available for this tenant yet.'
              }
              actions={
                <>
                  {onCreateModel ? (
                    <Button type="button" variant="pill" size="pill" onClick={onCreateModel} className="text-xs">
                      New process model
                    </Button>
                  ) : null}
                  {groupFilterOn ? (
                    <Button
                      type="button"
                      variant="pill-outline"
                      size="pill"
                      onClick={onClearGroupFilter}
                      className="text-xs"
                    >
                      Clear filter
                    </Button>
                  ) : null}
                </>
              }
            />
          ) : (
            <DataTable
              columns={columns}
              rows={filtered}
              getRowKey={(model) => model.id}
              onRowClick={(model) => onOpenModel?.(model)}
              minWidth="760px"
            />
          )}

          {!loading && !isEmpty ? (
            <div className="flex flex-wrap items-center justify-between gap-3 px-[22px] py-3.5 text-[13px] text-muted-foreground">
              <span>{resultCount}</span>
              <span className="flex items-center gap-2.5">
                <span>Rows per page: 25</span>
                <span className="font-mono">
                  1–{filtered.length}
                </span>
              </span>
            </div>
          ) : null}
        </Card>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open && !deleting) {
            setDeleteTarget(null);
            setDeleteError(null);
          }
        }}
        title="Delete process model?"
        description={
          deleteTarget ? (
            <>
              This permanently deletes{' '}
              <span className="font-semibold text-foreground">{deleteTarget.display_name}</span>{' '}
              and its files. This can’t be undone.
              {deleteError ? (
                <span className="mt-2 block text-destructive" role="alert">
                  {deleteError}
                </span>
              ) : null}
            </>
          ) : null
        }
        confirmLabel={deleting ? 'Deleting…' : 'Delete'}
        tone="destructive"
        pending={deleting}
        onConfirm={confirmDelete}
      />
    </>
  );
}
