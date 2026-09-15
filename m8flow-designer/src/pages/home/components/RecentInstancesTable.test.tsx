import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { RecentInstancesTable } from './RecentInstancesTable';

describe('RecentInstancesTable', () => {
  it('renders provided rows with status pills and relative started times', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    render(
      <MemoryRouter>
        <RecentInstancesTable
          rows={[
            {
              id: 721,
              tenant_id: 't1',
              tenant_name: 'aot-demo',
              process_model_display_name: 'Single Approval test',
              start_in_seconds: nowSec - 2 * 3600,
              status: 'complete',
            },
            {
              id: 720,
              tenant_id: 't1',
              tenant_name: 'aot-demo',
              process_model_display_name: 'Invoice payment',
              start_in_seconds: nowSec - 3 * 3600,
              status: 'error',
            },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('Recent process instances')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View all' })).toHaveAttribute(
      'href',
      '/process-instances',
    );
    expect(screen.getByText('721')).toBeInTheDocument();
    expect(screen.getByText('Single Approval test')).toBeInTheDocument();
    expect(screen.getByText('Complete')).toBeInTheDocument();
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('2h ago')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open instance 721' })).toHaveAttribute(
      'href',
      '/process-instances/721',
    );
  });

  it('shows empty copy when there are no rows', () => {
    render(
      <MemoryRouter>
        <RecentInstancesTable rows={[]} />
      </MemoryRouter>,
    );
    expect(screen.getByText('No recent process instances.')).toBeInTheDocument();
  });
});
