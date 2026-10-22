import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { capabilitiesFromContext } from '@/components/session/testSupport';
import { ApiError } from '@/lib/api';
import { chooseOption } from '@/test/chooseOption';

const mockUseCapabilities = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useCapabilities: () => mockUseCapabilities(),
}));

const api = {
  fetchCeleryOverview: vi.fn(),
  fetchCeleryWorkers: vi.fn(),
  fetchCeleryTasks: vi.fn(),
  fetchCeleryHistory: vi.fn(),
  fetchCeleryHistoryTask: vi.fn(),
  fetchCeleryTaskTypes: vi.fn(),
  revokeCeleryTask: vi.fn(),
  setCeleryRateLimit: vi.fn(),
  setCeleryTimeLimit: vi.fn(),
  sendCeleryWorkerAction: vi.fn(),
};
vi.mock('@/lib/celeryApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/celeryApi')>('@/lib/celeryApi');
  return {
    ...actual,
    fetchCeleryOverview: () => api.fetchCeleryOverview(),
    fetchCeleryWorkers: () => api.fetchCeleryWorkers(),
    fetchCeleryTasks: () => api.fetchCeleryTasks(),
    fetchCeleryHistory: (...args: unknown[]) => api.fetchCeleryHistory(...args),
    fetchCeleryHistoryTask: (...args: unknown[]) => api.fetchCeleryHistoryTask(...args),
    fetchCeleryTaskTypes: (...args: unknown[]) => api.fetchCeleryTaskTypes(...args),
    revokeCeleryTask: (...args: unknown[]) => api.revokeCeleryTask(...args),
    setCeleryRateLimit: (...args: unknown[]) => api.setCeleryRateLimit(...args),
    setCeleryTimeLimit: (...args: unknown[]) => api.setCeleryTimeLimit(...args),
    sendCeleryWorkerAction: (...args: unknown[]) => api.sendCeleryWorkerAction(...args),
  };
});

import CeleryMonitorPage from './CeleryMonitorPage';

const POLL = 'm8flow_backend.scheduler.poll_due_task';
const WORKER_NAME = 'celery@worker-1';

const OVERVIEW = {
  workersOnline: 1,
  workersOffline: 1,
  concurrency: 2,
  tasksRunning: 1,
  tasksReserved: 1,
  tasksScheduled: 0,
  tasksProcessed: 3311,
  queues: [
    { name: 'celery', messages: 4, consumers: [WORKER_NAME] },
    { name: 'orphaned', messages: 2, consumers: [] },
  ],
  unacked: 3,
  history: { windowHours: 24, succeeded: 128, failed: 7, retried: 2, revoked: 0 },
  historyEnabled: true,
  controlEnabled: true,
  transport: 'redis',
  capturedAt: '2026-10-21T10:15:00+00:00',
};

const WORKERS = [
  {
    name: WORKER_NAME,
    online: true,
    lastSeenAt: OVERVIEW.capturedAt,
    pid: 1,
    uptimeSeconds: 84292,
    pool: 'prefork',
    concurrency: 2,
    processes: 2,
    maxTasksPerChild: null,
    softTimeLimitSeconds: null,
    hardTimeLimitSeconds: null,
    autoscaleMin: 2,
    autoscaleMax: 4,
    prefetchCount: 8,
    tasksProcessed: 3311,
    tasksProcessedByName: { [POLL]: 3311 },
    queues: ['celery'],
    registeredTasks: [POLL],
    running: 1,
    reserved: 1,
    scheduled: 0,
    system: { maxrss: 92160, utime: 12.5 },
    conf: [{ key: 'broker_url', value: 'redis://:***@redis:6379/0' }],
  },
  { name: 'celery@gone', online: false, lastSeenAt: '2026-10-20T09:00:00+00:00' },
];

const live = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  name: POLL,
  worker: WORKER_NAME,
  queue: 'celery',
  startedAt: '2026-10-21T10:14:58+00:00',
  eta: null,
  acknowledged: true,
  revoked: false,
  args: '[]',
  kwargs: '{}',
  ...extra,
});

