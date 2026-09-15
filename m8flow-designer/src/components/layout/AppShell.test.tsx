import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GLOBAL_TENANT_STORAGE_KEY } from '@/lib/selectedTenant';
import { SessionProvider } from '@/components/session/SessionProvider';
import { AppShell } from './AppShell';

const mockGetCurrentUser = vi.fn();
const mockLogout = vi.fn();
const mockIsSuperAdmin = vi.fn();
// Explicit generic (rather than inferring the mock's type from its default
// implementation) so the declared *type* accepts the optional arg both call
// sites below actually pass (the forwarding shim a few lines down and the
// `mockImplementation` override further below), without needing an unused
// parameter in the default no-op implementation itself. The real
// `getActiveTenantDisplayLabel` takes one `OrganizationMembership[]` param,
// so a zero-arg mock signature was always a mismatch; `unknown` here
// (rather than importing that type) keeps the fixtures below free to pass
// loosely-shaped test data.
const mockGetActiveTenantDisplayLabel = vi.fn<(extra?: unknown) => string | null>(() => null);
const mockGetSelectedTenantId = vi.fn<() => string | null>(() => null);
const mockFetchTenants = vi.fn().mockResolvedValue([]);
const mockFetchOrganizationMemberships = vi.fn().mockResolvedValue([]);

vi.mock('@/lib/auth', () => ({
  getCurrentUser: () => mockGetCurrentUser(),
  isSuperAdmin: () => mockIsSuperAdmin(),
  logout: () => mockLogout(),
  getActiveTenantDisplayLabel: (extra?: unknown) => mockGetActiveTenantDisplayLabel(extra),
  getSelectedTenantId: () => mockGetSelectedTenantId(),
}));

const mockFetchCapabilities = vi.fn().mockResolvedValue({
  can_manage_processes: false,
  can_manage_tenant: false,
});

vi.mock('@/lib/api', () => ({
  fetchTenants: (...args: unknown[]) => mockFetchTenants(...args),
  fetchCapabilities: () => mockFetchCapabilities(),
  fetchOrganizationMemberships: () => mockFetchOrganizationMemberships(),
}));

function renderShell(initialPath = '/') {
  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: (
          <SessionProvider>
            <AppShell />
          </SessionProvider>
        ),
        children: [
          { index: true, element: <div>home-outlet</div> },
          { path: 'processes', element: <div>processes-outlet</div> },
          {
            path: 'processes/:processModelId',
            element: <div>detail-outlet</div>,
          },
        ],
      },
    ],
    { initialEntries: [initialPath] },
  );
  return render(<RouterProvider router={router} />);
}

