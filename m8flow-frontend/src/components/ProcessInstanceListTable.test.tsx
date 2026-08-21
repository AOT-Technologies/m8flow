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

const h = vi.hoisted(() => ({ fetches: 0 }));

const upstreamSpy = vi.fn();

// Upstream stand-in. It models the two behaviours of the real component that this
// override depends on: it invokes the (possibly wrapped) filterComponent on every
// render, and it re-queries when the reportMetadata object IDENTITY changes — see
// the useEffect deps in spiffworkflow-frontend/src/components/ProcessInstanceListTable.tsx.
// Modelling identity rather than value is what lets these tests catch a wrapper that
// hands upstream a fresh object on every render.
vi.mock('@spiff-core/components/ProcessInstanceListTable', async () => {
  const React = await import('react');
  return {
    default: function MockUpstream(props: Record<string, any>) {
      upstreamSpy(props);
      React.useEffect(() => {
        h.fetches += 1;
      }, [props.reportMetadata]);
      return (
        <div
          data-testid="upstream-pi-table"
          data-metadata={JSON.stringify(props.reportMetadata ?? null)}
        >
          {props.filterComponent ? props.filterComponent() : null}
        </div>
      );
    },
  };
});

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

// Real metadata arrives from the server with columns populated; the override treats
// an empty columns array as "not settled yet" because upstream adopts the server's
// echo in that state.
const metadata = (filterBy: any[] = [], columns: any[] = [{ accessor: 'id' }]) => ({
  columns,
  filter_by: filterBy,
  order_by: [],
});

const filters = () => <div data-testid="filters" />;
const forwarded = () =>
  JSON.parse(screen.getByTestId('upstream-pi-table').dataset.metadata!);
const selected = () =>
  JSON.parse(screen.getByTestId('donut').dataset.selected!);

beforeEach(() => {
  vi.clearAllMocks();
  h.fetches = 0;
  // clearAllMocks keeps implementations, so pin the default explicitly rather
  // than inheriting whatever the previous test set.
  vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
});

describe('ProcessInstanceListTable status donut', () => {
  it('renders no donut when the table has no filter bar', () => {
    render(<ProcessInstanceListTable reportMetadata={metadata()} />);
    expect(screen.queryByTestId('donut')).not.toBeInTheDocument();
  });

  it('renders the donut below the filter bar and forwards metadata untouched', () => {
    const md = metadata();
    render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={md}
        filterComponent={filters}
      />,
    );
    expect(screen.getByTestId('filters')).toBeInTheDocument();
    expect(screen.getByTestId('donut').dataset.variant).toBe('all');
    expect(forwarded()).toEqual(md);
    expect(h.fetches).toBe(1);
  });

  it('does not provoke a re-query when re-rendered with unchanged metadata', () => {
    // Pins the object-identity invariant: returning `{...reportMetadata}` from the
    // memo instead of the prop itself would make upstream refetch on every render.
    const md = metadata();
    const { rerender } = render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={md}
        filterComponent={filters}
      />,
    );
    expect(h.fetches).toBe(1);
    rerender(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={md}
        filterComponent={filters}
      />,
    );
    expect(h.fetches).toBe(1);
  });

  it('injects the clicked status as a filter and clears it on a second click', () => {
    render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata([
          { field_name: 'process_model_identifier', field_value: 'm1' },
        ])}
        filterComponent={filters}
      />,
    );

    fireEvent.click(screen.getByTestId('donut'));
    expect(forwarded().filter_by).toEqual([
      { field_name: 'process_model_identifier', field_value: 'm1' },
      { field_name: 'process_status', field_value: 'error', operator: 'equals' },
    ]);
    expect(selected()).toEqual(['error']);
    expect(h.fetches).toBe(2);

    fireEvent.click(screen.getByTestId('donut'));
    expect(forwarded().filter_by).toEqual([
      { field_name: 'process_model_identifier', field_value: 'm1' },
    ]);
  });

  it('ignores a click while the page has its own status filter, and it cannot resurface after that filter is cleared', () => {
    // Regression: the clearing effect used to fire only on a transition INTO a
    // widget status, so a click made while one was already active lurked in state
    // and silently filtered the table the moment the user cleared the filter bar.
    const { rerender } = render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata([
          { field_name: 'process_status', field_value: 'complete', operator: 'equals' },
        ])}
        filterComponent={filters}
      />,
    );

    fireEvent.click(screen.getByTestId('donut'));
    expect(selected()).toEqual(['complete']);
    expect(forwarded().filter_by).toEqual([
      { field_name: 'process_status', field_value: 'complete', operator: 'equals' },
    ]);

    // user clears the status in upstream's MultiSelect -> new metadata object
    rerender(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata()}
        filterComponent={filters}
      />,
    );
    expect(forwarded().filter_by).toEqual([]);
    expect(selected()).toEqual([]);
  });

  it('retires the donut selection when upstream replaces its metadata (Clear, report load, tab switch)', () => {
    const md = metadata([{ field_name: 'process_model_identifier', field_value: 'm1' }]);
    const { rerender } = render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={md}
        filterComponent={filters}
      />,
    );
    fireEvent.click(screen.getByTestId('donut'));
    expect(selected()).toEqual(['error']);

    // upstream's Clear button hands down a fresh object with the filters emptied
    rerender(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata()}
        filterComponent={filters}
      />,
    );
    expect(selected()).toEqual([]);
    expect(forwarded().filter_by).toEqual([]);
  });

  it('does not inject while upstream metadata is unsettled (empty columns)', () => {
    // With columns empty upstream adopts the server's echo of whatever is posted,
    // which would bake the donut's filter into upstream state irreversibly.
    render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata([], [])}
        filterComponent={filters}
      />,
    );
    fireEvent.click(screen.getByTestId('donut'));
    expect(forwarded().filter_by).toEqual([]);
    expect(selected()).toEqual([]);
  });

  it('resolves duplicate status filters the same way upstream does (last wins)', () => {
    render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata([
          { field_name: 'process_status', field_value: 'waiting', operator: 'equals' },
          { field_name: 'process_status', field_value: 'complete', operator: 'equals' },
        ])}
        filterComponent={filters}
      />,
    );
    expect(selected()).toEqual(['complete']);
    fireEvent.click(screen.getByTestId('donut'));
    expect(forwarded().filter_by).toHaveLength(2);
  });

  it('highlights every status when the filter bar has several selected', () => {
    // Upstream stores a multi-select as a comma-joined value.
    render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata([
          { field_name: 'process_status', field_value: 'error,waiting', operator: 'equals' },
        ])}
        filterComponent={filters}
      />,
    );
    expect(selected()).toEqual(['error', 'waiting']);
  });

  it('survives a non-string status field_value', () => {
    // ReportFilter.field_value is `any` upstream and really does hold booleans.
    render(
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={metadata([
          { field_name: 'process_status', field_value: true },
        ])}
        filterComponent={filters}
      />,
    );
    expect(screen.getByTestId('donut')).toBeInTheDocument();
    expect(selected()).toEqual(['true']);
  });

  it('renders and toggles safely with no reportMetadata at all', () => {
    render(
      <ProcessInstanceListTable variant="all" filterComponent={filters} />,
    );
    expect(screen.getByTestId('donut')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('donut'));
    expect(forwarded()).toBeNull();
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
