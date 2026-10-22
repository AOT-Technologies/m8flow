import { useTranslation } from 'react-i18next';

import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pill } from '@/components/library/pill/Pill';
import { Card } from '@/components/ui/card';
import type { CeleryWorker } from '@/lib/celeryApi';
import { formatDuration, formatNumber } from '@/pages/nats/natsShared';

import { formatTimestamp } from './celeryShared';

/** Flower's Workers page: everyone answering now, then anyone seen in history who stopped. */
export function CeleryWorkersTab({ workers, onOpenWorker }: { workers: CeleryWorker[]; onOpenWorker: (name: string) => void }) {
  const { t } = useTranslation();

  const columns: DataTableColumn<CeleryWorker>[] = [
    {
      key: 'name',
      header: t('celery.workers.name'),
      width: 'minmax(220px,2fr)',
      render: (row) => (
        <button
          type="button"
          className="text-left font-medium break-all text-foreground underline-offset-2 hover:underline"
          onClick={() => onOpenWorker(row.name)}
        >
          {row.name}
        </button>
      ),
    },
    {
      key: 'status',
      header: t('celery.workers.status'),
      render: (row) => (
        <Pill size="lg" tone={row.online ? 'success' : 'error'}>
          {row.online ? t('celery.workers.online') : t('celery.workers.offline')}
        </Pill>
      ),
    },
    { key: 'pool', header: t('celery.workers.pool'), render: (row) => row.pool ?? '—' },
    {
      key: 'processes',
      header: t('celery.workers.processes'),
      render: (row) =>
        row.online ? <span className="font-mono">{`${formatNumber(row.processes)} / ${formatNumber(row.concurrency)}`}</span> : '—',
    },
    { key: 'running', header: t('celery.workers.running'), render: (row) => <span className="font-mono">{formatNumber(row.running)}</span> },
    { key: 'processed', header: t('celery.workers.processed'), render: (row) => <span className="font-mono">{formatNumber(row.tasksProcessed)}</span> },
    { key: 'queues', header: t('celery.workers.queues'), render: (row) => row.queues?.join(', ') || '—' },
    {
      key: 'uptime',
      header: t('celery.workers.uptimeOrLastSeen'),
      render: (row) => (row.online ? formatDuration(row.uptimeSeconds) : formatTimestamp(row.lastSeenAt)),
    },
  ];

  return (
    <Card variant="bordered">
      <DataTable
        columns={columns}
        rows={workers}
        minWidth="980px"
        getRowKey={(row) => row.name}
        emptyState={t('celery.workers.empty')}
      />
    </Card>
  );
}