describe('AppShell', () => {
  afterEach(() => {
    vi.clearAllMocks();
    mockIsSuperAdmin.mockReturnValue(false);
    mockGetActiveTenantDisplayLabel.mockReturnValue(null);
    mockGetSelectedTenantId.mockReturnValue(null);
    mockFetchOrganizationMemberships.mockResolvedValue([]);
    mockFetchCapabilities.mockResolvedValue({
      can_manage_processes: false,
      can_read_secrets: false,
      can_manage_secrets: false,
      can_read_connectors: false,
      can_manage_connector_profiles: false,
      can_manage_tenant: false,
    });
    try {
      localStorage.clear();
    } catch {
      /* ignore */
    }
  });

  it.each([
    [
      'username when both username and email are present',
      { username: 'editor', email: 'editor@example.com' },
      'editor',
    ],
    ['email when username is null', { username: null, email: 'editor@example.com' }, 'editor@example.com'],
    ['unknown user when both claims are null', { username: null, email: null }, 'unknown user'],
    ['unknown user when getCurrentUser returns null', null, 'unknown user'],
    [
      'empty username rather than falling through to email (nullish coalescing)',
      { username: '', email: 'editor@example.com' },
      '',
    ],
  ] as const)('shows %s in the Profile menu', (_label, user, displayed) => {
    mockGetCurrentUser.mockReturnValue(user);

    renderShell();

    fireEvent.click(screen.getByRole('button', { name: 'Profile' }));
    const identity = screen.getByRole('menu', { name: 'Profile' }).querySelector('strong');
    expect(identity).not.toBeNull();
    expect(identity?.textContent).toBe(displayed);
  });

  it('for a non-admin editor: no Tenant selector and does not fetch tenants', () => {
    mockGetCurrentUser.mockReturnValue({ username: 'editor', email: null });
    mockIsSuperAdmin.mockReturnValue(false);

    renderShell();

    expect(screen.getByText('flow', { exact: false })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Home' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Processes' })).toBeInTheDocument();
    expect(screen.getByText('Process Instances')).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(mockFetchTenants).not.toHaveBeenCalled();
    expect(screen.getByText('home-outlet')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Tenants' })).not.toBeInTheDocument();
    expect(screen.queryByText('Tenants')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Tenant Management' })).not.toBeInTheDocument();
  });

  it('shows the cookie-backed active tenant badge for a non-admin editor', () => {
    mockGetCurrentUser.mockReturnValue({ username: 'editor', email: null });
    mockIsSuperAdmin.mockReturnValue(false);
    mockGetActiveTenantDisplayLabel.mockReturnValue('Acme Corp');
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 'stale-tenant');

    renderShell();

    expect(screen.getByTestId('nav-tenant-name')).toHaveTextContent('Acme Corp');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(mockFetchTenants).not.toHaveBeenCalled();
  });

  it('replaces a cookie tenant id with the organization-memberships display name', async () => {
    mockGetCurrentUser.mockReturnValue({ username: 'editor', email: null });
    mockIsSuperAdmin.mockReturnValue(false);
    mockGetActiveTenantDisplayLabel.mockImplementation((extra: unknown) => {
        const rows = Array.isArray(extra) ? extra : [];
        if (rows.length > 0) {
          const named = rows.find(
            (row) =>
              row &&
              typeof row === 'object' &&
              typeof (row as { name?: unknown }).name === 'string' &&
              (row as { name: string }).name.trim(),
          ) as { name: string } | undefined;
          return named?.name.trim() ?? null;
        }
        return '860821d8-64f9-43c4-bbdf-ef3010463d5e';
      });
    mockFetchOrganizationMemberships.mockResolvedValue([
      {
        alias: 'acme',
        id: '860821d8-64f9-43c4-bbdf-ef3010463d5e',
        name: 'Acme Corp',
      },
    ]);

    renderShell();

    expect(screen.getByTestId('nav-tenant-name')).toHaveTextContent(
      '860821d8-64f9-43c4-bbdf-ef3010463d5e',
    );
    expect(await screen.findByTestId('nav-tenant-name')).toHaveTextContent('Acme Corp');
    expect(mockFetchOrganizationMemberships).toHaveBeenCalled();
  });

  it('shows Setup → Configuration when capabilities allow secrets read', async () => {
    mockGetCurrentUser.mockReturnValue({ username: 'integrator', email: null });
    mockFetchCapabilities.mockResolvedValue({
      can_manage_processes: false,
      can_read_secrets: true,
      can_manage_secrets: true,
    });

    renderShell();

    expect(await screen.findByRole('link', { name: 'Configuration' })).toHaveAttribute(
      'href',
      '/configuration/secrets',
    );
  });

  it('shows Setup → Connectors when capabilities allow catalog read', async () => {
    mockGetCurrentUser.mockReturnValue({ username: 'editor', email: null });
    mockFetchCapabilities.mockResolvedValue({
      can_manage_processes: true,
      can_read_connectors: true,
      can_manage_connector_profiles: false,
    });

    renderShell();

    expect(await screen.findByRole('link', { name: 'Connectors' })).toHaveAttribute(
      'href',
      '/connectors',
    );
  });

  it('shows Tenant Management when capabilities allow manage tenant', async () => {
    mockGetCurrentUser.mockReturnValue({ username: 'tenant-admin', email: null });
    mockFetchCapabilities.mockResolvedValue({
      can_manage_processes: true,
      can_manage_tenant: true,
    });

    renderShell();

    expect(await screen.findByRole('link', { name: 'Tenant Management' })).toHaveAttribute(
      'href',
      '/tenant-management',
    );
    expect(screen.queryByText('Tenants')).not.toBeInTheDocument();
  });

  it('for a super-admin: shows Tenant selector and fetches tenants', async () => {
    mockGetCurrentUser.mockReturnValue({ username: 'super-admin', email: null });
    mockIsSuperAdmin.mockReturnValue(true);
    mockFetchTenants.mockResolvedValue([{ id: 't1', name: 'Tenant One' }]);
    mockFetchCapabilities.mockResolvedValue({
      can_manage_processes: false,
      can_manage_tenant: true,
    });

    renderShell();

    expect(screen.getByRole('combobox', { name: /Tenant/ })).toBeInTheDocument();
    expect(mockFetchTenants).toHaveBeenCalled();
    expect(screen.queryByTestId('nav-tenant-name')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Tenants' })).toHaveAttribute('href', '/tenants');
    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'Tenant One' })).toBeInTheDocument();
    });
    expect(screen.queryByRole('link', { name: 'Tenant Management' })).not.toBeInTheDocument();
  });

  it('restores the persisted tenant on refresh', () => {
    localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, 't1');
    mockGetCurrentUser.mockReturnValue({ username: 'super-admin', email: null });
    mockIsSuperAdmin.mockReturnValue(true);
    mockFetchTenants.mockResolvedValue([{ id: 't1', name: 'Tenant One' }]);

    renderShell();

    expect(screen.getByRole('combobox', { name: /Tenant/ })).toHaveValue('t1');
  });

  it('persists tenant changes and clears All Tenants', async () => {
    mockGetCurrentUser.mockReturnValue({ username: 'super-admin', email: null });
    mockIsSuperAdmin.mockReturnValue(true);
    mockFetchTenants.mockResolvedValue([{ id: 't1', name: 'Tenant One' }]);

    renderShell();

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'Tenant One' })).toBeInTheDocument();
    });

    const select = screen.getByRole('combobox', { name: /Tenant/ });
    fireEvent.change(select, { target: { value: 't1' } });
    expect(localStorage.getItem(GLOBAL_TENANT_STORAGE_KEY)).toBe('t1');

    fireEvent.change(select, { target: { value: '' } });
    expect(localStorage.getItem(GLOBAL_TENANT_STORAGE_KEY)).toBeNull();
    expect(select).toHaveValue('');
  });

  it('calls logout from the Profile popout menu', () => {
    mockGetCurrentUser.mockReturnValue({ username: 'editor', email: null });

    renderShell();
    fireEvent.click(screen.getByRole('button', { name: 'Profile' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Log out' }));

    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  it('marks Processes active on /processes and keeps Home as a live link', () => {
    mockGetCurrentUser.mockReturnValue({ username: 'editor', email: null });

    renderShell('/processes');

    expect(screen.getByRole('link', { name: 'Processes' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current');
    expect(screen.getByText('processes-outlet')).toBeInTheDocument();
  });
});
