import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import type { ProcessInstanceCompletableTaskRow } from '@/lib/processInstancesApi';
import { ProcessInstanceCompletableTasksTable } from './ProcessInstanceCompletableTasksTable';

const rows: ProcessInstanceCompletableTaskRow[] = [
  {
    id: 42,
    task_title: 'Submit Expense Claim',
    task_name: 'submit_claim',
    lane_name: 'Submitter',
  },
  {
    id: 43,
    task_title: null,
    task_name: 'manager_review',
    lane_name: null,
  },
];

function renderTable(tasks: ProcessInstanceCompletableTaskRow[]) {
  return render(
    <MemoryRouter>
      <ProcessInstanceCompletableTasksTable instanceId={7} tasks={tasks} />
    </MemoryRouter>,
  );
}

describe('ProcessInstanceCompletableTasksTable', () => {
  it('shows title, lane as Waiting for, and Go to Task Review', () => {
    renderTable([rows[0]]);

    expect(screen.getByRole('heading', { name: 'Tasks I can complete' })).toBeInTheDocument();
    expect(screen.getByText('Submit Expense Claim')).toBeInTheDocument();
    expect(screen.queryByText('submit_claim')).not.toBeInTheDocument();
    expect(screen.getByText('Submitter')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go' })).toHaveAttribute('href', '/task-review/42');
  });

  it('falls back to task_name and em-dash when title and lane are missing', () => {
    renderTable(rows);

    expect(screen.getByText('manager_review')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Go' })[1]).toHaveAttribute(
      'href',
      '/task-review/43',
    );
  });

  it('renders headers with no rows when the list is empty', () => {
    renderTable([]);
    expect(screen.getByText('Waiting for')).toBeInTheDocument();
    expect(screen.queryByText('Loading tasks…')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Go' })).not.toBeInTheDocument();
  });
});
