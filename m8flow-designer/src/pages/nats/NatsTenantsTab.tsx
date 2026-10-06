import { useEffect, useState } from 'react';

import { Alert } from '@/components/library/alert/Alert';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { fetchNatsTenants, type NatsTenantEventCounts } from '@/lib/natsApi';
import { formatRelativeTime } from '@/lib/relativeTime';

import { backlogTone, formatNumber, natsErrorMessage } from './natsShared';

export function NatsTenantsTab({
  refreshKey,
  onViewEvents,
}: {
  refreshKey: number;
  onViewEvents: (tenantId: string) => void;
}) {
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
      header: 'Tenant',
      width: 'minmax(160px,2fr)',
      render: (row) => <span className="font-medium text-foreground">{row.tenantSlug ?? row.tenantId}</span>,
    },
    {
      key: 'queued',
      header: 'Queued',
      render: (row) => <Pill size="lg" dot={false} tone={backlogTone(row.queued)}>{formatNumber(row.queued)}</Pill>,
    },
    { key: 'started', header: 'Started', render: (row) => <span className="font-mono">{formatNumber(row.instantiated)}</span> },
    {
      key: 'failed',
      header: 'Failed',
      render: (row) => (
        <Pill size="lg" dot={false} tone={row.failed > 0 ? 'error' : 'muted'}>{formatNumber(row.failed)}</Pill>
      ),
    },
    { key: 'total', header: 'Total', render: (row) => <span className="font-mono">{formatNumber(row.total)}</span> },
    { key: 'activity', header: 'Last activity', render: (row) => formatRelativeTime(row.lastActivityInSeconds || null) },
    {
      key: 'actions',
      header: '',
      width: 'minmax(110px,1fr)',
      className: 'text-right',
      render: (row) =>
        row.tenantId ? (
          <Button variant="link" size="sm" onClick={() => onViewEvents(row.tenantId as string)}>
            View events
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-3xl text-sm text-muted-foreground">
        Per-tenant backlog comes from the event audit trail: JetStream reports pending messages per consumer, and one
        consumer serves every tenant, so the broker cannot break it down this way.
      </p>
      {error && <Alert tone="error">{error}</Alert>}
      <Card variant="bordered">
        <DataTable
          columns={columns}
          rows={rows ?? []}
          minWidth="760px"
          getRowKey={(row) => row.tenantId ?? '(unattributed)'}
          emptyState={rows ? 'No NATS events recorded yet.' : 'Loading…'}
        />
      </Card>
    </div>
  );
}
