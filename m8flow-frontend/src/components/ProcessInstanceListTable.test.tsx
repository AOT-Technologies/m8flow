import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ProcessInstanceListTable from './ProcessInstanceListTable';

const h = vi.hoisted(() => ({
  postBodies: [] as any[],
  result: null as any,
  report: null as any,
}));

vi.mock('../services/HttpService', () => ({
  default: {
    HttpMethods: { GET: 'GET', POST: 'POST' },
    makeCallToBackend: vi.fn((opts: any) => {
      // The saved-report path fetches the report metadata first, then feeds it
      // into the search call. Dispatch on path so both can be exercised.
      if (opts.path.startsWith('/process-instances/report-metadata')) {
        setTimeout(() => opts.successCallback(h.report), 0);
        return;
      }
      if (opts.path.startsWith('/process-instances')) {
        h.postBodies.push(opts.postBody);
        // Mirror the backend, which echoes the POSTed report_metadata back on
        // the response and only ever overwrites filter_by server-side.
        // See run_process_instance_report in process_instance_report_service.py.
        const response = {
          ...h.result,
          report_metadata: {
            ...h.result.report_metadata,
            order_by: opts.postBody?.report_metadata?.order_by ?? [],
          },
        };
        // Resolve asynchronously, mirroring a real HTTP call. This ensures the
        // success callback runs after the component's mount effects (including
        // the effect that clears stale rows) have flushed.
        setTimeout(() => opts.successCallback(response), 0);
      }
    }),
  },
}));

vi.mock('../services/UserService', () => ({
  default: {
    getPreferredUsername: () => 'someone',
    getUserEmail: () => 'someone@example.com',
    isSuperAdmin: () => false,
  },
}));

vi.mock('../services/DateAndTimeService', () => ({
  default: {
    REFRESH_INTERVAL_SECONDS: 5,
    REFRESH_TIMEOUT_SECONDS: 600,
    formatDurationForDisplay: (v: any) => `${v}`,
    formatDateTime: (v: any) => `${v}`,
    convertSecondsToFormattedDateTime: (v: any) => `${v}`,
  },
}));

vi.mock('../helpers', () => ({
  getLastMilestoneFromProcessInstance: () => ['', ''],
  getProcessStatus: (v: any) => v,
  modifyProcessIdentifierForPathParam: (v: any) => v,
  refreshAtInterval: () => () => {},
  getPageInfoFromSearchParams: (
    sp: any,
    _defaultPerPage: any,
    _defaultPage: any,
    prefix?: string,
  ) => {
    const pfx = prefix ? `${prefix}_` : '';
    const page = parseInt(sp.get(`${pfx}page`) || '1', 10);
    const perPage = parseInt(sp.get(`${pfx}per_page`) || '10', 10);
    return { page, perPage };
  },
}));

vi.mock('./PaginationForTable', () => ({
  default: (props: any) => <div>{props.tableToDisplay}</div>,
}));

vi.mock('./TableCellWithTimeAgoInWords', () => ({
  default: () => <td />,
}));

vi.mock('./ErrorDisplay', () => ({
  childrenForErrorObject: () => null,
  errorForDisplayFromString: () => ({}),
}));

