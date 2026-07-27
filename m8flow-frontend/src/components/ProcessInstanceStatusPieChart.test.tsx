import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProcessInstanceStatusPieChart from './ProcessInstanceStatusPieChart';

// Deterministic status list so the test does not depend on the upstream config module.
vi.mock('../config', () => ({
  PROCESS_STATUSES: [
    'complete',
    'error',
    'not_started',
    'running',
    'suspended',
    'terminated',
    'user_input_required',
    'waiting',
  ],
}));

vi.mock('../helpers', () => ({
  getProcessStatus: (status: string) => status,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: any) => opts?.defaultValue ?? key,
    i18n: {},
  }),
}));

// Return a per-status total based on the process_status filter in the request body.
const COUNTS: { [status: string]: number } = {
  complete: 5,
  error: 2,
  running: 3,
};

// Default: return a per-status total based on the process_status filter.
const defaultImpl = (opts: any) => {
  const filterBy = opts?.postBody?.report_metadata?.filter_by || [];
  const statusFilter = filterBy.find(
    (f: any) => f.field_name === 'process_status',
  );
  const status = statusFilter?.field_value;
  // A process_model_identifier constraint in the base filters simulates "no matches".
  const hasModelConstraint = filterBy.some(
    (f: any) => f.field_name === 'process_model_identifier',
  );
  const total = hasModelConstraint ? 0 : COUNTS[status] || 0;
  opts.successCallback({ pagination: { total }, results: [] });
};

const makeCallToBackend = vi.fn(defaultImpl);

vi.mock('../services/HttpService', () => ({
  default: {
    makeCallToBackend: (opts: any) => makeCallToBackend(opts),
  },
}));

const reportMetadata = { columns: [], filter_by: [], order_by: [] } as any;

describe('ProcessInstanceStatusPieChart', () => {
  afterEach(() => {
    vi.clearAllMocks();
    // clearAllMocks resets call history but not the implementation, so restore
    // the default so a test that overrides it does not leak into later tests.
    makeCallToBackend.mockImplementation(defaultImpl);
  });

  it('renders the total and one legend row per non-zero status', async () => {
    render(
      <ProcessInstanceStatusPieChart
        variant="all"
        reportMetadata={reportMetadata}
      />,
    );

    // Total (5 + 2 + 3) shown in the donut center.
    expect(await screen.findByText('10')).toBeInTheDocument();

    // Only statuses with counts > 0 appear in the legend.
    expect(screen.getByText('complete')).toBeInTheDocument();
    expect(screen.getByText('error')).toBeInTheDocument();
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(screen.queryByText('waiting')).not.toBeInTheDocument();
    expect(screen.queryByText('not_started')).not.toBeInTheDocument();

    // One count query per status in the config list.
    expect(makeCallToBackend).toHaveBeenCalledTimes(8);
    // Counts are queried against the "all" list endpoint.
    expect(makeCallToBackend.mock.calls[0][0].path).toContain(
      '/process-instances?per_page=1',
    );
  });

  it('fires onStatusClick when a legend row is clicked', async () => {
    const onStatusClick = vi.fn();
    render(
      <ProcessInstanceStatusPieChart
        variant="all"
        reportMetadata={reportMetadata}
        onStatusClick={onStatusClick}
      />,
    );

    // Select the legend control by role/name so the assertion is stable even
    // if the status label text appears elsewhere on the page later.
    await screen.findByText('error');
    fireEvent.click(screen.getByRole('button', { name: /error/i }));
    expect(onStatusClick).toHaveBeenCalledWith('error');
  });

  it('forwards non-status base filters verbatim to each count query', async () => {
    render(
      <ProcessInstanceStatusPieChart
        variant="all"
        reportMetadata={
          {
            columns: [],
            filter_by: [
              // a non-status filter with a non-equals operator must be preserved
              {
                field_name: 'start_from',
                field_value: '123',
                operator: 'greater_than',
              },
              // an incoming process_status filter must be stripped (the chart
              // shows the full distribution, adding its own per-status equals)
              {
                field_name: 'process_status',
                field_value: 'complete',
                operator: 'equals',
              },
            ],
            order_by: [],
          } as any
        }
      />,
    );

    await waitFor(() => expect(makeCallToBackend).toHaveBeenCalled());
    const sentFilters =
      makeCallToBackend.mock.calls[0][0].postBody.report_metadata.filter_by;
    // base filter kept unchanged, including its operator
    expect(sentFilters).toContainEqual({
      field_name: 'start_from',
      field_value: '123',
      operator: 'greater_than',
    });
    // exactly one process_status filter, and it is the chart's own equals query
    const statusFilters = sentFilters.filter(
      (f: any) => f.field_name === 'process_status',
    );
    expect(statusFilters).toHaveLength(1);
    expect(statusFilters[0].operator).toBe('equals');
  });

  it('exits loading and renders the empty state when every count query fails', async () => {
    makeCallToBackend.mockImplementation((opts: any) => {
      opts.failureCallback({ message: 'boom' });
    });

    render(
      <ProcessInstanceStatusPieChart
        variant="all"
        reportMetadata={reportMetadata}
      />,
    );

    expect(
      await screen.findByText('No process instances to display.'),
    ).toBeInTheDocument();
  });

  it('uses the for-me endpoint for the for-me variant', async () => {
    render(
      <ProcessInstanceStatusPieChart
        variant="for-me"
        reportMetadata={reportMetadata}
      />,
    );

    await screen.findByText('10');
    expect(makeCallToBackend.mock.calls[0][0].path).toContain(
      '/process-instances/for-me?per_page=1',
    );
  });

  it('shows an empty message when there are no instances', async () => {
    render(
      <ProcessInstanceStatusPieChart
        variant="all"
        reportMetadata={{ columns: [], filter_by: [
          { field_name: 'process_model_identifier', field_value: 'nope', operator: 'equals' },
        ], order_by: [] } as any}
      />,
    );

    // With no matching instances every status total is 0, so the empty state renders.
    expect(
      await screen.findByText('No process instances to display.'),
    ).toBeInTheDocument();
  });
});