const TASKS = {
  active: [live('running-1', { kwargs: '{"process_instance_id": 42}' })],
  reserved: [live('waiting-1', { startedAt: null, revoked: true, kwargs: '{"api_key": "[redacted]"}' })],
  scheduled: [],
  revoked: ['waiting-1'],
  capturedAt: OVERVIEW.capturedAt,
};

const historyRow = (taskId: string, state: string, extra: Record<string, unknown> = {}) => ({
  taskId,
  name: POLL,
  state,
  worker: WORKER_NAME,
  queue: 'celery',
  tenantId: null,
  args: '[]',
  kwargs: '{}',
  retries: 0,
  receivedAt: '2026-10-21T10:00:00+00:00',
  startedAt: '2026-10-21T10:00:00+00:00',
  finishedAt: '2026-10-21T10:00:01+00:00',
  runtimeSeconds: 0.004,
  updatedAt: '2026-10-21T10:00:01+00:00',
  exception: null,
  ...extra,
});

const HISTORY = {
  results: [historyRow('done-1', 'SUCCESS'), historyRow('failed-1', 'FAILURE', { exception: "ValueError('boom')" })],
  pagination: { page: 1, perPage: 25, total: 2, pages: 1 },
};

const TASK_TYPES = [
  {
    name: POLL,
    total: 130,
    succeeded: 128,
    failed: 2,
    retried: 0,
    revoked: 0,
    running: 0,
    avgRuntimeSeconds: 0.004,
    maxRuntimeSeconds: 1.5,
    lastSeenAt: '2026-10-21T10:00:01+00:00',
  },
];

const OK = { ok: true, message: 'Done here.', results: [{ worker: WORKER_NAME, ok: true, message: 'Done here.' }] };

