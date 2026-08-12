/**
 * Pure task-bucket helpers for useExtendedGrouping (kept out of the hook file for CPD).
 */
import type { ProcessInstanceTask } from '../interfaces';

export const ASSIGNED_TO_ME_SENTINEL =
  'spiff_synthetic_key_indicating_assigned_to_me';

export function groupByProcessGroupPath(
  tasks: ProcessInstanceTask[],
): Record<string, ProcessInstanceTask[]> {
  const buckets: Record<string, ProcessInstanceTask[]> = {};
  for (const task of tasks) {
    const parts = task.process_model_identifier.split('/');
    const key = parts.slice(0, -1).join('/');
    (buckets[key] ??= []).push(task);
  }
  return buckets;
}

export function groupByResponsibleParty(
  tasks: ProcessInstanceTask[],
  meKey: string,
): Record<string, ProcessInstanceTask[]> {
  const buckets: Record<string, ProcessInstanceTask[]> = {};
  for (const task of tasks) {
    const key = task.assigned_user_group_identifier || meKey;
    (buckets[key] ??= []).push(task);
  }
  return buckets;
}
