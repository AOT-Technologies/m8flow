import { describe, expect, it } from 'vitest';

import { processInstanceLifecycleVisibility } from './lifecycleActions';

describe('processInstanceLifecycleVisibility', () => {
  it('hides all three on terminal statuses', () => {
    for (const status of ['complete', 'error', 'terminated']) {
      expect(processInstanceLifecycleVisibility(status)).toEqual({
        terminate: false,
        suspend: false,
        resume: false,
      });
    }
  });

  it('shows terminate and suspend on live statuses', () => {
    for (const status of ['running', 'waiting', 'user_input_required', 'not_started']) {
      expect(processInstanceLifecycleVisibility(status)).toEqual({
        terminate: true,
        suspend: true,
        resume: false,
      });
    }
  });

  it('swaps resume in for suspend when suspended', () => {
    expect(processInstanceLifecycleVisibility('suspended')).toEqual({
      terminate: true,
      suspend: false,
      resume: true,
    });
  });
});
