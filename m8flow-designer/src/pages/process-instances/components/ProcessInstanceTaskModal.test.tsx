import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ProcessInstanceTaskState } from '@/lib/processInstancesApi';
import { ProcessInstanceTaskModal } from './ProcessInstanceTaskModal';

const scriptTask: ProcessInstanceTaskState = {
  guid: 'g-script',
  bpmn_identifier: 'Script_1',
  bpmn_name: 'Compute total',
  typename: 'ScriptTask',
  state: 'COMPLETED',
  last_state_change: 101.5,
};

/** Answers the permissions-check POST for task-data, and the task GET. */
function stubFetch({ canReadData = true, data = { invoice_total: 1250 } as Record<string, unknown> } = {}) {
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<unknown>>((url) => {
    if (String(url).includes('/permissions-check')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ results: { '/v1.0/task-data/7': { GET: canReadData } } }),
      });
    }
    return Promise.resolve({ ok: true, json: async () => ({ ...scriptTask, data }) });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function taskCalls(fetchMock: ReturnType<typeof stubFetch>) {
  return fetchMock.mock.calls.filter(([url]) => String(url).includes('/tasks/'));
}

describe('ProcessInstanceTaskModal', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows task identity and its data as formatted JSON', async () => {
    const fetchMock = stubFetch();

    render(
      <MemoryRouter>
        <ProcessInstanceTaskModal instanceId={7} tenantId="t1" task={scriptTask} onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(screen.getByText('Compute total (ScriptTask)')).toBeInTheDocument();
    expect(screen.getByText('g-script')).toBeInTheDocument();
    expect(await screen.findByText(/"invoice_total": 1250/)).toBeInTheDocument();
    expect(String(taskCalls(fetchMock)[0][0])).toContain('/process-instances/7/tasks/g-script?tenantId=t1');
    expect(
      screen.getByRole('link', { name: 'View process instance at the time when this task was active' }),
    ).toHaveAttribute('href', '/?to_task_guid=g-script');
  });

  it('shows no task data, and does not fetch it, without the task-data permission', async () => {
    const fetchMock = stubFetch({ canReadData: false });

    render(
      <MemoryRouter>
        <ProcessInstanceTaskModal instanceId={7} tenantId="t1" task={scriptTask} onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(await screen.findByText("You don't have permission to view this task's data.")).toBeInTheDocument();
    expect(screen.getByText('g-script')).toBeInTheDocument();
    expect(taskCalls(fetchMock)).toHaveLength(0);
    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).includes('/permissions-check'))!;
    expect(JSON.parse(String(init?.body))).toEqual({
      requests_to_check: { '/v1.0/task-data/7': ['GET'] },
    });
    // Time travel needs only instance read.
    expect(screen.getByRole('link', { name: /at the time/ })).toBeInTheDocument();
  });

  it('says no data was recorded instead of showing an empty object', async () => {
    // e.g. a start event: nothing was in scope yet.
    stubFetch({ data: {} });

    render(
      <MemoryRouter>
        <ProcessInstanceTaskModal instanceId={7} tenantId="t1" task={scriptTask} onClose={() => {}} />
      </MemoryRouter>,
    );

    expect(await screen.findByText('No data recorded for this task.')).toBeInTheDocument();
    expect(screen.queryByText('{}')).not.toBeInTheDocument();
  });

  it('offers no time-travel link for a task that has not finished', () => {
    stubFetch();

    render(
      <MemoryRouter>
        <ProcessInstanceTaskModal
          instanceId={7}
          task={{ ...scriptTask, state: 'READY' }}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('link', { name: /at the time/ })).not.toBeInTheDocument();
  });
});
