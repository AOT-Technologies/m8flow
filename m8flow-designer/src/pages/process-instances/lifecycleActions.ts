const TERMINAL = new Set(['complete', 'error', 'terminated']);
const SUSPENDABLE = new Set(['running', 'waiting', 'user_input_required', 'not_started']);

export type ProcessInstanceLifecycleVisibility = {
  terminate: boolean;
  suspend: boolean;
  resume: boolean;
};

/** Header buttons from [Terminate, suspend, and resume on process instance detail].
 * Hide all three on terminal statuses. Resume swaps into the suspend slot. */
export function processInstanceLifecycleVisibility(
  status: string,
): ProcessInstanceLifecycleVisibility {
  if (TERMINAL.has(status)) {
    return { terminate: false, suspend: false, resume: false };
  }
  return {
    terminate: true,
    suspend: SUSPENDABLE.has(status),
    resume: status === 'suspended',
  };
}
