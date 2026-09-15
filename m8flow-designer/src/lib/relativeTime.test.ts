import { describe, expect, it } from 'vitest';

import { formatRelativeTime } from './relativeTime';

describe('formatRelativeTime', () => {
  const nowMs = 1_700_000_000_000;

  it('returns an em dash for null/undefined', () => {
    expect(formatRelativeTime(null, nowMs)).toBe('—');
    expect(formatRelativeTime(undefined, nowMs)).toBe('—');
  });

  it('formats hours and days like the mockup', () => {
    const nowSec = Math.floor(nowMs / 1000);
    expect(formatRelativeTime(nowSec - 2 * 3600, nowMs)).toBe('2h ago');
    expect(formatRelativeTime(nowSec - 3 * 86400, nowMs)).toBe('3d ago');
  });
});

describe('formatRelativeTimeVerbose', () => {
  const nowMs = 1_700_000_000_000;

  it('matches My tasks mockup phrasing', async () => {
    const { formatRelativeTimeVerbose } = await import('./relativeTime');
    const nowSec = Math.floor(nowMs / 1000);
    expect(formatRelativeTimeVerbose(nowSec - 10 * 3600, nowMs)).toBe('about 10 hours ago');
    expect(formatRelativeTimeVerbose(nowSec - 3 * 86400, nowMs)).toBe('3 days ago');
  });
});
