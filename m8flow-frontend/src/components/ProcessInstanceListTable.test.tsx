import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ProcessInstanceListTable from './ProcessInstanceListTable';

const h = vi.hoisted(() => ({
  postBodies: [] as any[],
  result: null as any,
}));

vi.mock('../services/HttpService', () => ({
  default: {
    HttpMethods: { GET: 'GET', POST: 'POST' },
    makeCallToBackend: vi.fn((opts: any) => {
      if (opts.path.startsWith('/process-instances')) {
        h.postBodies.push(opts.postBody);
        // Resolve asynchronously, mirroring a real HTTP call. This ensures the
        // success callback runs after the component's mount effects (including
        // the effect that clears stale rows) have flushed.
        setTimeout(() => opts.successCallback(h.result), 0);
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

const renderTable = (initialEntries: string[] = ['/']) =>
  render(
    <MemoryRouter initialEntries={initialEntries}>
      <ProcessInstanceListTable variant="all" reportMetadata={reportMetadata()} />
    </MemoryRouter>,
  );

const lastBody = () => h.postBodies[h.postBodies.length - 1];

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
});
