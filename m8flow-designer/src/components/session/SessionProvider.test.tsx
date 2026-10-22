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
const mockCheckPermissions = vi.fn().mockResolvedValue({
  '/process-models': { GET: true, POST: true, PUT: true },
  '/process-instances': { GET: true, POST: true },
  '/m8flow/mcp-connection': { GET: true },
  '/messages': { GET: true },
  '/secrets': { GET: true },
  '/m8flow/connectors-grouped': { GET: true },
  '/m8flow/templates': { GET: true },
  '/m8flow/task-review-access': { GET: true },
});
const mockFetchTenants = vi.fn().mockResolvedValue([]);
const mockFetchOrganizationMemberships = vi.fn().mockResolvedValue([]);

vi.mock('@/lib/auth', () => ({
  isSuperAdmin: () => mockIsSuperAdmin(),
  getSelectedTenantId: () => mockGetSelectedTenantId(),
  getActiveTenantDisplayLabel: (extra?: unknown) => mockGetActiveTenantDisplayLabel(extra),
}));

vi.mock('@/lib/api', () => ({
  fetchCapabilities: () => mockFetchCapabilities(),
  checkPermissions: (...args: unknown[]) => mockCheckPermissions(...args),
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
  mockCheckPermissions.mockResolvedValue({
    '/process-models': { GET: true, POST: true, PUT: true },
    '/process-instances': { GET: true, POST: true },
    '/m8flow/mcp-connection': { GET: true },
    '/messages': { GET: true },
    '/secrets': { GET: true },
    '/m8flow/connectors-grouped': { GET: true },
    '/m8flow/templates': { GET: true },
    '/m8flow/task-review-access': { GET: true },
  });
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
  it('checks process-list access against the process-model backend endpoint', async () => {
    renderHook(() => useCapabilities(), { wrapper });

    await waitFor(() => expect(mockCheckPermissions).toHaveBeenCalledTimes(1));

    const requestsToCheck = mockCheckPermissions.mock.calls[0][0];
    expect(requestsToCheck).toEqual(expect.objectContaining({
      '/process-models': ['GET', 'POST', 'PUT'],
    }));
    expect(requestsToCheck).not.toHaveProperty('/processes');
  });

  it('checks task inbox access against the backend authorization target', async () => {
    mockCheckPermissions.mockResolvedValue({ '/m8flow/task-review-access': { GET: true } });
    const { result } = renderHook(() => useCapabilities(), { wrapper });

    await waitFor(() => expect(result.current.canReadTaskReview).toBe(true));
    expect(mockCheckPermissions.mock.calls[0][0]['/m8flow/task-review-access']).toContain('GET');
    expect(mockCheckPermissions.mock.calls[0][0]).not.toHaveProperty('/m8flow/task-review');
    expect(mockCheckPermissions.mock.calls[0][0]).not.toHaveProperty('/tasks');
  });

  it('uses the process-start route permission instead of the capability summary', async () => {
    mockFetchCapabilities.mockResolvedValue({ can_start_processes: true });
    mockCheckPermissions.mockResolvedValue({
      '/process-instances': { GET: true, POST: false },
    });
    const { result } = renderHook(() => useCapabilities(), { wrapper });

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.canStartProcesses).toBe(false);
    expect(mockCheckPermissions.mock.calls[0][0]['/process-instances']).toContain('POST');
  });

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

  it('uses the process-model PUT permission instead of capability summary data', async () => {
    mockFetchCapabilities.mockResolvedValue({
      can_manage_processes: true,
      can_manage_process_models: true,
    });
    mockCheckPermissions.mockResolvedValue({ '/process-models': { POST: true, PUT: false } });
    const { result } = renderHook(() => useCapabilities(), { wrapper });

    await waitFor(() => expect(result.current.canManageProcesses).toBe(true));
    // A viewer's direct permission check denies model writes.
    expect(result.current.canManageProcessModels).toBe(false);
  });

  it('allows process-model editing when the direct PUT permission is granted', async () => {
    mockFetchCapabilities.mockResolvedValue({ can_manage_process_models: false });
    mockCheckPermissions.mockResolvedValue({ '/process-models': { PUT: true } });
    const { result } = renderHook(() => useCapabilities(), { wrapper });

    await waitFor(() => expect(result.current.canManageProcessModels).toBe(true));
  });

  it('requests and exposes operation-specific write permissions', async () => {
    mockCheckPermissions.mockResolvedValue({
      '/process-models': { POST: true },
      '/process-groups': { POST: true, PUT: false, DELETE: true },
      '/process-models/{id}/copy': { POST: true },
      '/process-instances/{id}/suspend': { POST: true },
      '/process-instances/{id}/resume': { POST: false },
      '/process-instances/{id}/terminate': { POST: true },
      '/process-instances/{id}': { DELETE: true },
      '/m8flow/templates': { POST: true },
      '/m8flow/templates/import': { POST: false },
      '/m8flow/templates/{id}': { PUT: true, DELETE: false },
      '/m8flow/templates/{id}/files/{file}': { PUT: true, DELETE: false },
      '/m8flow/connector-profiles': { POST: true },
      '/m8flow/connector-profiles/{id}': { PUT: false, DELETE: true },
      '/secrets': { POST: true },
      '/secrets/{key}': { PUT: false, DELETE: true },
      '/m8flow/task-review-access/{id}/submit': { POST: true },
      '/m8flow/home-task-count': { GET: true },
      '/m8flow/tenant-realms': { POST: true },
      '/m8flow/tenants/{id}/members': { POST: false },
      '/m8flow/nats-tokens/{id}': { DELETE: true },
    });

    const { result } = renderHook(() => useCapabilities(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('ready'));

    const request = mockCheckPermissions.mock.calls[0][0];
    expect(request['/process-models/{id}/copy']).toEqual(['POST']);
    expect(request['/process-instances/{id}/terminate']).toEqual(['POST']);
    expect(request['/process-instances/{id}']).toEqual(['DELETE']);
    expect(request['/m8flow/tenants/{id}/groups/{group}/roles/{role}']).toEqual(['PUT', 'DELETE']);
    expect(result.current.canCreateProcessModels).toBe(true);
    expect(result.current.canUpdateProcessGroups).toBe(false);
    expect(result.current.canCopyProcessModels).toBe(true);
    expect(result.current.canSuspendProcessInstances).toBe(true);
    expect(result.current.canResumeProcessInstances).toBe(false);
    expect(result.current.canTerminateProcessInstances).toBe(true);
    expect(result.current.canDeleteProcessInstances).toBe(true);
    expect(result.current.canCreateTemplates).toBe(true);
    expect(result.current.canImportTemplates).toBe(false);
    expect(result.current.canUpdateTemplates).toBe(true);
    expect(result.current.canDeleteTemplates).toBe(false);
    expect(result.current.canUpdateTemplateFiles).toBe(true);
    expect(result.current.canDeleteTemplateFiles).toBe(false);
    expect(result.current.canCreateConnectorProfiles).toBe(true);
    expect(result.current.canUpdateConnectorProfiles).toBe(false);
    expect(result.current.canDeleteConnectorProfiles).toBe(true);
    expect(result.current.canCreateSecrets).toBe(true);
    expect(result.current.canUpdateSecrets).toBe(false);
    expect(result.current.canDeleteSecrets).toBe(true);
    expect(result.current.canCreateTenants).toBe(true);
    expect(result.current.canAddTenantMembers).toBe(false);
    expect(result.current.canSubmitTaskReviews).toBe(true);
    expect(result.current.canReadHomeTaskCount).toBe(true);
    expect(result.current.canRevokeNatsApiKeys).toBe(true);
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
