import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { fetchNatsTenants, type NatsTenantEventCounts } from '@/lib/natsApi';
import { formatRelativeTime } from '@/lib/relativeTime';

import { backlogTone, formatNumber, natsErrorMessage, type NatsEventSourceWorker } from './natsShared';

export function NatsTenantsTab({
  refreshKey,
  onViewEvents,
}: {
  refreshKey: number;
  onViewEvents: (tenantId: string, worker: NatsEventSourceWorker) => void;
}) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<NatsTenantEventCounts[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchNatsTenants()
      .then((next) => {
        if (!cancelled) {
          setRows(next);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(natsErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const columns: DataTableColumn<NatsTenantEventCounts>[] = [
    {
      key: 'tenant',
      header: t('nats.tenants.tenant'),
      width: 'minmax(160px,2fr)',
      render: (row) => <span className="font-medium text-foreground">{row.tenantSlug ?? row.tenantId}</span>,
    },
    {
      key: 'queued',
      header: t('nats.tenants.queued'),
      render: (row) => <Pill size="lg" dot={false} tone={backlogTone(row.queued)}>{formatNumber(row.queued)}</Pill>,
    },
    { key: 'started', header: t('nats.tenants.started'), render: (row) => <span className="font-mono">{formatNumber(row.instantiated)}</span> },
    {
      key: 'failed',
      header: t('nats.tenants.failed'),
      render: (row) => (
        <Pill size="lg" dot={false} tone={row.failed > 0 ? 'error' : 'muted'}>{formatNumber(row.failed)}</Pill>
      ),
    },
    { key: 'total', header: t('nats.tenants.total'), render: (row) => <span className="font-mono">{formatNumber(row.total)}</span> },
    {
      key: 'emailsSent',
      header: t('nats.tenants.emailsSent'),
      render: (row) => <span className="font-mono">{formatNumber(row.emailsSent)}</span>,
    },
    {
      key: 'emailFailures',
      header: t('nats.tenants.emailFailures'),
      render: (row) => (
        <Pill size="lg" dot={false} tone={row.emailFailures > 0 ? 'error' : 'muted'}>
          {formatNumber(row.emailFailures)}
        </Pill>
      ),
    },
    { key: 'activity', header: t('nats.tenants.lastActivity'), render: (row) => formatRelativeTime(row.lastActivityInSeconds || null) },
    {
      key: 'actions',
      header: '',
      width: 'minmax(190px,1fr)',
      className: 'text-right',
      render: (row) =>
        row.tenantId ? (
          <>
            <Button variant="link" size="sm" onClick={() => onViewEvents(row.tenantId as string, 'consumer')}>
              {t('nats.tenants.viewEvents')}
            </Button>
            <Button
              variant="link"
              size="sm"
              onClick={() => onViewEvents(row.tenantId as string, 'notification_worker')}
            >
              {t('nats.tenants.viewEmails')}
            </Button>
          </>
        ) : null,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-3xl text-sm text-muted-foreground">{t('nats.tenants.intro')}</p>
      {error && <Alert tone="error">{error}</Alert>}
      <Card variant="bordered">
        <DataTable
          columns={columns}
          rows={rows ?? []}
          minWidth="980px"
          getRowKey={(row) => row.tenantId ?? '(unattributed)'}
          emptyState={rows ? t('nats.tenants.empty') : t('common.loading')}
        />
      </Card>
    </div>
  );
}
