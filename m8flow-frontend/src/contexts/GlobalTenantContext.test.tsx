import React from 'react';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, renderHook, act, screen } from '@testing-library/react';
import {
  GlobalTenantProvider,
  useGlobalTenant,
  GLOBAL_TENANT_STORAGE_KEY,
} from './GlobalTenantContext';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <GlobalTenantProvider>{children}</GlobalTenantProvider>
);

afterEach(() => {
  vi.restoreAllMocks();
  try {
    localStorage.clear();
  } catch {
    /* ignore */
  }
});

describe('GlobalTenantContext', () => {
  it('reads the persisted tenant from localStorage on init', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'tenant-42');
    const { result } = renderHook(() => useGlobalTenant(), { wrapper });
    expect(result.current.selectedTenantId).toBe('tenant-42');
  });

  it('persists and clears the tenant via setSelectedTenantId', () => {
    const { result } = renderHook(() => useGlobalTenant(), { wrapper });

    act(() => result.current.setSelectedTenantId('tenant-7'));
    expect(result.current.selectedTenantId).toBe('tenant-7');
    expect(localStorage.getItem(GLOBAL_TENANT_STORAGE_KEY)).toBe('tenant-7');

    act(() => result.current.setSelectedTenantId(''));
    expect(result.current.selectedTenantId).toBe('');
    expect(localStorage.getItem(GLOBAL_TENANT_STORAGE_KEY)).toBeNull();
  });

  it('does not crash when localStorage access throws, defaulting to empty', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });

    let result: ReturnType<typeof useGlobalTenant> | undefined;
    function Consumer() {
      result = useGlobalTenant();
      return <div data-testid="tenant">{result.selectedTenantId || 'none'}</div>;
    }

    expect(() =>
      render(
        <GlobalTenantProvider>
          <Consumer />
        </GlobalTenantProvider>,
      ),
    ).not.toThrow();

    expect(screen.getByTestId('tenant').textContent).toBe('none');
    expect(result?.selectedTenantId).toBe('');

    // Updating tenant must also not throw even though setItem throws.
    expect(() => act(() => result?.setSelectedTenantId('tenant-9'))).not.toThrow();
    expect(result?.selectedTenantId).toBe('tenant-9');
  });
});
