import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  fetchProcessInstancePendingTasks,
  type ProcessInstancePendingTaskRow,
  type WaitingFor,
} from '@/lib/processInstancesApi';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export type ProcessInstanceCompletableTasksTableProps = {
  instanceId: number;
  tenantId?: string | null;
  /** When set, skip the network fetch (page-shell prototype / tests). */
  tasks?: ProcessInstancePendingTaskRow[] | null;
};

function taskLabel(task: ProcessInstancePendingTaskRow): string {
  const title = task.task_title?.trim();
  return title || task.task_name;
}

export function formatWaitingFor(
  waiting: WaitingFor | null | undefined,
  lane?: string | null,
): string {
  if (waiting) {
    if (waiting.type === 'group') return `Group: ${waiting.label}`;
    if (waiting.type === 'initiator') return `${waiting.label} (initiator)`;
    return waiting.label;
  }
  return lane?.trim() || '—';
}

/**
 * Open tasks — every incomplete human task on this instance and who it is
 * waiting for. Go (opens `/task-review/{human_task_id}`) only on rows the
 * viewer can complete. (Named for its origin as "Tasks I can complete".)
 */
export function ProcessInstanceCompletableTasksTable({
  instanceId,
  tenantId = null,
  tasks: tasksOverride,
}: ProcessInstanceCompletableTasksTableProps) {
  const [tasks, setTasks] = useState<ProcessInstancePendingTaskRow[]>(tasksOverride ?? []);
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
    fetchProcessInstancePendingTasks(instanceId, tenantId)
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

  const columns: DataTableColumn<ProcessInstancePendingTaskRow>[] = [
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
      width: 'minmax(0,200px)',
      className: 'text-[13.5px] text-muted-foreground',
      render: (task) => (
        <span title={task.waiting_for?.usernames.join(', ') || undefined}>
          {formatWaitingFor(task.waiting_for, task.lane_name)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      width: 'minmax(0,100px)',
      className: 'text-right',
      render: (task) =>
        task.can_complete ? (
          <div className="flex justify-end">
            <Button asChild variant="pill-info" size="pill">
              <Link to={`/task-review/${task.id}`}>Go</Link>
            </Button>
          </div>
        ) : null,
    },
  ];

  const notice =
    tasks.length === 0
      ? 'No open tasks on this instance.'
      : tasks.some((task) => task.can_complete)
        ? null
        : 'No tasks are currently assigned to you.';

  return (
    <section>
      <h2 className="mb-3 font-display text-[19px] font-semibold text-foreground">Open tasks</h2>
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
          <>
            {notice && !error ? (
              <p className="px-[22px] py-4 text-sm text-muted-foreground">{notice}</p>
            ) : null}
            {tasks.length > 0 ? (
              <DataTable
                columns={columns}
                rows={tasks}
                getRowKey={(task) => task.id}
                emptyState=""
                minWidth="520px"
              />
            ) : null}
          </>
        )}
      </Card>
    </section>
  );
}
