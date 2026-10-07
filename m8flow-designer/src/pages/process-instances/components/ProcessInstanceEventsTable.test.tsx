import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ProcessInstanceEventRow } from '@/lib/processInstancesApi';
import { ProcessInstanceEventsTable } from './ProcessInstanceEventsTable';

const rows: ProcessInstanceEventRow[] = [
  {
    id: 1163,
    task_guid: null,
    bpmn_process: 'Process_approval',
    task_name: null,
    task_identifier: 'Event_0jqbb0y',
    task_type: 'StartEvent',
    event_type: 'process_instance_created',
    user: 'system',
    occurred_at: new Date(1_783_380_927 * 1000).toISOString(),
    error_message: null,
  },
  {
    id: 1162,
    task_guid: null,
    bpmn_process: 'Process_approval',
    task_name: 'Start',
    task_identifier: null,
    task_type: 'BpmnStartTask',
    event_type: 'task_completed',
    user: 'system',
    occurred_at: new Date(1_783_380_927 * 1000).toISOString(),
    error_message: null,
  },
];

describe('ProcessInstanceEventsTable', () => {
  it('renders mockup columns, em-dash for missing BPMN cells, and no link for instance-level events', () => {
    render(
      <MemoryRouter>
        <ProcessInstanceEventsTable instanceId={7} events={rows} />
      </MemoryRouter>,
    );

    expect(screen.getByText('ID')).toBeInTheDocument();
    expect(screen.getByText('Bpmn process')).toBeInTheDocument();
    expect(screen.getByText('Task identifier')).toBeInTheDocument();
    expect(screen.getByText('Event_0jqbb0y')).toBeInTheDocument();
    expect(screen.getByText('StartEvent')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('system')).toHaveLength(2);

    const stamp = screen.getAllByText('2026-07-06 23:35:27');
    expect(stamp.length).toBeGreaterThan(0);
    expect(stamp[0].closest('a')).toBeNull();
    const eventPill = screen
      .getByText('process_instance_created')
      .closest('[data-slot="pill"]');
    expect(eventPill).toHaveClass('min-w-0', 'max-w-full', 'whitespace-normal');
    expect(screen.getByText('process_instance_created')).toHaveClass('break-all');
  });

  it('renders headers with no rows when the event list is empty', () => {
    render(
      <MemoryRouter>
        <ProcessInstanceEventsTable instanceId={7} events={[]} />
      </MemoryRouter>,
    );
    expect(screen.getByText('Event type')).toBeInTheDocument();
    expect(screen.queryByText('Loading events…')).not.toBeInTheDocument();
  });
});

const failedAndLinked: ProcessInstanceEventRow[] = [
  {
    id: null,
    task_guid: 'g-script',
    bpmn_process: 'Process_approval',
    task_name: 'Compute total',
    task_identifier: 'Script_1',
    task_type: 'ScriptTask',
    event_type: 'task_completed',
    user: 'system',
    occurred_at: new Date(1_783_380_930 * 1000).toISOString(),
    error_message: null,
  },
  {
    id: 1170,
    task_guid: 'g-service',
    bpmn_process: 'Process_approval',
    task_name: 'Call ERP',
    task_identifier: 'Service_1',
    task_type: 'ServiceTask',
    event_type: 'task_failed',
    user: 'system',
    occurred_at: new Date(1_783_380_931 * 1000).toISOString(),
    error_message: 'proxy said 502 Bad Gateway',
  },
];

describe('ProcessInstanceEventsTable failures, links and filters', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('links task timestamps to the time-travel view', () => {
    render(
      <MemoryRouter>
        <ProcessInstanceEventsTable instanceId={7} events={failedAndLinked} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: '2026-07-06 23:35:30' })).toHaveAttribute(
      'href',
      '/?to_task_guid=g-script',
    );
  });

  it('flags failed events and opens their error details', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ProcessInstanceEventsTable instanceId={7} events={failedAndLinked} />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: /task_failed/ }));

    expect(await screen.findByText('Event error details')).toBeInTheDocument();
    expect(screen.getByText('proxy said 502 Bad Gateway')).toBeInTheDocument();
    expect(screen.getAllByText('Call ERP').length).toBeGreaterThan(0);
  });

  it('refetches with the chosen event type and resets to page 1', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        results: failedAndLinked,
        pagination: { count: 2, total: 2, pages: 1 },
        filter_options: { event_types: ['task_completed', 'task_failed'], task_types: ['ScriptTask', 'ServiceTask'] },
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter>
        <ProcessInstanceEventsTable instanceId={7} tenantId="t1" />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: /^Event type:/ }));
    await user.click(await screen.findByRole('menuitemradio', { name: 'task_failed' }));

    await waitFor(() =>
      expect(String(fetchMock.mock.calls[fetchMock.mock.calls.length - 1]?.[0])).toContain('event_type=task_failed&page=1&per_page=50'),
    );
  });
});
