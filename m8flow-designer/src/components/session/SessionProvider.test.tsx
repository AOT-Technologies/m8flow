import { render, renderHook, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GLOBAL_TENANT_STORAGE_KEY } from '@/lib/selectedTenant';
import { SessionProvider } from './SessionProvider';
import { useActiveTenant, useCapabilities, useTenantRegistry } from './hooks';

const mockIsSuperAdmin = vi.fn<() => boolean>(() => false);
const mockGetSelectedTenantId = vi.fn<() => string | null>(() => null);
const mockGetActiveTenantDisplayLabel = vi.fn<(extra?: unknown) => string | null>(() => null);
const mockFetchCapabilities = vi.fn().mockResolvedValue({});
const mockFetchTenants = vi.fn().mockResolvedValue([]);
const mockFetchOrganizationMemberships = vi.fn().mockResolvedValue([]);

vi.mock('@/lib/auth', () => ({
  isSuperAdmin: () => mockIsSuperAdmin(),
  getSelectedTenantId: () => mockGetSelectedTenantId(),
  getActiveTenantDisplayLabel: (extra?: unknown) => mockGetActiveTenantDisplayLabel(extra),
}));

vi.mock('@/lib/api', () => ({
  fetchCapabilities: () => mockFetchCapabilities(),
  fetchTenants: () => mockFetchTenants(),
  fetchOrganizationMemberships: () => mockFetchOrganizationMemberships(),
}));

function wrapper({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}

afterEach(() => {
  vi.clearAllMocks();
  mockIsSuperAdmin.mockReturnValue(false);
  mockGetSelectedTenantId.mockReturnValue(null);
  mockGetActiveTenantDisplayLabel.mockReturnValue(null);
  mockFetchCapabilities.mockResolvedValue({});
  mockFetchTenants.mockResolvedValue([]);
  mockFetchOrganizationMemberships.mockResolvedValue([]);
  try {
    localStorage.clear();
  } catch {
    /* ignore */
  }
});

describe('useActiveTenant', () => {
  it('non-super-admin: never needsTenant, scopedTenantId is null, activeTenantId is the cookie', () => {
    mockIsSuperAdmin.mockReturnValue(false);
    mockGetSelectedTenantId.mockReturnValue('acme');
    const { result } = renderHook(() => useActiveTenant(), { wrapper });

    expect(result.current.isSuperAdmin).toBe(false);
    expect(result.current.needsTenant).toBe(false);
    expect(result.current.scopedTenantId).toBeNull();
    expect(result.current.activeTenantId).toBe('acme');
  });

  it('super-admin with no sidebar selection: needsTenant is true', () => {
    mockIsSuperAdmin.mockReturnValue(true);
    const { result } = renderHook(() => useActiveTenant(), { wrapper });

    expect(result.current.needsTenant).toBe(true);
    expect(result.current.scopedTenantId).toBeNull();
  });

  it('super-admin with a persisted sidebar selection: needsTenant is false, scopedTenantId is the pick', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 't1');
    mockIsSuperAdmin.mockReturnValue(true);
    const { result } = renderHook(() => useActiveTenant(), { wrapper });

    expect(result.current.selectedTenantId).toBe('t1');
    expect(result.current.scopedTenantId).toBe('t1');
    expect(result.current.needsTenant).toBe(false);
  });

  it('activeTenantId tracks the cookie, not localStorage (invariant: storage never stands in for the cookie)', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'stale-from-storage');
    mockIsSuperAdmin.mockReturnValue(false);
    mockGetSelectedTenantId.mockReturnValue(null); // no cookie
    const { result } = renderHook(() => useActiveTenant(), { wrapper });

    expect(result.current.activeTenantId).toBeNull();
  });
});

describe('useCapabilities', () => {
  it('reflects the fetched backend flags', async () => {
    mockFetchCapabilities.mockResolvedValue({
      can_manage_processes: true,
      can_read_secrets: true,
      can_manage_tenant: true,
    });
    const { result } = renderHook(() => useCapabilities(), { wrapper });

    await waitFor(() => expect(result.current.canManageProcesses).toBe(true));
    expect(result.current.canReadSecrets).toBe(true);
    expect(result.current.canManageTenant).toBe(true);
    expect(result.current.canManageSecrets).toBe(false);
  });
});

describe('useTenantRegistry', () => {
  it('super-admin: loads the tenant registry', async () => {
    mockIsSuperAdmin.mockReturnValue(true);
    mockFetchTenants.mockResolvedValue([{ id: 't1', name: 'Tenant One' }]);
    const { result } = renderHook(() => useTenantRegistry(), { wrapper });

    await waitFor(() => expect(result.current.tenants).toHaveLength(1));
    expect(result.current.tenants[0]).toEqual({ id: 't1', name: 'Tenant One' });
  });

  it('non-super-admin: does not fetch the tenant registry', () => {
    mockIsSuperAdmin.mockReturnValue(false);
    renderHook(() => useTenantRegistry(), { wrapper });

    expect(mockFetchTenants).not.toHaveBeenCalled();
  });
});

describe('provider guard', () => {
  it('throws when a hook is used outside a SessionProvider', () => {
    function Probe() {
      useActiveTenant();
      return null;
    }
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(/within a <SessionProvider>/);
    spy.mockRestore();
    expect(screen.queryByText(/./)).not.toBeInTheDocument();
  });
});
