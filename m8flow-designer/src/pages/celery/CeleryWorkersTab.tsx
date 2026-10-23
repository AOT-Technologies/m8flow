import { useTranslation } from 'react-i18next';

import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pill } from '@/components/library/pill/Pill';
import { Card } from '@/components/ui/card';
import type { CeleryWorker } from '@/lib/celeryApi';
import { CardHeading, formatDuration, formatNumber } from '@/pages/nats/natsShared';

import { formatTimestamp } from './celeryShared';

type Counts = Pick<CeleryWorker, 'running' | 'tasksReceived' | 'tasksProcessed' | 'tasksSucceeded' | 'tasksFailed'>;
type Row = { kind: 'worker'; worker: CeleryWorker } | { kind: 'total'; counts: Counts };

const COUNT_KEYS = ['running', 'tasksReceived', 'tasksProcessed', 'tasksSucceeded', 'tasksFailed'] as const;

/** Flower's Total row: the online workers' numbers added up; unknown if any one is unknown. */
function totals(workers: CeleryWorker[]): Counts {
  const online = workers.filter((worker) => worker.online);
  return Object.fromEntries(
    COUNT_KEYS.map((key) => [
      key,
      online.some((worker) => worker[key] == null) ? null : online.reduce((sum, worker) => sum + (worker[key] ?? 0), 0),
    ]),
  ) as Counts;
}

/** Flower's Workers page: everyone answering now, then anyone seen in history who stopped, and a total. */
export function CeleryWorkersTab({ workers, onOpenWorker }: { workers: CeleryWorker[]; onOpenWorker: (name: string) => void }) {
  const { t } = useTranslation();
  const counts = (row: Row): Counts | null => (row.kind === 'total' ? row.counts : row.worker.online ? row.worker : null);
  const number = (key: (typeof COUNT_KEYS)[number]) => (row: Row) => (
    <span className={row.kind === 'total' ? 'font-mono font-semibold' : 'font-mono'}>{formatNumber(counts(row)?.[key])}</span>
  );

  const columns: DataTableColumn<Row>[] = [
    {
      key: 'name',
      header: t('celery.workers.name'),
      width: 'minmax(220px,2fr)',
      render: (row) =>
        row.kind === 'total' ? (
          <span className="font-semibold text-foreground">{t('celery.workers.total')}</span>
        ) : (
          <button
            type="button"
            className="text-left font-medium break-all text-foreground underline-offset-2 hover:underline"
            onClick={() => onOpenWorker(row.worker.name)}
          >
            {row.worker.name}
          </button>
        ),
    },
    {
      key: 'status',
      header: t('celery.workers.status'),
      render: (row) =>
        row.kind === 'worker' && (
          <Pill size="lg" tone={row.worker.online ? 'success' : 'error'}>
            {row.worker.online ? t('celery.workers.online') : t('celery.workers.offline')}
          </Pill>
        ),
    },
    { key: 'running', header: t('celery.workers.running'), render: number('running') },
    { key: 'received', header: t('celery.workers.received'), render: number('tasksReceived') },
    { key: 'processed', header: t('celery.workers.processed'), render: number('tasksProcessed') },
    { key: 'succeeded', header: t('celery.workers.succeeded'), render: number('tasksSucceeded') },
    {
      key: 'failed',
      header: t('celery.workers.failed'),
      render: (row) => {
        const failed = counts(row)?.tasksFailed;
        return <span className={failed ? 'font-mono text-destructive' : 'font-mono'}>{formatNumber(failed)}</span>;
      },
    },
    {
      key: 'load',
      header: t('celery.workers.loadAverage'),
      width: 'minmax(150px,1.2fr)',
      render: (row) =>
        row.kind === 'worker' && <span className="font-mono">{row.worker.loadAverage ? row.worker.loadAverage.join(', ') : '—'}</span>,
    },
    {
      key: 'uptime',
      header: t('celery.workers.uptimeOrLastSeen'),
      render: (row) =>
        row.kind === 'worker' && (row.worker.online ? formatDuration(row.worker.uptimeSeconds) : formatTimestamp(row.worker.lastSeenAt)),
    },
  ];

  const rows: Row[] = workers.length
    ? [...workers.map((worker) => ({ kind: 'worker' as const, worker })), { kind: 'total', counts: totals(workers) }]
    : [];

  return (
    <Card variant="bordered">
      <CardHeading title={t('celery.tabs.workers')} subtitle={t('celery.workers.countsHint')} />
      <DataTable
        columns={columns}
        rows={rows}
        minWidth="1040px"
        getRowKey={(row) => (row.kind === 'total' ? '__total' : row.worker.name)}
        emptyState={t('celery.workers.empty')}
      />
    </Card>
  );
}
