import i18n from '@/i18n';

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
      return i18n.t('processes.errors.startUnstartable', { name: displayName });
    }
    if (err.status === 403) {
      return i18n.t('processes.errors.startForbidden', { name: displayName });
    }
  }
  return err instanceof Error ? err.message : i18n.t('processes.errors.startFailed');
}
