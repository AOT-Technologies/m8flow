import { useEffect, useState } from 'react';

import {
  fetchProcessInstanceCompletedTasks,
  type ProcessInstanceCompletedTaskRow,
  type ProcessInstanceCompletedTasksResponse,
} from '@/lib/processInstancesApi';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Card } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

export type ProcessInstanceCompletedTasksTableProps = {
  instanceId: number;
  tenantId?: string | null;
  /** When set, skip the network fetch (page-shell prototype / tests). */
  data?: ProcessInstanceCompletedTasksResponse | null;
};

type SubTab = 'completedByMe' | 'allCompleted';

function taskLabel(task: ProcessInstanceCompletedTaskRow): string {
  const title = task.task_title?.trim();
  return title || task.task_name;
}

function completedBy(task: ProcessInstanceCompletedTaskRow): string {
  const name = task.completed_by?.trim();
  return name || '—';
}

/** UTC `YYYY-MM-DD HH:MM:SS` matching Events; not a link. */
function formatTimestamp(epochSeconds: number | null | undefined): string {
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

const EMPTY: ProcessInstanceCompletedTasksResponse = {
  completed_by_me: [],
  all_completed: [],
};

/**
 * Tasks tab body for process instance detail: Completed by me / All
 * completed. Fetches GET /v1.0/m8flow/process-instances/{id}/completed-tasks.
 * Task is title else name, never owner. Empty "Completed by me" uses the
 * mockup sentence. All-completed empty copy stays fog (headers only).
 */
export function ProcessInstanceCompletedTasksTable({
  instanceId,
  tenantId = null,
  data: dataOverride,
}: ProcessInstanceCompletedTasksTableProps) {
  const [data, setData] = useState<ProcessInstanceCompletedTasksResponse>(dataOverride ?? EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(dataOverride === undefined);
  const [subTab, setSubTab] = useState<SubTab>('completedByMe');

  useEffect(() => {
    if (dataOverride !== undefined) {
      setData(dataOverride ?? EMPTY);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchProcessInstanceCompletedTasks(instanceId, tenantId)
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load tasks');
          setData(EMPTY);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [instanceId, tenantId, dataOverride]);

  const rows = subTab === 'completedByMe' ? data.completed_by_me : data.all_completed;
  const showMineEmpty = !loading && !error && subTab === 'completedByMe' && rows.length === 0;

  const columns: DataTableColumn<ProcessInstanceCompletedTaskRow>[] = [
    {
      key: 'task',
      header: 'Task',
      width: 'minmax(160px,2fr)',
      className: 'text-[14px] text-foreground',
      render: (task) => taskLabel(task),
    },
    {
      key: 'completedBy',
      header: 'Completed by',
      width: 'minmax(0,140px)',
      className: 'text-[13px] text-muted-foreground',
      render: (task) => completedBy(task),
    },
    {
      key: 'timestamp',
      header: 'Timestamp',
      width: 'minmax(0,160px)',
      render: (task) => (
        <time
          className="font-mono text-[12.5px] text-muted-foreground"
          dateTime={task.timestamp != null ? new Date(task.timestamp * 1000).toISOString() : undefined}
        >
          {formatTimestamp(task.timestamp)}
        </time>
      ),
    },
  ];

  return (
    <section>
      <Tabs value={subTab} onValueChange={(value) => setSubTab(value as SubTab)} className="mb-4">
        <TabsList className="gap-[22px]">
          <TabsTrigger
            value="completedByMe"
            className="text-[14.5px] data-[state=active]:border-info data-[state=active]:text-info"
          >
            Completed by me
          </TabsTrigger>
          <TabsTrigger
            value="allCompleted"
            className="text-[14.5px] data-[state=active]:border-info data-[state=active]:text-info"
          >
            All completed
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {error ? (
        <p className="py-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="py-8 text-sm text-muted-foreground" aria-busy="true">
          Loading tasks…
        </p>
      ) : null}

      {showMineEmpty ? (
        <p className="m-0 text-[13.5px] text-muted-foreground italic">
          You have not completed any tasks for this process instance.
        </p>
      ) : null}

      {!loading && !showMineEmpty ? (
        <Card variant="bordered" className="overflow-x-auto">
          <DataTable
            columns={columns}
            rows={rows}
            getRowKey={(task) => task.id}
            emptyState=""
            minWidth="560px"
          />
        </Card>
      ) : null}
    </section>
  );
}
