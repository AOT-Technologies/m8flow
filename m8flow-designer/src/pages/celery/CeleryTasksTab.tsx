import { useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pagination } from '@/components/library/pagination/Pagination';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { Card } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  CELERY_TASK_STATES,
  fetchCeleryHistory,
  type CeleryHistoryPage,
  type CeleryHistorySort,
  type CeleryHistoryTask,
  type CeleryTaskState,
} from '@/lib/celeryApi';

import { celeryErrorMessage, formatRuntime, formatTimestamp, STATE_LABEL, StateBadge } from './celeryShared';

const ALL = '__all__';
const PAGE_SIZES = [15, 25, 50, 100];

type Sort = { column: CeleryHistorySort; order: 'asc' | 'desc' };
// Newest event first, until a column header is clicked.
const DEFAULT_SORT: Sort = { column: 'updated', order: 'desc' };

export const WINDOW_OPTIONS: { value: string; labelKey: ParseKeys }[] = [
  { value: '1', labelKey: 'celery.history.window1h' },
  { value: '6', labelKey: 'celery.history.window6h' },
  { value: '24', labelKey: 'celery.history.window24h' },
  { value: '168', labelKey: 'celery.history.window7d' },
  { value: ALL, labelKey: 'celery.history.windowAll' },
];

export type HistoryFilters = {
  state: CeleryTaskState | null;
  name: string | null;
  worker: string | null;
  windowHours: number | null;
  search: string;
};

/** Flower's Tasks page, from the history the workers record: filter, search, page, open. */
export function CeleryTasksTab({
  historyEnabled,
  filters,
  onFiltersChange,
  taskNames,
  workerNames,
  refreshKey,
  onOpenTask,
}: {
  historyEnabled: boolean;
  filters: HistoryFilters;
  onFiltersChange: (next: HistoryFilters) => void;
  taskNames: string[];
  workerNames: string[];
  refreshKey: number;
  onOpenTask: (taskId: string) => void;
}) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<CeleryHistoryPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState(filters.search);
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [perPage, setPerPage] = useState(25);

  // Typing settles for a moment before it becomes a query.
  useEffect(() => {
    if (search === filters.search) return undefined;
    const timer = window.setTimeout(() => onFiltersChange({ ...filters, search }), 300);
    return () => window.clearTimeout(timer);
  }, [search, filters, onFiltersChange]);

  useEffect(() => setPage(1), [filters, sort, perPage]);

  useEffect(() => {
    if (!historyEnabled) return;
    let cancelled = false;
    fetchCeleryHistory({ ...filters, search: filters.search || null, page, perPage, sort: sort.column, order: sort.order })
      .then((next) => {
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(celeryErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [historyEnabled, filters, page, perPage, sort, refreshKey]);

  if (!historyEnabled) return <Alert tone="info">{t('celery.history.disabled')}</Alert>;

  // Flower's sortable columns: the first click sorts descending, the next ascending.
  const sortable = (column: CeleryHistorySort, label: string) => {
    const active = sort.column === column;
    const Icon = !active ? ArrowUpDown : sort.order === 'asc' ? ArrowUp : ArrowDown;
    return (
      <button
        type="button"
        className="inline-flex items-center gap-1 tracking-wide uppercase hover:text-foreground"
        aria-label={t(active && sort.order === 'desc' ? 'celery.history.sortAscending' : 'celery.history.sortDescending', { column: label })}
        onClick={() => setSort(active && sort.order === 'desc' ? { column, order: 'asc' } : { column, order: 'desc' })}
      >
        {label}
        <Icon className={active ? 'size-3 text-foreground' : 'size-3'} aria-hidden />
      </button>
    );
  };

  const columns: DataTableColumn<CeleryHistoryTask>[] = [
    { key: 'state', header: sortable('state', t('celery.history.state')), render: (row) => <StateBadge state={row.state} /> },
    {
      key: 'name',
      header: sortable('name', t('celery.history.name')),
      width: 'minmax(240px,2fr)',
      render: (row) => (
        <button type="button" className="text-left" onClick={() => onOpenTask(row.taskId)}>
          <div className="font-medium break-all text-foreground underline-offset-2 hover:underline">{row.name ?? '—'}</div>
          <div className="font-mono text-[12px] text-muted-foreground">{row.taskId}</div>
        </button>
      ),
    },
    { key: 'worker', header: sortable('worker', t('celery.history.worker')), render: (row) => <span className="break-all">{row.worker ?? '—'}</span> },
    { key: 'received', header: sortable('received', t('celery.history.received')), render: (row) => formatTimestamp(row.receivedAt ?? row.startedAt) },
    { key: 'runtime', header: sortable('runtime', t('celery.history.runtime')), render: (row) => <span className="font-mono">{formatRuntime(row.runtimeSeconds)}</span> },
    {
      key: 'arguments',
      header: t('celery.history.arguments'),
      width: 'minmax(220px,3fr)',
      render: (row) => (
        <code className="block font-mono text-[12px] break-all text-muted-foreground">
          {row.exception ?? ([row.args, row.kwargs].filter((part) => part && part !== '[]' && part !== '{}').join(' ') || '—')}
        </code>
      ),
    },
  ];

  const select = (label: string, value: string, options: { value: string; label: string }[], onChange: (value: string) => void) => (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={label} className="h-9 w-48 rounded-lg text-[13px]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <SearchBar value={search} onChange={setSearch} placeholder={t('celery.history.search')} className="w-72" />
        {select(
          t('celery.history.state'),
          filters.state ?? ALL,
          [{ value: ALL, label: t('celery.history.allStates') }, ...CELERY_TASK_STATES.map((state) => ({ value: state, label: t(STATE_LABEL[state]) }))],
          (value) => onFiltersChange({ ...filters, state: value === ALL ? null : (value as CeleryTaskState) }),
        )}
        {select(
          t('celery.history.name'),
          filters.name ?? ALL,
          [{ value: ALL, label: t('celery.history.allTypes') }, ...taskNames.map((name) => ({ value: name, label: name }))],
          (value) => onFiltersChange({ ...filters, name: value === ALL ? null : value }),
        )}
        {select(
          t('celery.history.worker'),
          filters.worker ?? ALL,
          [{ value: ALL, label: t('celery.history.allWorkers') }, ...workerNames.map((name) => ({ value: name, label: name }))],
          (value) => onFiltersChange({ ...filters, worker: value === ALL ? null : value }),
        )}
        {select(
          t('celery.history.window'),
          filters.windowHours == null ? ALL : String(filters.windowHours),
          WINDOW_OPTIONS.map((option) => ({ value: option.value, label: t(option.labelKey) })),
          (value) => onFiltersChange({ ...filters, windowHours: value === ALL ? null : Number(value) }),
        )}
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <Card variant="bordered">
        <DataTable
          columns={columns}
          rows={data?.results ?? []}
          minWidth="980px"
          getRowKey={(row) => row.taskId}
          emptyState={data ? t('celery.history.empty') : t('common.loading')}
        />
      </Card>
      {data && data.pagination.total > PAGE_SIZES[0] && (
        <Pagination
          page={page}
          onPageChange={setPage}
          totalItems={data.pagination.total}
          pageSize={perPage}
          pageSizeOptions={PAGE_SIZES}
          onPageSizeChange={setPerPage}
        />
      )}
    </div>
  );
}
