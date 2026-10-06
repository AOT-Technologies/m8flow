import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import type { ProcessInstancePendingTaskRow } from '@/lib/processInstancesApi';
import { ProcessInstanceCompletableTasksTable } from './ProcessInstanceCompletableTasksTable';

const mine: ProcessInstancePendingTaskRow = {
  id: 42,
  task_title: 'Submit Expense Claim',
  task_name: 'submit_claim',
  lane_name: 'Submitter',
  can_complete: true,
  waiting_for: { type: 'group', label: 'Submitter', usernames: ['Asha', 'Ravi'] },
};

const theirs: ProcessInstancePendingTaskRow = {
  id: 43,
  task_title: null,
  task_name: 'manager_review',
  lane_name: null,
  can_complete: false,
  waiting_for: { type: 'initiator', label: 'admin', usernames: ['admin'] },
};

function renderTable(tasks: ProcessInstancePendingTaskRow[]) {
  return render(
    <MemoryRouter>
      <ProcessInstanceCompletableTasksTable instanceId={7} tasks={tasks} />
    </MemoryRouter>,
  );
}

describe('ProcessInstanceCompletableTasksTable', () => {
  it('lists every open task with Waiting for, Go only where the user can complete', () => {
    renderTable([mine, theirs]);

    expect(screen.getByRole('heading', { name: 'Open tasks' })).toBeInTheDocument();
    expect(screen.getByText('Submit Expense Claim')).toBeInTheDocument();
    expect(screen.getByText('manager_review')).toBeInTheDocument();
    expect(screen.getByText('Group: Submitter')).toHaveAttribute('title', 'Asha, Ravi');
    expect(screen.getByText('admin (initiator)')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Go' })).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'Go' })).toHaveAttribute('href', '/task-review/42');
    expect(screen.queryByText('No tasks are currently assigned to you.')).not.toBeInTheDocument();
  });

  it('says so when none of the open tasks are assigned to the user', () => {
    renderTable([theirs]);
    expect(screen.getByText('No tasks are currently assigned to you.')).toBeInTheDocument();
    expect(screen.getByText('manager_review')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Go' })).not.toBeInTheDocument();
  });

  it('falls back to lane, then em-dash, without waiting_for', () => {
    renderTable([
      { ...mine, waiting_for: null },
      { ...theirs, waiting_for: null },
    ]);
    expect(screen.getByText('Submitter')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('shows an empty message when the instance has no open tasks', () => {
    renderTable([]);
    expect(screen.getByText('No open tasks on this instance.')).toBeInTheDocument();
    expect(screen.queryByText('Waiting for')).not.toBeInTheDocument();
    expect(screen.queryByText('Loading tasks…')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Go' })).not.toBeInTheDocument();
  });
});
