import { useEffect, useState } from 'react';

import {
  fetchProcessInstanceEvents,
  type ProcessInstanceEventRow,
} from '@/lib/processInstancesApi';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pill } from '@/components/library/pill/Pill';
import { Card } from '@/components/ui/card';

export type ProcessInstanceEventsTableProps = {
  instanceId: number;
  tenantId?: string | null;
  /** When set, skip the network fetch (page-shell prototype / tests). */
  events?: ProcessInstanceEventRow[] | null;
};

function cell(value: string | null | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : '—';
}

/** UTC `YYYY-MM-DD HH:MM:SS` matching the mockup clock; not a link (target is fog). */
function formatEventTimestamp(epochSeconds: number | null | undefined): string {
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
 * Events tab body for process instance detail. Fetches
 * GET /v1.0/m8flow/process-instances/{id}/events. Timestamp is plain text —
 * mockup anchors stay map fog. Empty copy stays fog (headers only).
 */
export function ProcessInstanceEventsTable({
  instanceId,
  tenantId = null,
  events: eventsOverride,
}: ProcessInstanceEventsTableProps) {
  const [events, setEvents] = useState<ProcessInstanceEventRow[]>(eventsOverride ?? []);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(eventsOverride === undefined);

  useEffect(() => {
    if (eventsOverride !== undefined) {
      setEvents(eventsOverride ?? []);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchProcessInstanceEvents(instanceId, tenantId)
      .then((payload) => {
        if (!cancelled) setEvents(payload);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load events');
          setEvents([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [instanceId, tenantId, eventsOverride]);

  const columns: DataTableColumn<ProcessInstanceEventRow>[] = [
    {
      key: 'id',
      header: 'ID',
      width: 'minmax(50px,60px)',
      className: 'font-mono text-[13px] font-medium text-info',
      render: (event) => event.id,
    },
    {
      key: 'bpmn_process',
      header: 'Bpmn process',
      width: 'minmax(200px,2.2fr)',
      className: 'min-w-0 break-all font-mono text-[12px] text-muted-foreground',
      render: (event) => cell(event.bpmn_process),
    },
    {
      key: 'task_name',
      header: 'Task name',
      width: 'minmax(0,120px)',
      className: 'text-[13px]',
      render: (event) => cell(event.task_name),
    },
    {
      key: 'task_identifier',
      header: 'Task identifier',
      width: 'minmax(0,130px)',
      className: 'text-[13px] text-muted-foreground',
      render: (event) => cell(event.task_identifier),
    },
    {
      key: 'task_type',
      header: 'Task type',
      width: 'minmax(0,130px)',
      className: 'text-[13px] text-muted-foreground',
      render: (event) => cell(event.task_type),
    },
    {
      key: 'event_type',
      header: 'Event type',
      width: 'minmax(0,140px)',
      render: (event) => (
        <Pill tone="success" dot={false}>
          {event.event_type}
        </Pill>
      ),
    },
    {
      key: 'user',
      header: 'User',
      width: 'minmax(0,90px)',
      className: 'text-[13px] text-muted-foreground italic',
      render: (event) => event.user,
    },
    {
      key: 'timestamp',
      header: 'Timestamp',
      width: 'minmax(0,150px)',
      render: (event) => (
        <time
          className="font-mono text-[12.5px] text-foreground"
          dateTime={event.timestamp != null ? new Date(event.timestamp * 1000).toISOString() : undefined}
        >
          {formatEventTimestamp(event.timestamp)}
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
          Loading events…
        </p>
      ) : (
        <DataTable
          columns={columns}
          rows={events}
          getRowKey={(event) => event.id}
          emptyState=""
          minWidth="1080px"
        />
      )}
    </Card>
  );
}
