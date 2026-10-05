import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Outlet, Route, Routes, useParams } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

afterEach(() => {
  vi.useRealTimers();
});

describe('TaskReviewInboxPage', () => {
  it('fetches with page/perPage and renders task rows', async () => {
    mockFetch.mockResolvedValue(ONE_TASK);
    renderInbox();
    expect(await screen.findByText('Review Expense Claim')).toBeInTheDocument();
    expect(screen.getByText('Approval With Escalation')).toBeInTheDocument();
    expect(screen.getByText('Priya Nair')).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith({ page: 1, perPage: 20, tenantId: undefined, sort: 'newest' });
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
    expect(mockFetch).toHaveBeenCalledWith({ page: 1, perPage: 20, tenantId: 't1', sort: 'newest' });
  });

  it('navigates to the task detail when a row is clicked', async () => {
    mockFetch.mockResolvedValue(ONE_TASK);
    renderInbox();
    const row = await screen.findByText('Review Expense Claim');
    fireEvent.click(row);
    expect(await screen.findByText(/DETAIL 42/)).toBeInTheDocument();
  });

  it('toggles the Created sort between newest and oldest first', async () => {
    mockFetch.mockResolvedValue(ONE_TASK);
    renderInbox();
    await screen.findByText('Review Expense Claim');
    const header = screen.getByTestId('task-review-sort-created');
    expect(header).toHaveAccessibleName('Sort by created, newest first');

    fireEvent.click(header);
    expect(await screen.findByLabelText('Sort by created, oldest first')).toBeInTheDocument();
    expect(mockFetch).toHaveBeenLastCalledWith({
      page: 1,
      perPage: 20,
      tenantId: undefined,
      sort: 'oldest',
    });
  });

  it('marks recently created tasks as New', async () => {
    const fresh = {
      ...ONE_TASK.results[0],
      id: 43,
      task_title: 'Fresh Task',
      created_at_in_seconds: Math.floor(Date.now() / 1000) - 60,
    };
    mockFetch.mockResolvedValue({ ...ONE_TASK, results: [fresh, ONE_TASK.results[0]] });
    renderInbox();
    await screen.findByText('Fresh Task');
    expect(screen.getAllByText('New')).toHaveLength(1);
  });

  it('shows empty copy when there are no tasks', async () => {
    mockFetch.mockResolvedValue({ results: [], pagination: { page: 1, per_page: 20, total: 0 } });
    renderInbox();
    expect(await screen.findByText('No pending tasks.')).toBeInTheDocument();
  });

  it('keeps the last good list when a background poll fails', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockFetch.mockResolvedValueOnce(ONE_TASK).mockRejectedValueOnce(new Error('network blip'));
    renderInbox();
    await screen.findByText('Review Expense Claim');

    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(screen.getByText('Review Expense Claim')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not start a poll while the previous request is still in flight', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockFetch.mockResolvedValueOnce(ONE_TASK).mockReturnValueOnce(new Promise(() => {}));
    renderInbox();
    await screen.findByText('Review Expense Claim');

    await act(() => vi.advanceTimersByTimeAsync(30_000)); // poll 1 hangs
    await act(() => vi.advanceTimersByTimeAsync(30_000)); // poll 2 skipped
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});
