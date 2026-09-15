import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Outlet, Route, Routes, useParams } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/tasksApi', () => ({ fetchTaskReviewList: vi.fn() }));

import { fetchTaskReviewList, type TaskReviewListResponse } from '@/lib/tasksApi';
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
import TaskReviewInboxPage from './TaskReviewInboxPage';

const mockFetch = fetchTaskReviewList as unknown as ReturnType<typeof vi.fn>;

const CTX: SessionFixtureContext = {
  scopedTenantId: null,
  selectedTenantId: null,
  isSuperAdmin: false,
  canManageProcesses: false,
};

const ONE_TASK: TaskReviewListResponse = {
  results: [
    {
      id: 42,
      task_title: 'Review Expense Claim',
      task_name: 'review',
      process_model_display_name: 'Approval With Escalation',
      process_instance_id: 210,
      submitted_by: 'Priya Nair',
      status: 'READY',
      created_at_in_seconds: Math.floor(Date.now() / 1000) - 3600,
      tenant_name: 'aot-demo',
    },
  ],
  pagination: { page: 1, per_page: 20, total: 1 },
};

function DetailMarker() {
  const { taskId } = useParams();
  return <div>DETAIL {taskId}</div>;
}

function renderInbox(ctx: SessionFixtureContext = CTX) {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(ctx));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(ctx));
  return render(
    <MemoryRouter initialEntries={['/task-review']}>
      <Routes>
        <Route element={<Outlet context={ctx} />}>
          <Route path="task-review" element={<TaskReviewInboxPage />} />
          <Route path="task-review/:taskId" element={<DetailMarker />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('TaskReviewInboxPage', () => {
  it('fetches with page/perPage and renders task rows', async () => {
    mockFetch.mockResolvedValue(ONE_TASK);
    renderInbox();
    expect(await screen.findByText('Review Expense Claim')).toBeInTheDocument();
    expect(screen.getByText('Approval With Escalation')).toBeInTheDocument();
    expect(screen.getByText('Priya Nair')).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith({ page: 1, perPage: 20, tenantId: undefined });
  });

  it('hides the Tenant column for a non-super-admin', async () => {
    mockFetch.mockResolvedValue(ONE_TASK);
    renderInbox();
    await screen.findByText('Review Expense Claim');
    expect(screen.queryByRole('columnheader', { name: 'Tenant' })).not.toBeInTheDocument();
  });

  it('shows the Tenant column and passes tenantId for a super-admin scope', async () => {
    mockFetch.mockResolvedValue(ONE_TASK);
    renderInbox({ ...CTX, isSuperAdmin: true, scopedTenantId: 't1' });
    await screen.findByText('Review Expense Claim');
    expect(screen.getByRole('columnheader', { name: 'Tenant' })).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith({ page: 1, perPage: 20, tenantId: 't1' });
  });

  it('navigates to the task detail when a row is clicked', async () => {
    mockFetch.mockResolvedValue(ONE_TASK);
    renderInbox();
    const row = await screen.findByText('Review Expense Claim');
    fireEvent.click(row);
    expect(await screen.findByText(/DETAIL 42/)).toBeInTheDocument();
  });

  it('shows empty copy when there are no tasks', async () => {
    mockFetch.mockResolvedValue({ results: [], pagination: { page: 1, per_page: 20, total: 0 } });
    renderInbox();
    expect(await screen.findByText('No pending tasks.')).toBeInTheDocument();
  });
});