function renderPage({ read = true, manage = true, path = '/system/celery' } = {}) {
  mockUseCapabilities.mockReturnValue(
    capabilitiesFromContext({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: read,
      canReadCeleryMonitoring: read,
      canManageCelery: manage,
    }),
  );
  return render(
    <MemoryRouter initialEntries={[path]}>
      <CeleryMonitorPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  api.fetchCeleryOverview.mockResolvedValue(OVERVIEW);
  api.fetchCeleryWorkers.mockResolvedValue(WORKERS);
  api.fetchCeleryTasks.mockResolvedValue(TASKS);
  api.fetchCeleryHistory.mockResolvedValue(HISTORY);
  api.fetchCeleryHistoryTask.mockResolvedValue(
    historyRow('running-1', 'STARTED', { result: null, traceback: null, kwargs: '{"process_instance_id": 42}' }),
  );
  api.fetchCeleryTaskTypes.mockResolvedValue(TASK_TYPES);
  api.revokeCeleryTask.mockResolvedValue(OK);
  api.setCeleryRateLimit.mockResolvedValue(OK);
  api.setCeleryTimeLimit.mockResolvedValue(OK);
  api.sendCeleryWorkerAction.mockResolvedValue(OK);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('CeleryMonitorPage', () => {
  it('shows a loader until the first snapshot arrives', async () => {
    let resolveOverview: (value: typeof OVERVIEW) => void = () => {};
    api.fetchCeleryOverview.mockReturnValue(new Promise((resolve) => (resolveOverview = resolve)));
    renderPage();

    expect(screen.getByRole('status', { name: 'Loading Celery…' })).toBeInTheDocument();
    resolveOverview(OVERVIEW);
    expect(await screen.findByText('running-1')).toBeInTheDocument();
    expect(screen.queryByRole('status', { name: 'Loading Celery…' })).not.toBeInTheDocument();
  });

  it('opens on the dashboard: live numbers, last-24-hour outcomes and live tasks', async () => {
    renderPage();

    expect(await screen.findByText('Connected')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTitle(/no longer answer/)).toHaveTextContent('1');
    expect(screen.getByText('Succeeded').parentElement).toHaveTextContent('128');
    expect(screen.getByText('Failed').parentElement).toHaveTextContent('7');
    expect(screen.getByTitle(/waiting in the broker/)).toHaveTextContent('6');
    expect(screen.getByText('{"process_instance_id": 42}')).toBeInTheDocument();
    expect(screen.getByText('{"api_key": "[redacted]"}')).toBeInTheDocument();
  });

  it('warns when no worker is online', async () => {
    api.fetchCeleryOverview.mockResolvedValue({ ...OVERVIEW, workersOnline: 0 });
    renderPage();
    expect(await screen.findByText(/No Celery worker is online/)).toBeInTheDocument();
  });

  it('shows Disconnected with the server message when the broker is unreachable', async () => {
    api.fetchCeleryOverview.mockRejectedValue(
      new ApiError('/v1.0/m8flow/celery/overview', 503, 'GET', 'The Celery broker is not reachable.'),
    );
    renderPage();

    expect(await screen.findByText('Disconnected')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Celery unavailable. The Celery broker is not reachable.');
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
  });

  it('keeps the last snapshot on screen while refreshing', async () => {
    renderPage();
    expect(await screen.findByText('running-1')).toBeInTheDocument();

    api.fetchCeleryOverview.mockReturnValue(new Promise(() => {}));
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(screen.getByText('running-1')).toBeInTheDocument();
  });

  it('does not call the API without the backend read permission', () => {
    renderPage({ read: false });
    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(api.fetchCeleryOverview).not.toHaveBeenCalled();
  });

  it('revokes a live task after confirmation', async () => {
    renderPage();
    const row = (await screen.findByText('running-1')).closest('[role="row"]') as HTMLElement;
    await userEvent.click(within(row).getByRole('button', { name: 'Terminate' }));
    await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Terminate' }));

    await waitFor(() => expect(api.revokeCeleryTask).toHaveBeenCalledWith({ taskId: 'running-1', terminate: true }));
    expect(await screen.findByText('Done here.')).toBeInTheDocument();
  });

  it('offers no control actions without the manage permission', async () => {
    renderPage({ manage: false });
    expect(await screen.findByText('running-1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Revoke' })).not.toBeInTheDocument();
  });

  it('offers no control actions when the backend turned them off', async () => {
    api.fetchCeleryOverview.mockResolvedValue({ ...OVERVIEW, controlEnabled: false });
    renderPage();
    expect(await screen.findByText('running-1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Revoke' })).not.toBeInTheDocument();
  });

  it('lists online and offline workers and opens a worker', async () => {
    renderPage({ path: '/system/celery?tab=workers' });

    expect(await screen.findByText('celery@gone')).toBeInTheDocument();
    expect(screen.getAllByText('Offline').length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole('button', { name: WORKER_NAME }));

    expect(await screen.findByText('Pool and limits')).toBeInTheDocument();
    expect(screen.getByText('2 – 4')).toBeInTheDocument();
    expect(screen.getByText('redis://:***@redis:6379/0')).toBeInTheDocument();
    expect(screen.getByText('maxrss')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Shut down' })).toBeInTheDocument();
  });

  it('offers autoscale, not grow or shrink, on an autoscaled worker', async () => {
    renderPage({ path: `/system/celery?tab=workers&worker=${encodeURIComponent(WORKER_NAME)}` });
    expect(await screen.findByRole('button', { name: 'Autoscale' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Grow pool' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Shrink pool' })).not.toBeInTheDocument();
  });

  it('grows the pool and shuts a worker down from its page', async () => {
    api.fetchCeleryWorkers.mockResolvedValue([{ ...WORKERS[0], autoscaleMin: null, autoscaleMax: null }, WORKERS[1]]);
    renderPage({ path: `/system/celery?tab=workers&worker=${encodeURIComponent(WORKER_NAME)}` });

    await userEvent.click(await screen.findByRole('button', { name: 'Grow pool' }));
    const grow = screen.getByRole('dialog');
    await userEvent.click(within(grow).getByRole('button', { name: 'Grow pool' }));
    await waitFor(() => expect(api.sendCeleryWorkerAction).toHaveBeenCalledWith(WORKER_NAME, { action: 'pool_grow', n: 1 }));

    await userEvent.click(screen.getByRole('button', { name: 'Shut down' }));
    await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Shut down' }));
    await waitFor(() => expect(api.sendCeleryWorkerAction).toHaveBeenCalledWith(WORKER_NAME, { action: 'shutdown' }));
  });

  it('shows an offline worker without controls', async () => {
    renderPage({ path: '/system/celery?tab=workers&worker=celery%40gone' });
    expect(await screen.findByText(/no longer answers/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Shut down' })).not.toBeInTheDocument();
  });

  it('lists task history and filters it by state', async () => {
    renderPage({ path: '/system/celery?tab=tasks' });

    expect(await screen.findByText('done-1')).toBeInTheDocument();
    expect(screen.getByText("ValueError('boom')")).toBeInTheDocument();
    expect(api.fetchCeleryHistory).toHaveBeenLastCalledWith(expect.objectContaining({ state: null, windowHours: 24, page: 1 }));

    await chooseOption(screen.getByRole('combobox', { name: 'State' }), 'Failed');
    await waitFor(() => expect(api.fetchCeleryHistory).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'FAILURE' })));
  });

  it('explains when task history is turned off', async () => {
    api.fetchCeleryOverview.mockResolvedValue({ ...OVERVIEW, historyEnabled: false });
    renderPage({ path: '/system/celery?tab=tasks' });
    expect(await screen.findByText(/Task history is turned off/)).toBeInTheDocument();
    expect(api.fetchCeleryHistory).not.toHaveBeenCalled();
  });

  it('opens a task and revokes it from its details', async () => {
    renderPage({ path: '/system/celery?task=running-1' });

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('{"process_instance_id": 42}')).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Revoke' }));
    await userEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Revoke' }));
    await waitFor(() => expect(api.revokeCeleryTask).toHaveBeenCalledWith({ taskId: 'running-1', terminate: false }));
  });

  it('says so when a task was not recorded', async () => {
    api.fetchCeleryHistoryTask.mockRejectedValue(new ApiError('/v1.0/m8flow/celery/history/x', 404));
    renderPage({ path: '/system/celery?task=x' });
    expect(await screen.findByText('This task was not recorded in the task history.')).toBeInTheDocument();
  });

  it('shows task types and sets a rate limit, keeping a bad value in the dialog', async () => {
    renderPage({ path: '/system/celery?tab=taskTypes' });

    expect(await screen.findByText(POLL)).toBeInTheDocument();
    expect(screen.getByText('1.50 s')).toBeInTheDocument();

    api.setCeleryRateLimit.mockRejectedValueOnce(
      new ApiError('/v1.0/m8flow/celery/control/rate-limit', 400, 'POST', "'rateLimit' must look like 10, 10/s, 10/m or 10/h."),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Rate limit' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByRole('textbox'), 'fast');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    expect(await within(dialog).findByText(/must look like/)).toBeInTheDocument();

    await userEvent.clear(within(dialog).getByRole('textbox'));
    await userEvent.type(within(dialog).getByRole('textbox'), '10/m');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(api.setCeleryRateLimit).toHaveBeenLastCalledWith(POLL, '10/m'));
  });

  it('shows queues, their consumers and unacknowledged messages', async () => {
    renderPage({ path: '/system/celery?tab=broker' });

    expect(await screen.findByText('orphaned')).toBeInTheDocument();
    expect(screen.getByText('No worker consumes this queue')).toBeInTheDocument();
    expect(screen.getByTitle(/not yet acknowledged/)).toHaveTextContent('3');
  });
});
