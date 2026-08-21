import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ProcessInstanceListTable from './ProcessInstanceListTable';
import UserService from '../services/UserService';
import type { ReportMetadata } from '../interfaces';

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

const upstreamSpy = vi.fn();

// Upstream stand-in: records the props it was handed, renders the (possibly
// wrapped) filterComponent, and exposes the report metadata that drives its own
// re-query.
vi.mock('@spiff-core/components/ProcessInstanceListTable', () => ({
  default: (props: Record<string, any>) => {
    upstreamSpy(props);
    return (
      <div
        data-testid="upstream-pi-table"
        data-metadata={JSON.stringify(props.reportMetadata ?? null)}
      >
        {props.filterComponent ? props.filterComponent() : null}
      </div>
    );
  },
}));

vi.mock('./ProcessInstanceStatusPieChart', () => ({
  default: (props: Record<string, any>) => (
    <button
      type="button"
      data-testid="donut"
      data-selected={JSON.stringify(props.selectedStatuses)}
      data-variant={props.variant}
      onClick={() => props.onStatusClick('error')}
    >
      donut
    </button>
  ),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const metadata = (filterBy: any[] = []) => ({
  columns: [],
  filter_by: filterBy,
  order_by: [],
});

const forwardedMetadata = () =>
  JSON.parse(screen.getByTestId('upstream-pi-table').dataset.metadata!);

beforeEach(() => {
  vi.clearAllMocks();
  // clearAllMocks keeps implementations, so pin the default explicitly rather
  // than inheriting whatever the previous test set.
  vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
});

describe('ProcessInstanceListTable status donut', () => {
  it('renders no donut when the table has no filter bar', () => {
    render(<ProcessInstanceListTable reportMetadata={metadata()} />);
    expect(screen.queryByTestId('donut')).not.toBeInTheDocument();
  });

  it('renders the donut below the filter bar when one is present', () => {
    render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata()}
        filterComponent={() => <div data-testid="filters" />}
      />,
    );
    expect(screen.getByTestId('filters')).toBeInTheDocument();
    const donut = screen.getByTestId('donut');
    expect(donut.dataset.variant).toBe('all');
    // untouched metadata keeps the same identity upstream already saw
    expect(forwardedMetadata()).toEqual(metadata());
  });

  it('injects the clicked status as a filter and clears it on a second click', () => {
    render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata([
          { field_name: 'process_model_identifier', field_value: 'm1' },
        ])}
        filterComponent={() => <div data-testid="filters" />}
      />,
    );

    fireEvent.click(screen.getByTestId('donut'));
    expect(forwardedMetadata().filter_by).toEqual([
      { field_name: 'process_model_identifier', field_value: 'm1' },
      { field_name: 'process_status', field_value: 'error', operator: 'equals' },
    ]);
    expect(JSON.parse(screen.getByTestId('donut').dataset.selected!)).toEqual([
      'error',
    ]);

    fireEvent.click(screen.getByTestId('donut'));
    expect(forwardedMetadata().filter_by).toEqual([
      { field_name: 'process_model_identifier', field_value: 'm1' },
    ]);
  });

  it("defers to the page's own status filter and drops a stale chart status", () => {
    const { rerender } = render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata()}
        filterComponent={() => <div data-testid="filters" />}
      />,
    );
    fireEvent.click(screen.getByTestId('donut'));
    expect(forwardedMetadata().filter_by).toHaveLength(1);

    const widgetFiltered = metadata([
      { field_name: 'process_status', field_value: 'complete', operator: 'equals' },
    ]);
    rerender(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={widgetFiltered}
        filterComponent={() => <div data-testid="filters" />}
      />,
    );
    // the widget's status is forwarded verbatim, not replaced by the chart's
    expect(forwardedMetadata()).toEqual(widgetFiltered);
    expect(JSON.parse(screen.getByTestId('donut').dataset.selected!)).toEqual([
      'complete',
    ]);

    // clearing the widget must not resurrect the earlier chart selection
    rerender(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata()}
        filterComponent={() => <div data-testid="filters" />}
      />,
    );
    expect(forwardedMetadata().filter_by).toEqual([]);
  });
});

const baseReportMetadata: ReportMetadata = {
  columns: [
    { Header: 'Id', accessor: 'id', filterable: false },
    {
      Header: 'Process',
      accessor: 'process_model_display_name',
      filterable: false,
    },
    { Header: 'Status', accessor: 'status', filterable: false },
  ],
  filter_by: [],
  order_by: [],
};

function renderTable() {
  return render(
    <MemoryRouter>
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={baseReportMetadata}
      />
    </MemoryRouter>,
  );
}

describe('ProcessInstanceListTable tenant column', () => {
  it('injects a tenant column for super-admin on the all-instances table', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);

    renderTable();

    expect(screen.getByTestId('upstream-pi-table')).toBeInTheDocument();
    expect(upstreamSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        reportMetadata: expect.objectContaining({
          columns: [
            expect.objectContaining({ Header: 'Id', accessor: 'id' }),
            expect.objectContaining({ Header: 'tenant', accessor: 'tenantName' }),
            expect.objectContaining({
              Header: 'Process',
              accessor: 'process_model_display_name',
            }),
            expect.objectContaining({ Header: 'Status', accessor: 'status' }),
          ],
        }),
      }),
    );
  });

  it('passes report metadata through for non-super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);

    renderTable();

    expect(screen.getByTestId('upstream-pi-table')).toBeInTheDocument();
    expect(upstreamSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        reportMetadata: baseReportMetadata,
      }),
    );
  });

  it('does not inject a duplicate tenant column when one already exists', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);

    render(
      <MemoryRouter>
        <ProcessInstanceListTable
          variant="all"
          reportMetadata={{
            ...baseReportMetadata,
            columns: [
              { Header: 'Id', accessor: 'id', filterable: false },
              { Header: 'Tenant', accessor: 'tenantName', filterable: false },
              {
                Header: 'Process',
                accessor: 'process_model_display_name',
                filterable: false,
              },
            ],
          }}
        />
      </MemoryRouter>,
    );

    expect(upstreamSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        reportMetadata: expect.objectContaining({
          columns: [
            expect.objectContaining({ Header: 'Id', accessor: 'id' }),
            expect.objectContaining({ Header: 'Tenant', accessor: 'tenantName' }),
            expect.objectContaining({
              Header: 'Process',
              accessor: 'process_model_display_name',
            }),
          ],
        }),
      }),
    );
  });

  it('does not inject tenant as the only requested column before report metadata is initialized', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);

    render(
      <MemoryRouter>
        <ProcessInstanceListTable
          variant="all"
          reportMetadata={{
            columns: [],
            filter_by: [],
            order_by: [],
          }}
        />
      </MemoryRouter>,
    );

    expect(upstreamSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        reportMetadata: expect.objectContaining({
          columns: [],
        }),
      }),
    );
  });
});
