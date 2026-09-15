import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { ProcessInstanceCompletedTasksResponse } from '@/lib/processInstancesApi';
import { ProcessInstanceCompletedTasksTable } from './ProcessInstanceCompletedTasksTable';

const data: ProcessInstanceCompletedTasksResponse = {
  completed_by_me: [],
  all_completed: [
    {
      id: 42,
      task_title: 'Submit Expense Claim',
      task_name: 'submit_claim',
      completed_by: 'editor',
      timestamp: 1_783_380_927,
    },
    {
      id: 43,
      task_title: null,
      task_name: 'manager_review',
      completed_by: null,
      timestamp: null,
    },
  ],
};

const mine: ProcessInstanceCompletedTasksResponse = {
  completed_by_me: [
    {
      id: 42,
      task_title: 'Submit Expense Claim',
      task_name: 'submit_claim',
      completed_by: 'Priya Nair',
      timestamp: 1_783_380_927,
    },
  ],
  all_completed: [
    {
      id: 42,
      task_title: 'Submit Expense Claim',
      task_name: 'submit_claim',
      completed_by: 'Priya Nair',
      timestamp: 1_783_380_927,
    },
  ],
};

describe('ProcessInstanceCompletedTasksTable', () => {
  it('shows mockup empty copy on Completed by me when the caller has no rows', () => {
    render(<ProcessInstanceCompletedTasksTable instanceId={7} data={data} />);

    expect(screen.getByText('Completed by me')).toBeInTheDocument();
    expect(
      screen.getByText('You have not completed any tasks for this process instance.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Submit Expense Claim')).not.toBeInTheDocument();
    expect(screen.queryByText('Task')).not.toBeInTheDocument();
  });

  it('shows title, completer person, and UTC timestamp on All completed — not task_name as Task', async () => {
    // Radix's Tabs, like its DropdownMenu, doesn't switch under a plain
    // fireEvent.click in jsdom — use @testing-library/user-event, per the
    // map's Notes.
    const user = userEvent.setup();
    render(<ProcessInstanceCompletedTasksTable instanceId={7} data={data} />);

    await user.click(screen.getByRole('tab', { name: 'All completed' }));

    expect(screen.getByText('Task')).toBeInTheDocument();
    expect(screen.getByText('Submit Expense Claim')).toBeInTheDocument();
    expect(screen.queryByText('submit_claim')).not.toBeInTheDocument();
    expect(screen.getByText('editor')).toBeInTheDocument();
    expect(screen.getByText('manager_review')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2);

    const stamp = screen.getByText('2026-07-06 23:35:27');
    expect(stamp.closest('a')).toBeNull();
    expect(
      screen.queryByText('You have not completed any tasks for this process instance.'),
    ).not.toBeInTheDocument();
  });

  it('shows the caller row on Completed by me when they have completed a task', () => {
    render(<ProcessInstanceCompletedTasksTable instanceId={7} data={mine} />);

    expect(screen.getByText('Submit Expense Claim')).toBeInTheDocument();
    expect(screen.getByText('Priya Nair')).toBeInTheDocument();
    expect(
      screen.queryByText('You have not completed any tasks for this process instance.'),
    ).not.toBeInTheDocument();
  });

  it('renders headers with no rows on All completed when that list is empty', async () => {
    const user = userEvent.setup();
    render(
      <ProcessInstanceCompletedTasksTable
        instanceId={7}
        data={{ completed_by_me: [], all_completed: [] }}
      />,
    );

    await user.click(screen.getByRole('tab', { name: 'All completed' }));

    expect(screen.getByText('Task')).toBeInTheDocument();
    expect(screen.getByText('Completed by')).toBeInTheDocument();
    expect(screen.queryByText('Loading tasks…')).not.toBeInTheDocument();
    expect(
      screen.queryByText('You have not completed any tasks for this process instance.'),
    ).not.toBeInTheDocument();
  });
});
