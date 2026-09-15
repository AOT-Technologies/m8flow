import { useEffect, useState } from 'react';

import {
  fetchProcessInstanceMilestones,
  type ProcessInstanceMilestoneRow,
} from '@/lib/processInstancesApi';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Card } from '@/components/ui/card';

export type ProcessInstanceMilestonesTableProps = {
  instanceId: number;
  tenantId?: string | null;
  /** When set, skip the network fetch (page-shell prototype / tests). */
  milestones?: ProcessInstanceMilestoneRow[] | null;
};

function cell(value: string | null | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : '—';
}

function formatMilestoneTimestamp(epochSeconds: number | null | undefined): string {
  if (epochSeconds == null) {
    return '—';
  }
  const d = new Date(epochSeconds * 1000);
  if (Number.isNaN(d.getTime())) {
    return '—';
  }
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

/**
 * Milestones tab body: zero or one current last milestone — not a history.
 * GET /v1.0/m8flow/process-instances/{id}/milestones. Timestamp is plain text.
 */
export function ProcessInstanceMilestonesTable({
  instanceId,
  tenantId = null,
  milestones: milestonesOverride,
}: ProcessInstanceMilestonesTableProps) {
  const [milestones, setMilestones] = useState<ProcessInstanceMilestoneRow[]>(
    milestonesOverride ?? [],
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(milestonesOverride === undefined);

  useEffect(() => {
    if (milestonesOverride !== undefined) {
      setMilestones(milestonesOverride ?? []);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchProcessInstanceMilestones(instanceId, tenantId)
      .then((payload) => {
        if (!cancelled) setMilestones(payload);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load milestones');
          setMilestones([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [instanceId, tenantId, milestonesOverride]);

  const columns: DataTableColumn<ProcessInstanceMilestoneRow>[] = [
    {
      key: 'milestone',
      header: 'Milestone',
      width: 'minmax(120px,1.4fr)',
      className: 'text-[14px] font-semibold text-foreground',
      render: (row) => row.milestone,
    },
    {
      key: 'bpmn_process',
      header: 'Bpmn process',
      width: 'minmax(200px,2.6fr)',
      className: 'min-w-0 break-all font-mono text-[12.5px] text-muted-foreground',
      render: (row) => cell(row.bpmn_process),
    },
    {
      key: 'timestamp',
      header: 'Timestamp',
      width: 'minmax(0,180px)',
      render: (row) => (
        <time
          className="font-mono text-[12.5px] text-foreground"
          dateTime={row.timestamp != null ? new Date(row.timestamp * 1000).toISOString() : undefined}
        >
          {formatMilestoneTimestamp(row.timestamp)}
        </time>
      ),
    },
  ];

  return (
    <Card variant="bordered" className="overflow-x-auto">
      {error ? (
        <p className="px-[22px] py-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="px-[22px] py-8 text-sm text-muted-foreground" aria-busy="true">
          Loading milestones…
        </p>
      ) : (
        <DataTable
          columns={columns}
          rows={milestones}
          getRowKey={(row) => row.milestone}
          emptyState=""
          minWidth="700px"
        />
      )}
    </Card>
  );
}
