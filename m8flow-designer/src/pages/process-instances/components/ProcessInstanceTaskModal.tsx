import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { checkPermissions } from '@/lib/api';
import { fetchProcessInstanceTask, type ProcessInstanceTaskState } from '@/lib/processInstancesApi';
import { Alert } from '@/components/library/alert/Alert';
import { Modal } from '@/components/library/modal/Modal';

export type ProcessInstanceTaskModalProps = {
  instanceId: number;
  tenantId?: string | null;
  /** Null = closed. */
  task: ProcessInstanceTaskState | null;
  onClose: () => void;
};

/** Diagram task click: identity, state and the task's data as JSON. */
export function ProcessInstanceTaskModal({ instanceId, tenantId = null, task, onClose }: ProcessInstanceTaskModalProps) {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    if (!task) return undefined;
    let cancelled = false;
    setData(null);
    setError(null);
    setDenied(false);
    // Task data has its own grant (read-task-data); ask before fetching.
    const taskDataUri = `/v1.0/task-data/${instanceId}`;
    checkPermissions({ [taskDataUri]: ['GET'] })
      .then((permissions) => {
        if (cancelled) return;
        if (!permissions[taskDataUri]?.GET) {
          setDenied(true);
          return;
        }
        return fetchProcessInstanceTask(instanceId, task.guid, tenantId).then((detail) => {
          if (!cancelled) setData(detail.data ?? {});
        });
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load task data');
      });
    return () => {
      cancelled = true;
    };
  }, [instanceId, task, tenantId]);

  const canTimeTravel = task?.state === 'COMPLETED' || task?.state === 'ERROR';

  return (
    <Modal
      open={task !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={task ? `${task.bpmn_name || task.bpmn_identifier} (${task.typename})` : ''}
      size="md"
    >
      {task ? (
        <div className="flex min-h-0 flex-1 flex-col gap-3 text-[13.5px]">
          <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5">
            <dt className="text-muted-foreground">State</dt>
            <dd>{task.state}</dd>
            <dt className="text-muted-foreground">Identifier</dt>
            <dd className="font-mono text-[12.5px]">{task.bpmn_identifier}</dd>
            <dt className="text-muted-foreground">Guid</dt>
            <dd className="break-all font-mono text-[12.5px]">{task.guid}</dd>
          </dl>
          {canTimeTravel ? (
            <Link
              to={{ search: `?to_task_guid=${encodeURIComponent(task.guid)}` }}
              onClick={onClose}
              className="font-semibold text-info hover:underline"
            >
              View process instance at the time when this task was active
            </Link>
          ) : null}
          <div className="font-semibold text-foreground">Task data</div>
          {denied ? (
            <p className="text-muted-foreground">You don't have permission to view this task's data.</p>
          ) : error ? (
            <Alert tone="error">{error}</Alert>
          ) : data === null ? (
            <p className="text-muted-foreground" aria-busy="true">
              Loading task data…
            </p>
          ) : Object.keys(data).length === 0 ? (
            <p className="text-muted-foreground">No data recorded for this task.</p>
          ) : (
            <pre className="max-h-[420px] min-h-0 overflow-auto rounded-md bg-muted p-3 font-mono text-[12px] leading-relaxed">
              {JSON.stringify(data, null, 2)}
            </pre>
          )}
        </div>
      ) : null}
    </Modal>
  );
}
