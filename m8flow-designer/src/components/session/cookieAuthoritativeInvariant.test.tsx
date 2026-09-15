/**
 * HARD INVARIANT (AGENTS.md multitenancy rule): the cookie
 * `m8flow_selected_tenant` is authoritative for the finalized active tenant;
 * the localStorage key `m8flow_global_selected_tenant` is only a super-admin
 * sidebar *view* preference and can never stand in for the cookie.
 *
 * Two distinct tenant notions live in `useActiveTenant()` (see
 * .scratch/use-active-tenant-seam/assets/01-provider-boundary.md):
 *   - `activeTenantId`  — the COOKIE. Finalization truth; what downstream
 *     cookie-gated decisions (TenantManagement, lib/auth's selection gate)
 *     rely on. Must NEVER be derived from localStorage.
 *   - `scopedTenantId` / `needsTenant` — the super-admin VIEW filter, driven by
 *     the localStorage sidebar pick. A super-admin narrowing their view with a
 *     localStorage selection is legitimate and does not touch finalization.
 *
 * This file pins that separation so no future change can let a stale
 * localStorage alias satisfy the cookie-authoritative finalization gate.
 */
import { renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GLOBAL_TENANT_STORAGE_KEY } from '@/lib/selectedTenant';
import { SessionProvider } from './SessionProvider';
import { useActiveTenant } from './hooks';

const mockIsSuperAdmin = vi.fn<() => boolean>(() => false);
const mockGetSelectedTenantId = vi.fn<() => string | null>(() => null);

vi.mock('@/lib/auth', () => ({
  isSuperAdmin: () => mockIsSuperAdmin(),
  getSelectedTenantId: () => mockGetSelectedTenantId(),
  getActiveTenantDisplayLabel: () => null,
}));

vi.mock('@/lib/api', () => ({
  fetchCapabilities: () => Promise.resolve({}),
  fetchTenants: () => Promise.resolve([]),
  fetchOrganizationMemberships: () => Promise.resolve([]),
}));

function wrapper({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}

afterEach(() => {
  vi.clearAllMocks();
  mockIsSuperAdmin.mockReturnValue(false);
  mockGetSelectedTenantId.mockReturnValue(null);
  try {
    localStorage.clear();
  } catch {
    /* ignore */
  }
});

describe('cookie-authoritative invariant', () => {
  it('activeTenantId is the cookie, never localStorage — a stale alias with no cookie stays null (non-super-admin)', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'stale-alias');
    mockIsSuperAdmin.mockReturnValue(false);
    mockGetSelectedTenantId.mockReturnValue(null); // no cookie

    const { result } = renderHook(() => useActiveTenant(), { wrapper });

    expect(result.current.activeTenantId).toBeNull();
  });

  it('activeTenantId is the cookie, never localStorage — also for a super-admin with a sidebar pick and no cookie', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'stale-alias');
    mockIsSuperAdmin.mockReturnValue(true);
    mockGetSelectedTenantId.mockReturnValue(null); // no cookie

    const { result } = renderHook(() => useActiveTenant(), { wrapper });

    expect(result.current.activeTenantId).toBeNull();
  });

  it('the cookie wins when it disagrees with localStorage', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'stale-alias');
    mockGetSelectedTenantId.mockReturnValue('real-tenant-from-cookie');

    const { result } = renderHook(() => useActiveTenant(), { wrapper });

    expect(result.current.activeTenantId).toBe('real-tenant-from-cookie');
  });

  it('super-admin VIEW scope is localStorage-driven but does not set the finalization value', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 't1');
    mockIsSuperAdmin.mockReturnValue(true);
    mockGetSelectedTenantId.mockReturnValue(null); // no cookie

    const { result } = renderHook(() => useActiveTenant(), { wrapper });

    // The localStorage pick legitimately narrows the super-admin's view...
    expect(result.current.scopedTenantId).toBe('t1');
    expect(result.current.needsTenant).toBe(false);
    // ...but it never becomes the cookie-authoritative finalization value.
    expect(result.current.activeTenantId).toBeNull();
  });

  it('a non-super-admin is never gated on the super-admin axis and finalizes via the cookie only', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'stale-alias');
    mockIsSuperAdmin.mockReturnValue(false);

    // No cookie: not super-admin, so scopedTenantId stays null and the
    // super-admin view gate never trips — finalization is the cookie's job.
    // (Fresh mounts, not rerender: activeTenantId is read from the cookie once
    // at mount, which mirrors reality — the cookie only changes on a backend
    // redirect/reload, not mid-session.)
    mockGetSelectedTenantId.mockReturnValue(null);
    const first = renderHook(() => useActiveTenant(), { wrapper });
    expect(first.result.current.scopedTenantId).toBeNull();
    expect(first.result.current.needsTenant).toBe(false);
    expect(first.result.current.activeTenantId).toBeNull();
    first.unmount();

    // Cookie present: finalized to that tenant, independent of the stale alias.
    mockGetSelectedTenantId.mockReturnValue('acme');
    const second = renderHook(() => useActiveTenant(), { wrapper });
    expect(second.result.current.activeTenantId).toBe('acme');
  });
});
