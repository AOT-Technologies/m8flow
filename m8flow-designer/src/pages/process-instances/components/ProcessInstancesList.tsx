import { useEffect, useRef, type KeyboardEvent } from 'react';
import { Copy, ExternalLink, Link2 } from 'lucide-react';

import type { ProcessInstanceListItem, ProcessInstanceSort } from '@/lib/processInstancesApi';
import { ActionMenu } from '@/components/library/action-menu/ActionMenu';
import { Alert } from '@/components/library/alert/Alert';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pagination } from '@/components/library/pagination/Pagination';
import { Pill } from '@/components/library/pill/Pill';
import { processInstanceStatusToPillProps } from '@/components/library/pill/processInstanceStatusToPillProps';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { SortDropdown, type SortDropdownOption } from '@/components/library/sort-dropdown/SortDropdown';
import { Card } from '@/components/ui/card';
import { formatDuration } from '@/pages/process-model-detail/components/ProcessModelOverview';
import { formatRelativeTime } from '@/lib/relativeTime';

export type ProcessInstancesListProps = {
  instances: ProcessInstanceListItem[];
  loading?: boolean;
  error?: string | null;
  search: string;
  onSearchChange: (value: string) => void;
  status: string;
  onStatusChange: (value: string) => void;
  owners: string[];
  startedBy: string;
  onStartedByChange: (value: string) => void;
  sort: ProcessInstanceSort;
  onSortChange: (value: ProcessInstanceSort) => void;
  page: number;
  perPage: number;
  onPerPageChange: (value: number) => void;
  totalCount: number;
  onPageChange: (page: number) => void;
  onOpenInstance?: (instance: ProcessInstanceListItem) => void;
};

/** No mockup exists for a standalone Process Instances page (it appears
 * only as the "Recent instances" table inside a process model's detail in
 * Processes.dc.html). This table mirrors that column shape plus the app's
 * other tabular lists (ProcessesModelsList.tsx) — instance rows are
 * report-style data (status/timing columns), not browsable content. */
const STATUS_OPTIONS = [
  { value: '', label: 'Any status' },
  { value: 'running', label: 'Running' },
  { value: 'waiting', label: 'Waiting' },
  { value: 'user_input_required', label: 'User Input Required' },
  { value: 'suspended', label: 'Suspended' },
  { value: 'complete', label: 'Complete' },
  { value: 'error', label: 'Error' },
  { value: 'terminated', label: 'Terminated' },
  { value: 'not_started', label: 'Not Started' },
];

// Values must match the backend allowlist (workflow.py `_INSTANCE_SORTS`).
// Labels are bare (no "Sort: " prefix baked in) — `SortDropdown` supplies
// that prefix itself via its `label` prop (component-adoption map, ticket
// 19); the union type on onSortChange keeps the values honest.
const SORT_OPTIONS: { value: ProcessInstanceSort; label: string }[] = [
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'recent_start', label: 'Recent start' },
  { value: 'status', label: 'Status' },
];

const PER_PAGE_OPTIONS = [25, 50, 100];

