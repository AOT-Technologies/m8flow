import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from 'react';
import { ExternalLink, Folder, Plus, Trash2 } from 'lucide-react';

import { ApiError, type ProcessModelListItem } from '@/lib/api';
import { ActionMenu } from '@/components/library/action-menu/ActionMenu';
import { Chip } from '@/components/library/chip/Chip';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { EmptyState } from '@/components/library/empty-state/EmptyState';
import { Pill } from '@/components/library/pill/Pill';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { SortDropdown } from '@/components/library/sort-dropdown/SortDropdown';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { formatRelativeTime } from '@/lib/relativeTime';
import { cn } from '@/lib/utils';

const SORT_OPTIONS = [
  { value: 'desc', label: 'Newest first' },
  { value: 'asc', label: 'Oldest first' },
];

export type ProcessesModelsListProps = {
  models: ProcessModelListItem[];
  loading?: boolean;
  error?: string | null;
  /** Active group filter id from `?group=`; null = all groups. */
  groupFilter?: string | null;
  /** Label for the scope pill (group display name or id). */
  scopeLabel?: string;
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
  totalUnfilteredCount,
  onBrowseGroups,
  onClearGroupFilter,
  onOpenModel,
  onFilterByGroup,
  onStartModel,
  onDeleteModel,
  onCreateModel,
}: ProcessesModelsListProps) {
  const [search, setSearch] = useState('');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
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

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = models;
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
  }, [models, search, sortDir]);

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
      // Always "—" — process models have no status field yet (map fog);
      // this is a placeholder pill, not a real status vocabulary.
      render: () => <Pill tone="muted">—</Pill>,
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
              than get a button that 403s. */}
          {onStartModel ? (
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
          {/* "Browse groups" removed — the "Showing [scope] ▾" pill below opens
              the same group picker, so a second entry point was redundant. */}
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

          <Chip disabled>Any status</Chip>
          <Chip disabled>All owners</Chip>

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

