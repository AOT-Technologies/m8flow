import { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { Link } from 'react-router-dom';

import {
  fetchProcessInstanceEvents,
  type ProcessInstanceEventFilterOptions,
  type ProcessInstanceEventRow,
} from '@/lib/processInstancesApi';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Modal } from '@/components/library/modal/Modal';
import { Pagination } from '@/components/library/pagination/Pagination';
import { Pill } from '@/components/library/pill/Pill';
import { SortDropdown } from '@/components/library/sort-dropdown/SortDropdown';
import { Card } from '@/components/ui/card';

export type ProcessInstanceEventsTableProps = {
  instanceId: number;
  tenantId?: string | null;
  /** When set, skip the network fetch (page-shell prototype / tests). */
  events?: ProcessInstanceEventRow[] | null;
};

const PER_PAGE_OPTIONS = [25, 50, 100];
const DEFAULT_PER_PAGE = 50;
const FAILED_EVENT_TYPES = new Set(['task_failed', 'process_instance_error']);
/** Events whose task finished at that moment — the backend accepts only
 * COMPLETED / ERROR tasks for `to_task_guid`. */
const TIME_TRAVEL_EVENT_TYPES = new Set(['task_completed', 'task_failed']);
const NO_OPTIONS: ProcessInstanceEventFilterOptions = { event_types: [], task_types: [] };

function cell(value: string | null | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : '—';
}

