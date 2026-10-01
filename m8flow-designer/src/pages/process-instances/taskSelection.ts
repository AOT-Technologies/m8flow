import type { ProcessInstanceTaskState } from '@/lib/processInstancesApi';

/** Most recent runtime task for a clicked BPMN element — loops and
 * multi-instance leave several task rows per element id. Kept out of
 * InstanceDiagramViewer so it is testable (bpmn-js can't load under vitest). */
export function latestTaskForElement(
  tasks: ProcessInstanceTaskState[],
  bpmnIdentifier: string,
): ProcessInstanceTaskState | null {
  let latest: ProcessInstanceTaskState | null = null;
  for (const task of tasks) {
    if (task.bpmn_identifier !== bpmnIdentifier) continue;
    if (!latest || (task.last_state_change ?? 0) > (latest.last_state_change ?? 0)) latest = task;
  }
  return latest;
}
