import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ProcessInstanceEventRow } from '@/lib/processInstancesApi';
import { ProcessInstanceEventsTable } from './ProcessInstanceEventsTable';

const rows: ProcessInstanceEventRow[] = [
  {
    id: 1163,
    bpmn_process: 'Process_approval',
    task_name: null,
    task_identifier: 'Event_0jqbb0y',
    task_type: 'StartEvent',
    event_type: 'task_completed',
    user: 'system',
    timestamp: 1_783_380_927,
  },
  {
    id: 1162,
    bpmn_process: 'Process_approval',
    task_name: 'Start',
    task_identifier: null,
    task_type: 'BpmnStartTask',
    event_type: 'task_completed',
    user: 'system',
    timestamp: 1_783_380_927,
  },
];

describe('ProcessInstanceEventsTable', () => {
  it('renders mockup columns, em-dash for missing BPMN cells, and a non-link timestamp', () => {
    render(<ProcessInstanceEventsTable instanceId={7} events={rows} />);

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
  });

  it('renders headers with no rows when the event list is empty', () => {
    render(<ProcessInstanceEventsTable instanceId={7} events={[]} />);
    expect(screen.getByText('Event type')).toBeInTheDocument();
    expect(screen.queryByText('Loading events…')).not.toBeInTheDocument();
  });
});
