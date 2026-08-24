import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type React from 'react';
import ProcessInstanceListTable from './ProcessInstanceListTable';

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
    getPreferredUsername: vi.fn(() => 'admin'),
    getUserEmail: vi.fn(() => 'admin@example.com'),
  },
}));

vi.mock('../services/HttpService', () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

vi.mock('../services/DateAndTimeService', () => ({
  default: {
    REFRESH_INTERVAL_SECONDS: 30,
    REFRESH_TIMEOUT_SECONDS: 60,
    convertSecondsToFormattedDateTime: vi.fn((value: number) => `${value}`),
    formatDurationForDisplay: vi.fn((value: string) => value),
    formatDateTime: vi.fn((value: string) => value),
  },
}));

vi.mock('../helpers', () => ({
  getLastMilestoneFromProcessInstance: vi.fn((_row, value) => [value, value]),
  getPageInfoFromSearchParams: vi.fn(() => ({ page: 1, perPage: 10 })),
  getProcessStatus: vi.fn((value: string) => value),
  modifyProcessIdentifierForPathParam: vi.fn((value: string) => value),
  refreshAtInterval: vi.fn(() => vi.fn()),
}));

vi.mock('./PaginationForTable', () => ({
  default: ({ tableToDisplay }: { tableToDisplay: React.ReactNode }) => (
    <div data-testid="pagination-mock">{tableToDisplay}</div>
  ),
}));

vi.mock('./TableCellWithTimeAgoInWords', () => ({
  default: ({ timeInSeconds }: { timeInSeconds: number }) => (
    <td data-testid={`timeago-${timeInSeconds}`}>{timeInSeconds}</td>
  ),
}));

vi.mock('./ErrorDisplay', () => ({
  childrenForErrorObject: (error: string) => <div>{error}</div>,
  errorForDisplayFromString: (error: string) => error,
}));

vi.mock('./SpiffTooltip', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import UserService from '../services/UserService';
import HttpService from '../services/HttpService';

function stubProcessInstancesList() {
  vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts: any) => {
    if (opts.path.startsWith('/process-instances/report-metadata')) {
      return;
    }
    opts.successCallback({
      results: [
        {
          id: 42,
          process_model_identifier: 'hr/onboarding',
          process_model_display_name: 'Onboarding',
          start_in_seconds: 100,
          end_in_seconds: 0,
          process_initiator_username: 'admin',
          last_milestone_bpmn_name: 'Started',
          status: 'complete',
          updated_at_in_seconds: 120,
          task_updated_at_in_seconds: 120,
          tenantId: 'tenant-a',
          tenantName: 'Acme Corp',
        },
      ],
      pagination: { total: 1, pages: 1 },
      report_hash: 'hash-1',
      report_metadata: {
        columns: [
          { Header: 'Id', accessor: 'id' },
          { Header: 'Process', accessor: 'process_model_display_name' },
          { Header: 'Status', accessor: 'status' },
        ],
        filter_by: [],
        order_by: [],
      },
    });
  });
}

function renderTable() {
  return render(
    <MemoryRouter>
      <ProcessInstanceListTable variant="all" />
    </MemoryRouter>,
  );
}

describe('ProcessInstanceListTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stubProcessInstancesList();
  });

  it('shows a tenant column for super-admin on the all-instances table', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);

    renderTable();

    expect(
      await screen.findByTestId('process-instance-show-link-tenantName'),
    ).toHaveTextContent('Acme Corp');
    expect(screen.getByText('tenant')).toBeInTheDocument();
    expect(HttpService.makeCallToBackend).toHaveBeenCalledWith(
      expect.objectContaining({
        path: '/process-instances?per_page=10&page=1',
      }),
    );
  });

  it('does not show a tenant column for non-super-admin', async () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);

    renderTable();

    expect(
      await screen.findByTestId('process-instance-show-link-id'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('process-instance-show-link-tenantName'),
    ).toBeNull();
    expect(screen.queryByText('tenant')).toBeNull();
  });
});