/** UTC `YYYY-MM-DD HH:MM:SS` matching the mockup clock. */
function formatEventTimestamp(timestamp: string | null | undefined): string {
  if (timestamp == null) {
    return '—';
  }
  const d = new Date(timestamp);
  if (Number.isNaN(d.getTime())) {
    return '—';
  }
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

function options(values: string[], anyLabel: string) {
  return [{ value: '', label: anyLabel }, ...values.map((value) => ({ value, label: value }))];
}

/**
 * Events tab body for process instance detail. Fetches
 * GET /v1.0/m8flow/process-instances/{id}/events (paged, filterable).
 * Task-completion/failure timestamps link to `?to_task_guid=` (the page
 * re-renders the diagram as of that task); failed events open their
 * recorded error.
 */
export function ProcessInstanceEventsTable({
  instanceId,
  tenantId = null,
  events: eventsOverride,
}: ProcessInstanceEventsTableProps) {
  const [events, setEvents] = useState<ProcessInstanceEventRow[]>(eventsOverride ?? []);
  const [total, setTotal] = useState(eventsOverride?.length ?? 0);
  const [filterOptions, setFilterOptions] = useState<ProcessInstanceEventFilterOptions>(NO_OPTIONS);
  const [eventType, setEventType] = useState('');
  const [taskType, setTaskType] = useState('');
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(DEFAULT_PER_PAGE);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(eventsOverride === undefined);
  const [errorEvent, setErrorEvent] = useState<ProcessInstanceEventRow | null>(null);

  useEffect(() => {
    if (eventsOverride !== undefined) {
      setEvents(eventsOverride ?? []);
      setTotal(eventsOverride?.length ?? 0);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchProcessInstanceEvents(instanceId, tenantId, { eventType, taskType, page, perPage })
      .then((payload) => {
        if (cancelled) return;
        setEvents(payload.results);
        setTotal(payload.pagination.total);
        setFilterOptions(payload.filter_options);
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
  }, [instanceId, tenantId, eventsOverride, eventType, taskType, page, perPage]);

  const columns: DataTableColumn<ProcessInstanceEventRow>[] = [
    {
      key: 'id',
      header: 'ID',
      width: 'minmax(50px,60px)',
      className: 'font-mono text-[13px] font-medium text-info',
      render: (event) => event.id ?? '—',
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
      className: 'break-words text-[13px] text-muted-foreground',
      render: (event) => cell(event.task_identifier),
    },
    {
      key: 'task_type',
      header: 'Task type',
      width: 'minmax(0,130px)',
      className: 'break-words text-[13px] text-muted-foreground',
      render: (event) => cell(event.task_type),
    },
    {
      key: 'event_type',
      header: 'Event type',
      width: 'minmax(0,140px)',
      render: (event) => {
        const failed = FAILED_EVENT_TYPES.has(event.event_type);
        const pill = (
          <Pill
            tone={failed ? 'error' : 'success'}
            dot={false}
            className="min-w-0 max-w-full whitespace-normal text-left leading-tight"
          >
            <span className="min-w-0 break-all">{event.event_type}</span>
          </Pill>
        );
        if (!failed) return pill;
        return (
          <button
            type="button"
            title="Event has an error"
            className="inline-flex min-w-0 max-w-full items-center gap-1"
            onClick={() => setErrorEvent(event)}
          >
            <AlertCircle aria-hidden="true" className="size-3.5 shrink-0 text-destructive" />
            {pill}
          </button>
        );
      },
    },
    {
      key: 'user',
      header: 'User',
      width: 'minmax(0,90px)',
      className: 'text-[13px] text-muted-foreground italic',
      render: (event) => event.user,
    },
    {
      key: 'occurred_at',
      header: 'Timestamp',
      width: 'minmax(0,150px)',
      render: (event) => {
        const stamp = (
          <time
            className="font-mono text-[12.5px] text-foreground"
            dateTime={event.occurred_at != null ? new Date(event.occurred_at).toISOString() : undefined}
          >
            {formatEventTimestamp(event.occurred_at)}
          </time>
        );
        if (!event.task_guid || !TIME_TRAVEL_EVENT_TYPES.has(event.event_type)) return stamp;
        return (
          <Link
            to={{ search: `?to_task_guid=${encodeURIComponent(event.task_guid)}` }}
            title="View state when task was completed"
            className="hover:underline [&>time]:text-info"
          >
            {stamp}
          </Link>
        );
      },
    },
  ];

  return (
    <>
      {eventsOverride === undefined ? (
        <div className="mb-[18px] flex flex-wrap items-center gap-2.5">
          <SortDropdown
            label="Event type"
            options={options(filterOptions.event_types, 'Any event type')}
            value={eventType}
            onChange={(value) => {
              setEventType(value);
              setPage(1);
            }}
            className="min-w-0"
          />
          <SortDropdown
            label="Task type"
            options={options(filterOptions.task_types, 'Any task type')}
            value={taskType}
            onChange={(value) => {
              setTaskType(value);
              setPage(1);
            }}
            className="min-w-0"
          />
        </div>
      ) : null}

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
            getRowKey={(event) => event.id ?? `task-${event.task_guid}-${event.event_type}`}
            emptyState=""
            minWidth="1080px"
          />
        )}

        {!loading && total > 0 && eventsOverride === undefined ? (
          <div className="px-[22px] py-3.5">
            <Pagination
              page={page}
              onPageChange={setPage}
              totalItems={total}
              pageSize={perPage}
              pageSizeOptions={PER_PAGE_OPTIONS}
              onPageSizeChange={(size) => {
                setPerPage(size);
                setPage(1);
              }}
            />
          </div>
        ) : null}
      </Card>

      <Modal
        open={errorEvent !== null}
        onOpenChange={(open) => {
          if (!open) setErrorEvent(null);
        }}
        title="Event error details"
      >
        {errorEvent ? (
          <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 text-[13.5px]">
            <dt className="text-muted-foreground">Event type</dt>
            <dd>{errorEvent.event_type}</dd>
            <dt className="text-muted-foreground">Task name</dt>
            <dd>{cell(errorEvent.task_name)}</dd>
            <dt className="text-muted-foreground">Task ID</dt>
            <dd className="font-mono text-[12.5px]">{cell(errorEvent.task_identifier)}</dd>
            <dt className="text-muted-foreground">Task type</dt>
            <dd>{cell(errorEvent.task_type)}</dd>
            <dt className="text-muted-foreground">Timestamp</dt>
            <dd className="font-mono text-[12.5px]">{formatEventTimestamp(errorEvent.occurred_at)}</dd>
            <dt className="text-muted-foreground">Message</dt>
            <dd className="whitespace-pre-wrap break-words">
              {errorEvent.error_message ?? 'No error message was recorded for this event.'}
            </dd>
          </dl>
        ) : null}
      </Modal>
    </>
  );
}
