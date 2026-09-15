import { render, screen } from '@testing-library/react';
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SessionFixtureContext } from '@/components/session/testSupport';
import { activeTenantFromContext, capabilitiesFromContext } from '@/components/session/testSupport';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => ({
    tenants: [],
    refreshTenants: () => {},
    organizationMemberships: [],
    activeTenantLabel: null,
  }),
}));
import HomePage from './HomePage';

vi.mock('./components/HomeStatsGrid', () => ({
  HomeStatsGrid: ({
    tenantId,
    showTotalTenants,
  }: {
    tenantId: string | null;
    showTotalTenants: boolean;
  }) => (
    <div
      data-testid="home-stats-grid"
      data-tenant={tenantId ?? ''}
      data-show-total={String(showTotalTenants)}
    />
  ),
}));

vi.mock('./components/RecentInstancesTable', () => ({
  RecentInstancesTable: () => <div data-testid="recent-instances-table" />,
}));

vi.mock('./components/MyTasksList', () => ({
  MyTasksList: () => <div data-testid="my-tasks-list" />,
}));

function renderHome(context: SessionFixtureContext) {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  function Shell() {
    return <Outlet context={context} />;
  }

  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <Shell />,
        children: [{ index: true, element: <HomePage /> }],
      },
    ],
    { initialEntries: ['/'] },
  );

  return render(<RouterProvider router={router} />);
}

describe('HomePage', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders Home content using AppShell outlet context', () => {
    renderHome({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: true,
    });

    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-tenant', 't1');
    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-show-total', 'true');
    expect(screen.getByTestId('recent-instances-table')).toBeInTheDocument();
    expect(screen.getByTestId('my-tasks-list')).toBeInTheDocument();
  });

  it('passes null tenant and hides total-tenants for a regular user context', () => {
    renderHome({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
    });

    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-tenant', '');
    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-show-total', 'false');
  });
});
