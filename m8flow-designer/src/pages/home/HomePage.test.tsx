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
    showTaskCount,
  }: {
    tenantId: string | null;
    showTotalTenants: boolean;
    showTaskCount: boolean;
  }) => (
    <div
      data-testid="home-stats-grid"
      data-tenant={tenantId ?? ''}
      data-show-total={String(showTotalTenants)}
      data-show-task-count={String(showTaskCount)}
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

  it('shows My tasks when permissions-check grants the Home task permission', () => {
    renderHome({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: false,
      canReadTaskReview: true,
      canReadHomeTaskCount: true,
    });

    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument();
    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-tenant', 't1');
    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-show-total', 'false');
    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-show-task-count', 'true');
    expect(screen.getByTestId('recent-instances-table')).toBeInTheDocument();
    expect(screen.getByTestId('my-tasks-list')).toBeInTheDocument();
  });

  it('hides My tasks when the Home task permission is denied, even if task-list read is allowed', () => {
    renderHome({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canReadTaskReview: true,
      canReadHomeTaskCount: false,
    });

    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-tenant', '');
    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-show-total', 'false');
    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-show-task-count', 'false');
    expect(screen.queryByTestId('my-tasks-list')).not.toBeInTheDocument();
  });

  it('hides My tasks for super-admins when the explicit Home task permission is denied', () => {
    renderHome({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: true,
      canReadHomeTaskCount: false,
    });

    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-show-total', 'true');
    expect(screen.getByTestId('home-stats-grid')).toHaveAttribute('data-show-task-count', 'false');
    expect(screen.queryByTestId('my-tasks-list')).not.toBeInTheDocument();
  });
});
