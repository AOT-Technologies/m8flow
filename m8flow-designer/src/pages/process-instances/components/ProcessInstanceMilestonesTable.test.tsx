import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ProcessInstanceMilestonesTable } from './ProcessInstanceMilestonesTable';

describe('ProcessInstanceMilestonesTable', () => {
  it('renders one current row and a non-link timestamp', () => {
    render(
      <ProcessInstanceMilestonesTable
        instanceId={7}
        milestones={[
          {
            milestone: 'Invoice Approval',
            bpmn_process: 'Process_approval',
            timestamp: 1_783_380_927,
          },
        ]}
      />,
    );

    expect(screen.getByText('Milestone')).toBeInTheDocument();
    expect(screen.getByText('Invoice Approval')).toBeInTheDocument();
    expect(screen.getByText('Process_approval')).toBeInTheDocument();
    const stamp = screen.getByText('2026-07-06 23:35:27');
    expect(stamp.closest('a')).toBeNull();
  });

  it('renders headers with no rows when there is no last milestone', () => {
    render(<ProcessInstanceMilestonesTable instanceId={7} milestones={[]} />);
    expect(screen.getByText('Bpmn process')).toBeInTheDocument();
    expect(screen.queryByText('Loading milestones…')).not.toBeInTheDocument();
    expect(screen.queryByText('Invoice Approval')).not.toBeInTheDocument();
  });
});
