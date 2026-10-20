import { useEffect, useRef, type KeyboardEvent } from 'react';
import { Copy, ExternalLink, Link2 } from 'lucide-react';
import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';

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
  /** All-Tenants super-admin view: adds a Tenant column so rows from
   * different tenants are distinguishable. */
  showTenant?: boolean;
};

/** No mockup exists for a standalone Process Instances page (it appears
 * only as the "Recent instances" table inside a process model's detail in
 * Processes.dc.html). This table mirrors that column shape plus the app's
 * other tabular lists (ProcessesModelsList.tsx) — instance rows are
 * report-style data (status/timing columns), not browsable content. */
const STATUS_OPTIONS: { value: string; labelKey: ParseKeys }[] = [
  { value: '', labelKey: 'processInstances.status.all' },
  { value: 'running', labelKey: 'processInstances.status.running' },
  { value: 'waiting', labelKey: 'processInstances.status.waiting' },
  { value: 'user_input_required', labelKey: 'processInstances.status.userInputRequired' },
  { value: 'suspended', labelKey: 'processInstances.status.suspended' },
  { value: 'complete', labelKey: 'common.instanceStatus.complete' },
  { value: 'error', labelKey: 'common.instanceStatus.error' },
  { value: 'terminated', labelKey: 'processInstances.status.terminated' },
  { value: 'not_started', labelKey: 'processInstances.status.notStarted' },
];

// Values must match the backend allowlist (workflow.py `_INSTANCE_SORTS`).
// Labels are bare (no "Sort: " prefix baked in) — `SortDropdown` supplies
// that prefix itself via its `label` prop (component-adoption map, ticket
// 19); the union type on onSortChange keeps the values honest.
const SORT_OPTIONS: { value: ProcessInstanceSort; labelKey: ParseKeys }[] = [
  { value: 'newest', labelKey: 'processInstances.list.sort.newest' },
  { value: 'oldest', labelKey: 'processInstances.list.sort.oldest' },
  { value: 'recent_start', labelKey: 'processInstances.list.sort.recentStart' },
  { value: 'status', labelKey: 'common.status' },
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
  showTenant = false,
}: ProcessInstancesListProps) {
  const { t } = useTranslation();
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

  const resultCount = t('processInstances.list.resultCount', { count: totalCount });
  const isEmpty = !loading && !error && instances.length === 0;

  const statusOptions = STATUS_OPTIONS.map((option) => ({ value: option.value, label: t(option.labelKey) }));
  const sortOptions = SORT_OPTIONS.map((option) => ({ value: option.value, label: t(option.labelKey) }));
  const startedByOptions: SortDropdownOption[] = [
    { value: '', label: t('processInstances.status.all') },
    ...owners.map((owner) => ({ value: owner, label: owner })),
  ];

  const columns: DataTableColumn<ProcessInstanceListItem>[] = [
    ...(showTenant
      ? [
          {
            key: 'tenant',
            header: t('processInstances.list.columns.tenant'),
            width: '140px',
            className: 'truncate text-[13px] text-muted-foreground',
            render: (instance: ProcessInstanceListItem) =>
              instance.tenant_name || instance.tenant_id || '—',
          } as DataTableColumn<ProcessInstanceListItem>,
        ]
      : []),
    {
      key: 'id',
      header: t('processInstances.fields.id'),
      width: '64px',
      // Link-colored to signal the row is openable (Processes.dc.html
      // styles the instance id in link color); the whole row already
      // navigates via onRowClick, so this stays plain text.
      className: 'font-mono text-[13px] font-medium text-info',
      render: (instance) => instance.id,
    },
    {
      key: 'model',
      header: t('processInstances.list.columns.processModel'),
      width: 'minmax(200px,2fr)',
      className: 'min-w-0 truncate text-[14px] font-medium text-foreground',
      render: (instance) => instance.process_model_display_name,
    },
    {
      key: 'status',
      header: t('common.status'),
      width: '130px',
      render: (instance) => <Pill {...processInstanceStatusToPillProps(instance.status)} />,
    },
    {
      key: 'started',
      header: t('processInstances.fields.started'),
      width: '120px',
      className: 'text-[13px] text-muted-foreground',
      render: (instance) => formatRelativeTime(instance.started_at),
    },
    {
      key: 'startedBy',
      header: t('processInstances.fields.startedBy'),
      width: '130px',
      className: 'truncate text-[13px] text-muted-foreground',
      render: (instance) => instance.started_by || '—',
    },
    {
      key: 'duration',
      header: t('processInstances.list.columns.duration'),
      width: '100px',
      className: 'text-right font-mono text-[13px] text-muted-foreground',
      render: (instance) =>
        instance.started_at != null && instance.ended_at != null
          ? formatDuration(Math.max(0, (Date.parse(instance.ended_at) - Date.parse(instance.started_at)) / 1000))
          : '—',
    },
    {
      key: 'actions',
      header: <span className="sr-only">{t('common.actions')}</span>,
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
          <h1 className="font-display text-[32px] font-semibold tracking-tight text-foreground">{t('processInstances.title')}</h1>
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
            placeholder={t('processInstances.list.searchPlaceholder')}
            aria-label={t('processInstances.list.searchLabel')}
            className="max-w-[420px] min-w-0 flex-1"
          />

          <SortDropdown
            label={t('common.status')}
            options={statusOptions}
            value={status}
            onChange={onStatusChange}
            className="min-w-0"
          />

          <SortDropdown
            label={t('processInstances.fields.startedBy')}
            options={startedByOptions}
            value={startedBy}
            onChange={onStartedByChange}
            className="min-w-0"
          />

          <SortDropdown
            options={sortOptions}
            value={sort}
            onChange={(value) => onSortChange(value as ProcessInstanceSort)}
            className="min-w-0"
          />

          <div className="ml-auto whitespace-nowrap text-[13px] text-muted-foreground">
            {loading ? t('common.loading') : resultCount}
          </div>
        </div>

        {error ? (
          <Alert tone="error" className="mb-4">
            {error}
          </Alert>
        ) : null}

        <Card variant="bordered" className="overflow-x-auto">
          {loading ? (
            <div className="px-[22px] py-8 text-sm text-muted-foreground">{t('processInstances.list.loading')}</div>
          ) : isEmpty ? (
            <div className="px-6 py-[52px] text-center">
              <div className="text-[15.5px] font-semibold text-foreground">{t('processInstances.list.emptyTitle')}</div>
              <p className="mt-2 text-[13.5px] text-muted-foreground">
                {search.trim() || status || startedBy
                  ? t('processInstances.list.emptyFiltered')
                  : t('processInstances.list.emptyNoRuns')}
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
  const { t } = useTranslation();

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
      triggerLabel={t('processInstances.list.rowActions.label')}
      items={[
        { label: t('processInstances.list.rowActions.open'), icon: <ExternalLink className="size-3.5" />, onSelect: onOpen },
        {
          label: t('processInstances.list.rowActions.copyId'),
          icon: <Copy className="size-3.5" />,
          onSelect: () => copy(String(instance.id)),
        },
        {
          label: t('processInstances.copyLink'),
          icon: <Link2 className="size-3.5" />,
          onSelect: () => copy(instanceUrl),
        },
      ]}
    />
  );
}
