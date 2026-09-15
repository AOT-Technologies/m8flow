import { ApiError } from './api';

/** Turns a start-instance failure into a message the user can act on. The
 * backend returns 422 for an unstartable model (e.g. no start event), 403
 * when the caller lacks the start permission. Shared by the processes list
 * and the process-model overview. */
export function startErrorMessage(err: unknown, displayName: string): string {
  if (err instanceof ApiError) {
    if (err.serverMessage) {
      return err.serverMessage;
    }
    if (err.status === 422) {
      return `“${displayName}” can’t be started — its diagram may be missing a start event.`;
    }
    if (err.status === 403) {
      return `You don’t have permission to start “${displayName}”.`;
    }
  }
  return err instanceof Error ? err.message : 'Failed to start process';
}
