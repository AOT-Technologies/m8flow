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

const COLUMNS = [
  { Header: 'Id', accessor: 'id', filterable: false },
  { Header: 'Start', accessor: 'start_in_seconds', filterable: false },
  { Header: 'End', accessor: 'end_in_seconds', filterable: false },
  { Header: 'Waiting for', accessor: 'waiting_for', filterable: false },
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
    expect(screen.getByTestId('sort-header-start_in_seconds')).toBeTruthy();
    expect(screen.getByTestId('sort-header-end_in_seconds')).toBeTruthy();
    // waiting_for is not orderable server-side, so no sort affordance.
    expect(screen.queryByTestId('sort-header-waiting_for')).toBeNull();
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
      expect(lastBody().report_metadata.order_by).toEqual(['start_in_seconds']),
    );
    expect(
      screen
        .getByTestId('sort-header-start_in_seconds')
        .closest('th')
        ?.getAttribute('aria-sort'),
    ).toBe('ascending');

    fireEvent.click(screen.getByTestId('sort-header-start_in_seconds'));
    await waitFor(() =>
      expect(lastBody().report_metadata.order_by).toEqual(['-start_in_seconds']),
    );
    expect(
      screen
        .getByTestId('sort-header-start_in_seconds')
        .closest('th')
        ?.getAttribute('aria-sort'),
    ).toBe('descending');
  });

  it('sorts by the id column ascending on first click', async () => {
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
      expect(lastBody().report_metadata.order_by).toEqual(['end_in_seconds']),
    );
  });

  it('restores the sort from the URL on load (refresh / pagination persistence)', async () => {
    renderTable(['/?order_by=-end_in_seconds&page=2']);
    await screen.findByTestId('sort-header-end_in_seconds');
    expect(lastBody().report_metadata.order_by).toEqual(['-end_in_seconds']);
    // the descending indicator reflects the URL state
    expect(
      screen
        .getByTestId('sort-header-end_in_seconds')
        .closest('th')
        ?.getAttribute('aria-sort'),
    ).toBe('descending');
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