vi.mock('./SpiffTooltip', () => ({
  default: ({ children }: any) => <>{children}</>,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

vi.mock('@mui/icons-material', () => {
  const Icon = () => null;
  return new Proxy(
    { __esModule: true },
    {
      get: (_target, prop) => {
        if (prop === '__esModule') return true;
        if (prop === 'then' || typeof prop === 'symbol') return undefined;
        return Icon;
      },
      has: () => true,
    },
  );
});

// Mixes every sortability case the backend distinguishes:
//   - real process_instance columns (id, start_in_seconds, end_in_seconds)
//   - a metadata column, which the backend gives an orderable alias (filterable: true)
//   - derived/joined accessors the backend cannot meaningfully order by
//     (waiting_for and task_title come from the HumanTaskModel join,
//     process_initiator_username is derived from process_initiator_id)
//   - tenantName, which m8flow injects client-side after the query has run
//   - an accessor the frontend has never heard of, which must fail closed
const COLUMNS = [
  { Header: 'Id', accessor: 'id', filterable: false },
  { Header: 'Start', accessor: 'start_in_seconds', filterable: false },
  { Header: 'End', accessor: 'end_in_seconds', filterable: false },
  { Header: 'Region', accessor: 'region', filterable: true },
  { Header: 'Waiting for', accessor: 'waiting_for', filterable: false },
  { Header: 'Task', accessor: 'task_title', filterable: false },
  { Header: 'Started by', accessor: 'process_initiator_username', filterable: false },
  { Header: 'Tenant', accessor: 'tenantName', filterable: false },
  { Header: 'Derived', accessor: 'some_derived_thing', filterable: false },
];

const SORTABLE_ACCESSORS = ['id', 'start_in_seconds', 'end_in_seconds', 'region'];
const NON_SORTABLE_ACCESSORS = [
  'waiting_for',
  'task_title',
  'process_initiator_username',
  'tenantName',
  'some_derived_thing',
];

const reportMetadata = () => ({
  columns: COLUMNS,
  filter_by: [],
  order_by: [] as string[],
});

const renderTable = (
  initialEntries: string[] = ['/'],
  orderBy: string[] = [],
) =>
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <ProcessInstanceListTable
        variant="all"
        reportMetadata={{ ...reportMetadata(), order_by: orderBy }}
      />
    </MemoryRouter>,
  );

// The saved-report path: only reportIdentifier is passed, so the reportMetadata
// prop is necessarily undefined (the two are mutually exclusive).
const renderTableForSavedReport = (initialEntries: string[] = ['/']) =>
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <ProcessInstanceListTable variant="all" reportIdentifier="my_report" />
    </MemoryRouter>,
  );

const lastBody = () => h.postBodies[h.postBodies.length - 1];

const ariaSortFor = (accessor: string) =>
  screen
    .getByTestId(`sort-header-${accessor}`)
    .closest('th')
    ?.getAttribute('aria-sort');

beforeEach(() => {
  h.postBodies = [];
  h.result = {
    results: [],
    pagination: { count: 0, total: 0, pages: 1 },
    report_metadata: {
      columns: COLUMNS,
      filter_by: [],
      order_by: [],
    },
    report_hash: 'hash-1',
  };
  // Shape returned by /process-instances/report-metadata for a saved report.
  // Every built-in system report ships this order_by.
  h.report = {
    id: 1,
    identifier: 'my_report',
    name: 'My Report',
    report_metadata: {
      columns: COLUMNS,
      filter_by: [],
      order_by: ['-start_in_seconds', '-id'],
    },
  };
});

describe('ProcessInstanceListTable sorting', () => {
  it('renders sort affordance only for sortable columns', async () => {
    renderTable();
    await screen.findByTestId('sort-header-id');
    SORTABLE_ACCESSORS.forEach((accessor) => {
      expect(screen.getByTestId(`sort-header-${accessor}`)).toBeTruthy();
    });
    // Derived, joined, client-injected and unrecognised accessors are not
    // orderable server-side, so they get no sort affordance.
    NON_SORTABLE_ACCESSORS.forEach((accessor) => {
      expect(screen.queryByTestId(`sort-header-${accessor}`)).toBeNull();
    });
  });

  it('still renders the label for columns that are not sortable', async () => {
    renderTable();
    await screen.findByTestId('sort-header-id');
    expect(screen.getByText('Derived')).toBeTruthy();
    expect(screen.getByText('Tenant')).toBeTruthy();
  });

  it('sorts by a metadata column, which the backend can order by', async () => {
    renderTable();
    const regionHeader = await screen.findByTestId('sort-header-region');
    fireEvent.click(regionHeader);
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual(['region', '-id']),
    );
  });

  it('does not apply an order_by override on first load without a sort param', async () => {
    renderTable();
    await screen.findByTestId('sort-header-id');
    expect(lastBody().report_metadata.order_by).toEqual([]);
  });

  it('sorts ascending on first click and descending on second click', async () => {
    renderTable();
    const startHeader = await screen.findByTestId('sort-header-start_in_seconds');

    fireEvent.click(startHeader);
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual([
        'start_in_seconds',
        '-id',
      ]),
    );
    expect(ariaSortFor('start_in_seconds')).toBe('ascending');

    fireEvent.click(screen.getByTestId('sort-header-start_in_seconds'));
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual([
        '-start_in_seconds',
        '-id',
      ]),
    );
    expect(ariaSortFor('start_in_seconds')).toBe('descending');
  });

  it('clears the sort on the third click, falling back to default ordering', async () => {
    renderTable();
    const startHeader = await screen.findByTestId('sort-header-start_in_seconds');

    fireEvent.click(startHeader);
    await waitFor(() => expect(ariaSortFor('start_in_seconds')).toBe('ascending'));
    fireEvent.click(screen.getByTestId('sort-header-start_in_seconds'));
    await waitFor(() => expect(ariaSortFor('start_in_seconds')).toBe('descending'));

    // Third click drops the order_by param entirely, so the backend applies its
    // own default ordering and the UI stops claiming a sort.
    fireEvent.click(screen.getByTestId('sort-header-start_in_seconds'));
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual([]),
    );
    await waitFor(() => expect(ariaSortFor('start_in_seconds')).toBeNull());
  });

  it('starts a fresh ascending cycle after the sort has been cleared', async () => {
    renderTable();
    const startHeader = await screen.findByTestId('sort-header-start_in_seconds');
    fireEvent.click(startHeader);
    await waitFor(() => expect(ariaSortFor('start_in_seconds')).toBe('ascending'));
    fireEvent.click(screen.getByTestId('sort-header-start_in_seconds'));
    await waitFor(() => expect(ariaSortFor('start_in_seconds')).toBe('descending'));
    fireEvent.click(screen.getByTestId('sort-header-start_in_seconds'));
    await waitFor(() => expect(ariaSortFor('start_in_seconds')).toBeNull());

    fireEvent.click(screen.getByTestId('sort-header-start_in_seconds'));
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual([
        'start_in_seconds',
        '-id',
      ]),
    );
    expect(ariaSortFor('start_in_seconds')).toBe('ascending');
  });

  it('switching to another column starts that column at ascending', async () => {
    renderTable(['/?order_by=-start_in_seconds']);
    const endHeader = await screen.findByTestId('sort-header-end_in_seconds');
    fireEvent.click(endHeader);
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual([
        'end_in_seconds',
        '-id',
      ]),
    );
    expect(ariaSortFor('end_in_seconds')).toBe('ascending');
    expect(ariaSortFor('start_in_seconds')).toBeNull();
  });

  it('does not duplicate the tiebreaker when sorting by id itself', async () => {
    renderTable();
    const idHeader = await screen.findByTestId('sort-header-id');
    fireEvent.click(idHeader);
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual(['id']),
    );
  });

  it('sorts by the end column ascending on first click', async () => {
    renderTable();
    const endHeader = await screen.findByTestId('sort-header-end_in_seconds');
    fireEvent.click(endHeader);
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual([
        'end_in_seconds',
        '-id',
      ]),
    );
  });

  it('restores the sort from the URL on load (refresh / pagination persistence)', async () => {
    renderTable(['/?order_by=-end_in_seconds&page=2']);
    await screen.findByTestId('sort-header-end_in_seconds');
    expect(lastBody().report_metadata.order_by).toEqual([
      '-end_in_seconds',
      '-id',
    ]);
    // the descending indicator reflects the URL state
    expect(ariaSortFor('end_in_seconds')).toBe('descending');
  });

  it("shows the saved report's sort indicator without a click when opened via reportIdentifier", async () => {
    // The report metadata is fetched over the network and POSTed, never held in
    // the reportMetadata prop, so the indicator has to come from the response.
    renderTableForSavedReport();
    await screen.findByTestId('sort-header-start_in_seconds');
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual([
        '-start_in_seconds',
        '-id',
      ]),
    );
    await waitFor(() => expect(ariaSortFor('start_in_seconds')).toBe('descending'));
    // only the leading order_by term drives the indicator
    expect(ariaSortFor('id')).toBeNull();
  });

  it("clearing the sort reverts to the saved report's own order", async () => {
    // Cycling a column back to "none" removes the URL param, so ordering falls
    // back to the report metadata rather than to no order at all. Give the report
    // a different sort column so the fallback is unambiguous.
    h.report.report_metadata.order_by = ['-end_in_seconds'];
    renderTableForSavedReport(['/?order_by=-start_in_seconds']);
    const startHeader = await screen.findByTestId('sort-header-start_in_seconds');
    await waitFor(() => expect(ariaSortFor('start_in_seconds')).toBe('descending'));

    fireEvent.click(startHeader);
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual(['-end_in_seconds']),
    );
    await waitFor(() => expect(ariaSortFor('end_in_seconds')).toBe('descending'));
    expect(ariaSortFor('start_in_seconds')).toBeNull();
  });

  it('lets an explicit URL sort win over the saved report order', async () => {
    renderTableForSavedReport(['/?order_by=id']);
    await screen.findByTestId('sort-header-id');
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual(['id']),
    );
    await waitFor(() => expect(ariaSortFor('id')).toBe('ascending'));
    expect(ariaSortFor('start_in_seconds')).toBeNull();
  });

  it('shows the sort indicator from the reportMetadata prop without a click', async () => {
    renderTable(['/'], ['-end_in_seconds']);
    await screen.findByTestId('sort-header-end_in_seconds');
    await waitFor(() => expect(ariaSortFor('end_in_seconds')).toBe('descending'));
  });

  it('shows no sort indicator when no order is requested', async () => {
    // The backend applies its own default ordering in this case, but the UI does
    // not claim a sort it never asked for.
    renderTable();
    await screen.findByTestId('sort-header-id');
    expect(lastBody().report_metadata.order_by).toEqual([]);
    ['id', 'start_in_seconds', 'end_in_seconds'].forEach((accessor) => {
      expect(ariaSortFor(accessor)).toBeNull();
    });
  });
});
