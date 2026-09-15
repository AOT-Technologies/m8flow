import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import useProcessGroups from './useProcessGroups';

vi.mock('../services/HttpService', () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

import HttpService from '../services/HttpService';

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe('useProcessGroups (m8flow override)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does NOT append tenantId to the URL when none is provided', () => {
    renderHook(() => useProcessGroups({ processInfo: {} }), {
      wrapper: makeWrapper(),
    });
    const lastCall = vi.mocked(HttpService.makeCallToBackend).mock.calls.at(-1);
    expect(lastCall?.[0]?.path).toBe('/process-groups');
  });

  it('appends tenantId to /process-groups when provided', () => {
    renderHook(
      () => useProcessGroups({ processInfo: {}, tenantId: 'tenant-a' }),
      { wrapper: makeWrapper() },
    );
    const lastCall = vi.mocked(HttpService.makeCallToBackend).mock.calls.at(-1);
    expect(lastCall?.[0]?.path).toBe('/process-groups?tenantId=tenant-a');
  });

  it('appends tenantId as additional query when getRunnableProcessModels is on', () => {
    renderHook(
      () =>
        useProcessGroups({
          processInfo: {},
          getRunnableProcessModels: true,
          tenantId: 'tenant-a',
        }),
      { wrapper: makeWrapper() },
    );
    const lastCall = vi.mocked(HttpService.makeCallToBackend).mock.calls.at(-1);
    expect(lastCall?.[0]?.path).toContain(
      '/process-models?filter_runnable_by_user=true',
    );
    expect(lastCall?.[0]?.path).toContain('&tenantId=tenant-a');
  });

  it('url-encodes special characters in the tenant id', () => {
    renderHook(
      () =>
        useProcessGroups({
          processInfo: {},
          tenantId: 'tenant a/b',
        }),
      { wrapper: makeWrapper() },
    );
    const lastCall = vi.mocked(HttpService.makeCallToBackend).mock.calls.at(-1);
    expect(lastCall?.[0]?.path).toBe(
      '/process-groups?tenantId=tenant%20a%2Fb',
    );
  });
});
