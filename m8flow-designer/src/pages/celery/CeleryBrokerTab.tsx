import { useTranslation } from 'react-i18next';

import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Card } from '@/components/ui/card';
import type { CeleryOverview, CeleryQueue } from '@/lib/celeryApi';
import { CardHeading, formatNumber } from '@/pages/nats/natsShared';

import { Stat } from './CeleryDashboardTab';

/** Flower's Broker page: what is waiting in each queue and who consumes it. */
export function CeleryBrokerTab({ overview }: { overview: CeleryOverview }) {
  const { t } = useTranslation();

  const columns: DataTableColumn<CeleryQueue>[] = [
    { key: 'name', header: t('celery.broker.queue'), render: (row) => <span className="font-medium text-foreground">{row.name}</span> },
    { key: 'messages', header: t('celery.broker.messages'), render: (row) => <span className="font-mono">{formatNumber(row.messages)}</span> },
    {
      key: 'consumers',
      header: t('celery.broker.consumers'),
      width: 'minmax(240px,2fr)',
      render: (row) => (row.consumers.length ? row.consumers.join(', ') : <span className="text-destructive">{t('celery.broker.noConsumers')}</span>),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <Card variant="bordered" className="grid grid-cols-2 gap-6 p-5 md:grid-cols-3">
        <Stat label={t('celery.broker.transport')} value={overview.transport ?? '—'} />
        <Stat label={t('celery.broker.queues')} value={formatNumber(overview.queues.length)} />
        <Stat label={t('celery.broker.unacked')} title={t('celery.broker.unackedHint')} value={formatNumber(overview.unacked)} />
      </Card>
      <Card variant="bordered">
        <CardHeading title={t('celery.broker.title')} subtitle={t('celery.broker.subtitle')} />
        <DataTable columns={columns} rows={overview.queues} getRowKey={(row) => row.name} emptyState={t('common.noData')} />
      </Card>
    </div>
  );
}