export function ProcessInstancesList({
  instances,
  loading = false,
  error = null,
  search,
  onSearchChange,
  status,
  onStatusChange,
  owners,
  startedBy,
  onStartedByChange,
  sort,
  onSortChange,
  page,
  perPage,
  onPerPageChange,
  totalCount,
  onPageChange,
  onOpenInstance,
}: ProcessInstancesListProps) {
  const searchRef = useRef<HTMLInputElement>(null);

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

  function onSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      onSearchChange('');
      searchRef.current?.blur();
    }
  }

  const resultCount = `${totalCount} instance${totalCount === 1 ? '' : 's'}`;
  const isEmpty = !loading && !error && instances.length === 0;

  const startedByOptions: SortDropdownOption[] = [
    { value: '', label: 'All owners' },
    ...owners.map((owner) => ({ value: owner, label: owner })),
  ];

  const columns: DataTableColumn<ProcessInstanceListItem>[] = [
    {
      key: 'id',
      header: 'ID',
      width: '64px',
      // Link-colored to signal the row is openable (Processes.dc.html
      // styles the instance id in link color); the whole row already
      // navigates via onRowClick, so this stays plain text.
      className: 'font-mono text-[13px] font-medium text-info',
      render: (instance) => instance.id,
    },
    {
      key: 'model',
      header: 'Process model',
      width: 'minmax(200px,2fr)',
      className: 'min-w-0 truncate text-[14px] font-medium text-foreground',
      render: (instance) => instance.process_model_display_name,
    },
    {
      key: 'status',
      header: 'Status',
      width: '130px',
      render: (instance) => <Pill {...processInstanceStatusToPillProps(instance.status)} />,
    },
    {
      key: 'started',
      header: 'Started',
      width: '120px',
      className: 'text-[13px] text-muted-foreground',
      render: (instance) => formatRelativeTime(instance.start_in_seconds),
    },
    {
      key: 'startedBy',
      header: 'Started by',
      width: '130px',
      className: 'truncate text-[13px] text-muted-foreground',
      render: (instance) => instance.started_by || '—',
    },
    {
      key: 'duration',
      header: 'Duration',
      width: '100px',
      className: 'text-right font-mono text-[13px] text-muted-foreground',
      render: (instance) =>
        instance.start_in_seconds != null && instance.end_in_seconds != null
          ? formatDuration(instance.end_in_seconds - instance.start_in_seconds)
          : '—',
    },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      width: '44px',
      render: (instance) => (
        <div
          className="flex items-center justify-end"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <RowActionsMenu instance={instance} onOpen={() => onOpenInstance?.(instance)} />
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[32px] font-semibold tracking-tight text-foreground">Process Instances</h1>
        </div>
      </div>

      <div className="pb-14">
        <div className="mb-[18px] flex flex-wrap items-center gap-2.5">
          <SearchBar
            ref={searchRef}
            type="search"
            value={search}
            onChange={onSearchChange}
            onKeyDown={onSearchKeyDown}
            placeholder="Search by process model"
            aria-label="Search process instances"
            className="max-w-[420px] min-w-0 flex-1"
          />

          <SortDropdown
            label="Status"
            options={STATUS_OPTIONS}
            value={status}
            onChange={onStatusChange}
            className="min-w-0"
          />

          <SortDropdown
            label="Started by"
            options={startedByOptions}
            value={startedBy}
            onChange={onStartedByChange}
            className="min-w-0"
          />

          <SortDropdown
            options={SORT_OPTIONS}
            value={sort}
            onChange={(value) => onSortChange(value as ProcessInstanceSort)}
            className="min-w-0"
          />

          <div className="ml-auto whitespace-nowrap text-[13px] text-muted-foreground">
            {loading ? 'Loading…' : resultCount}
          </div>
        </div>

        {error ? (
          <Alert tone="error" className="mb-4">
            {error}
          </Alert>
        ) : null}

        <Card variant="bordered" className="overflow-x-auto">
          {loading ? (
            <div className="px-[22px] py-8 text-sm text-muted-foreground">Loading process instances…</div>
          ) : isEmpty ? (
            <div className="px-6 py-[52px] text-center">
              <div className="text-[15.5px] font-semibold text-foreground">No process instances</div>
              <p className="mt-2 text-[13.5px] text-muted-foreground">
                {search.trim() || status || startedBy
                  ? 'Try a different search or clear the filters.'
                  : 'No process instances have run for this tenant yet.'}
              </p>
            </div>
          ) : (
            <DataTable
              columns={columns}
              rows={instances}
              getRowKey={(instance) => instance.id}
              onRowClick={(instance) => onOpenInstance?.(instance)}
              minWidth="804px"
            />
          )}

          {!loading && !isEmpty ? (
            <div className="px-[22px] py-3.5">
              <Pagination
                page={page}
                onPageChange={onPageChange}
                totalItems={totalCount}
                pageSize={perPage}
                pageSizeOptions={PER_PAGE_OPTIONS}
                onPageSizeChange={onPerPageChange}
              />
            </div>
          ) : null}
        </Card>
      </div>
    </>
  );
}

/** Read-only per-row overflow menu (Processes.dc.html row kebab). Lifecycle
 * actions (suspend/resume/terminate/retry) are deliberately out of scope —
 * they'd require workflow-write endpoints that don't exist yet — so this
 * offers only safe, local actions. */
function RowActionsMenu({
  instance,
  onOpen,
}: {
  instance: ProcessInstanceListItem;
  onOpen: () => void;
}) {
  async function copy(text: string) {
    try {
      await navigator.clipboard?.writeText(text);
    } catch {
      // Clipboard can reject (permissions/insecure context) — a copy action
      // silently failing is acceptable; nothing else depends on it.
    }
  }

  const instanceUrl =
    typeof window !== 'undefined'
      ? `${window.location.origin}/process-instances/${instance.id}`
      : `/process-instances/${instance.id}`;

  return (
    <ActionMenu
      triggerLabel="Instance actions"
      items={[
        { label: 'Open', icon: <ExternalLink className="size-3.5" />, onSelect: onOpen },
        {
          label: 'Copy instance ID',
          icon: <Copy className="size-3.5" />,
          onSelect: () => copy(String(instance.id)),
        },
        {
          label: 'Copy link',
          icon: <Link2 className="size-3.5" />,
          onSelect: () => copy(instanceUrl),
        },
      ]}
    />
  );
}

