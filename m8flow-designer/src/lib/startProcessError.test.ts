import { describe, expect, it } from 'vitest';

import { ApiError } from './api';
import { startErrorMessage } from './startProcessError';

describe('startErrorMessage', () => {
  it('prefers the backend message', () => {
    const err = new ApiError('/start', 422, 'POST', 'lane Submitters has no owners');
    expect(startErrorMessage(err, 'Invoice')).toBe('lane Submitters has no owners');
  });

  it('explains 422 and 403', () => {
    expect(startErrorMessage(new ApiError('/start', 422, 'POST'), 'Invoice')).toMatch(
      /missing a start event/,
    );
    expect(startErrorMessage(new ApiError('/start', 403, 'POST'), 'Invoice')).toMatch(
      /permission to start/,
    );
  });
});
