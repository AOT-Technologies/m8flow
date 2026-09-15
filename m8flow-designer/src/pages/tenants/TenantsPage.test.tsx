import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SessionFixtureContext } from '@/components/session/testSupport';
import {
  activeTenantFromContext,
  capabilitiesFromContext,
  tenantRegistryFromContext,
} from '@/components/session/testSupport';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
const mockUseTenantRegistry = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => mockUseTenantRegistry(),
}));
import TenantsPage from './TenantsPage';

const mockFetchTenants = vi.fn();
const mockCreateTenant = vi.fn();
const mockRefreshTenants = vi.fn();

vi.mock('@/lib/tenantsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/tenantsApi')>('@/lib/tenantsApi');
  return {
    ...actual,
    fetchTenants: (...args: unknown[]) => mockFetchTenants(...args),
    createTenant: (...args: unknown[]) => mockCreateTenant(...args),
  };
});

function renderWithOutlet(context: Partial<SessionFixtureContext> = {}) {
  const full: SessionFixtureContext = {
    scopedTenantId: null,
    selectedTenantId: null,
    isSuperAdmin: true,
    refreshTenants: mockRefreshTenants,
    ...context,
  };
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(full));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(full));
  mockUseTenantRegistry.mockReturnValue(tenantRegistryFromContext(full));
  return render(
    <MemoryRouter initialEntries={['/tenants']}>
      <Routes>
        <Route element={<Outlet context={full} />}>
          <Route path="/tenants" element={<TenantsPage />} />
          <Route
            path="/tenant-management/:tenantId"
            element={<div data-testid="tenant-management-destination">tenant-admin-page</div>}
          />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const ACME = { id: 't1', name: 'Acme Corp', slug: 'acme-corp', status: 'ACTIVE' as const };
const BETA = { id: 't2', name: 'Beta Labs', slug: 'beta-labs', status: 'INACTIVE' as const };

describe('TenantsPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('explains denial and does not fetch for a non-super-admin', () => {
    renderWithOutlet({ isSuperAdmin: false });
    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(mockFetchTenants).not.toHaveBeenCalled();
    expect(screen.queryByTestId('tenant-add-button')).not.toBeInTheDocument();
  });

  it('lists tenants and filters by name, alias, and status', async () => {
    // `SortDropdown` opens via Radix's pointer-based trigger handling, which
    // `fireEvent.click` alone doesn't exercise in jsdom (confirmed against
    // the raw `ui/dropdown-menu.tsx` primitive directly, independent of this
    // page) — `userEvent` simulates the full pointer/mouse sequence Radix
    // needs. Every other interaction below still uses plain `fireEvent`.
    const user = userEvent.setup();
    mockFetchTenants.mockResolvedValue([ACME, BETA]);
    renderWithOutlet();

    expect(await screen.findByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('Beta Labs')).toBeInTheDocument();
    expect(screen.getByText('Showing 2 of 2 tenants')).toBeInTheDocument();
    expect(screen.queryByTestId('tenant-member-add-button')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /rename/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId('tenant-search-input'), { target: { value: 'acme' } });
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.queryByText('Beta Labs')).not.toBeInTheDocument();
    expect(screen.getByText('Showing 1 of 2 tenants')).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('tenant-search-input'), { target: { value: '' } });
    await user.click(screen.getByRole('button', { name: /^Search by:/ }));
    await user.click(await screen.findByRole('menuitem', { name: 'Tenant alias' }));
    fireEvent.change(screen.getByTestId('tenant-search-input'), { target: { value: 'beta-labs' } });
    expect(screen.getByText('Beta Labs')).toBeInTheDocument();
    expect(screen.queryByText('Acme Corp')).not.toBeInTheDocument();

    fireEvent.change(screen.getByTestId('tenant-search-input'), { target: { value: '' } });
    await user.click(screen.getByRole('button', { name: /^Status:/ }));
    await user.click(await screen.findByRole('menuitem', { name: 'Inactive' }));
    expect(screen.getByText('Beta Labs')).toBeInTheDocument();
    expect(screen.queryByText('Acme Corp')).not.toBeInTheDocument();
  });

  it('sorts by alias when the alias header is clicked', async () => {
    mockFetchTenants.mockResolvedValue([BETA, ACME]);
    renderWithOutlet();
    await screen.findByText('Acme Corp');

    fireEvent.click(screen.getByTestId('tenant-sort-slug'));
    fireEvent.click(screen.getByTestId('tenant-sort-slug'));
    const rows = screen.getAllByRole('row').slice(1);
    expect(rows[0]).toHaveTextContent('Beta Labs');
    expect(rows[1]).toHaveTextContent('Acme Corp');
  });

  it('creates a tenant from a name-only dialog', async () => {
    mockFetchTenants.mockResolvedValueOnce([]).mockResolvedValueOnce([ACME]);
    mockCreateTenant.mockResolvedValue(ACME);
    renderWithOutlet();

    fireEvent.click(await screen.findByTestId('tenant-add-button'));
    fireEvent.change(screen.getByTestId('tenant-name'), { target: { value: 'Acme Corp' } });
    fireEvent.click(screen.getByTestId('tenant-save'));

    await waitFor(() => {
      expect(mockCreateTenant).toHaveBeenCalledWith('Acme Corp', []);
    });
    expect(mockRefreshTenants).toHaveBeenCalled();
    expect(await screen.findByText('Acme Corp')).toBeInTheDocument();
  });

  it('blocks a duplicate name before posting', async () => {
    mockFetchTenants.mockResolvedValue([ACME]);
    renderWithOutlet();

    fireEvent.click(await screen.findByTestId('tenant-add-button'));
    fireEvent.change(screen.getByTestId('tenant-name'), { target: { value: 'Acme Corp' } });
    fireEvent.click(screen.getByTestId('tenant-save'));

    expect(await screen.findByText('A tenant with this name already exists.')).toBeInTheDocument();
    expect(mockCreateTenant).not.toHaveBeenCalled();
  });

  it('links each tenant to tenant management for that tenant', async () => {
    mockFetchTenants.mockResolvedValue([ACME, BETA]);
    renderWithOutlet();

    await screen.findByText('Acme Corp');
    expect(screen.getByTestId('tenant-open-t1')).toHaveAttribute('href', '/tenant-management/t1');
    expect(screen.getByTestId('tenant-manage-t1')).toHaveAttribute('href', '/tenant-management/t1');
    expect(screen.getByTestId('tenant-open-t2')).toHaveAttribute('href', '/tenant-management/t2');
    expect(screen.queryByRole('button', { name: /rename/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId('tenant-member-add-button')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('tenant-open-t1'));
    expect(await screen.findByTestId('tenant-management-destination')).toBeInTheDocument();
  });
});
