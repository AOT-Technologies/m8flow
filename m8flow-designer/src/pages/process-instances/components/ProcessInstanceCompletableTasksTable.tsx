import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  fetchProcessInstanceCompletableTasks,
  type ProcessInstanceCompletableTaskRow,
} from '@/lib/processInstancesApi';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export type ProcessInstanceCompletableTasksTableProps = {
  instanceId: number;
  tenantId?: string | null;
  /** When set, skip the network fetch (page-shell prototype / tests). */
  tasks?: ProcessInstanceCompletableTaskRow[] | null;
};

function taskLabel(task: ProcessInstanceCompletableTaskRow): string {
  const title = task.task_title?.trim();
  return title || task.task_name;
}

function waitingFor(task: ProcessInstanceCompletableTaskRow): string {
  const lane = task.lane_name?.trim();
  return lane || '—';
}

/**
 * Tasks I can complete — current-user candidate human tasks on this
 * instance. Go opens Task Review (`/task-review/{human_task_id}`). Empty
 * copy stays map fog (headers only).
 */
export function ProcessInstanceCompletableTasksTable({
  instanceId,
  tenantId = null,
  tasks: tasksOverride,
}: ProcessInstanceCompletableTasksTableProps) {
  const [tasks, setTasks] = useState<ProcessInstanceCompletableTaskRow[]>(tasksOverride ?? []);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(tasksOverride === undefined);

  useEffect(() => {
    if (tasksOverride !== undefined) {
      setTasks(tasksOverride ?? []);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchProcessInstanceCompletableTasks(instanceId, tenantId)
      .then((payload) => {
        if (!cancelled) setTasks(payload);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load tasks');
          setTasks([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [instanceId, tenantId, tasksOverride]);

  const columns: DataTableColumn<ProcessInstanceCompletableTaskRow>[] = [
    {
      key: 'task',
      header: 'Task',
      width: 'minmax(160px,2fr)',
      className: 'text-[14.5px] font-semibold text-foreground',
      render: (task) => taskLabel(task),
    },
    {
      key: 'waitingFor',
      header: 'Waiting for',
      width: 'minmax(0,140px)',
      className: 'text-[13.5px] text-muted-foreground',
      render: (task) => waitingFor(task),
    },
    {
      key: 'actions',
      header: 'Actions',
      width: 'minmax(0,100px)',
      className: 'text-right',
      render: (task) => (
        <div className="flex justify-end">
          <Button asChild variant="pill-info" size="pill">
            <Link to={`/task-review/${task.id}`}>Go</Link>
          </Button>
        </div>
      ),
    },
  ];

  return (
    <section>
      <h2 className="mb-3 font-display text-[19px] font-semibold text-foreground">
        Tasks I can complete
      </h2>
      <Card variant="bordered" className="overflow-x-auto">
        {error ? (
          <p className="px-[22px] py-4 text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="px-[22px] py-8 text-sm text-muted-foreground" aria-busy="true">
            Loading tasks…
          </p>
        ) : (
          <DataTable
            columns={columns}
            rows={tasks}
            getRowKey={(task) => task.id}
            emptyState=""
            minWidth="520px"
          />
        )}
      </Card>
    </section>
  );
}
