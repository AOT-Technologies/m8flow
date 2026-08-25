import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ProcessInstanceListTable from './ProcessInstanceListTable';
import type { ReportMetadata } from '../interfaces';

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

const upstreamSpy = vi.fn((props: Record<string, unknown>) => (
  <div data-testid="upstream-process-instance-list-table">
    {JSON.stringify(props.reportMetadata ?? null)}
  </div>
));

vi.mock('@spiff-core/components/ProcessInstanceListTable', () => ({
  default: (props: Record<string, unknown>) => upstreamSpy(props),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import UserService from '../services/UserService';

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

describe('ProcessInstanceListTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('injects a tenant column for super-admin on the all-instances table', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);

    renderTable();

    expect(screen.getByTestId('upstream-process-instance-list-table')).toBeInTheDocument();
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

    expect(screen.getByTestId('upstream-process-instance-list-table')).toBeInTheDocument();
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
