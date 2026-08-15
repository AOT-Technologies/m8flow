import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ProcessInstanceListTableWithFilters from './ProcessInstanceListTableWithFilters';

const h = vi.hoisted(() => ({
  mountCount: 0,
}));

vi.mock('../services/UserService', () => ({
  default: {
    isSuperAdmin: vi.fn(),
  },
}));

vi.mock('../contexts/GlobalTenantContext', () => ({
  useGlobalTenant: vi.fn(() => ({
    selectedTenantId: '',
    setSelectedTenantId: vi.fn(),
  })),
}));

vi.mock('@spiff-core/components/ProcessInstanceListTableWithFilters', async () => {
  const React = await import('react');
  return {
    default: function MockUpstream(props: {
      additionalReportFilters?: unknown;
    }) {
      React.useEffect(() => {
        h.mountCount += 1;
      }, []);
      return (
        <div
          data-testid="upstream-pi-filters"
          data-filters={JSON.stringify(props.additionalReportFilters ?? null)}
        />
      );
    },
  };
});

import UserService from '../services/UserService';
import { useGlobalTenant } from '../contexts/GlobalTenantContext';

describe('ProcessInstanceListTableWithFilters', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    h.mountCount = 0;
  });

  it('injects tenant_id equals filter for super-admin with a selected tenant', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    render(
      <ProcessInstanceListTableWithFilters
        additionalReportFilters={[
          { field_name: 'status', field_value: 'complete', operator: 'equals' },
        ]}
      />,
    );
    expect(JSON.parse(screen.getByTestId('upstream-pi-filters').dataset.filters!)).toEqual([
      { field_name: 'status', field_value: 'complete', operator: 'equals' },
      { field_name: 'tenant_id', field_value: 'tenant-a', operator: 'equals' },
    ]);
  });

  it('strips a prior tenant_id filter before injecting the selected tenant', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-b',
      setSelectedTenantId: vi.fn(),
    });
    render(
      <ProcessInstanceListTableWithFilters
        additionalReportFilters={[
          { field_name: 'tenant_id', field_value: 'stale', operator: 'equals' },
          { field_name: 'status', field_value: 'complete', operator: 'equals' },
        ]}
      />,
    );
    expect(JSON.parse(screen.getByTestId('upstream-pi-filters').dataset.filters!)).toEqual([
      { field_name: 'status', field_value: 'complete', operator: 'equals' },
      { field_name: 'tenant_id', field_value: 'tenant-b', operator: 'equals' },
    ]);
  });

  it('remounts upstream when the selected tenant changes for super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(true);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    const { rerender } = render(<ProcessInstanceListTableWithFilters />);
    expect(h.mountCount).toBe(1);

    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-b',
      setSelectedTenantId: vi.fn(),
    });
    rerender(<ProcessInstanceListTableWithFilters />);
    expect(h.mountCount).toBe(2);
  });

  it('passes incoming filters through unchanged for non-super-admin', () => {
    vi.mocked(UserService.isSuperAdmin).mockReturnValue(false);
    vi.mocked(useGlobalTenant).mockReturnValue({
      selectedTenantId: 'tenant-a',
      setSelectedTenantId: vi.fn(),
    });
    const incoming = [
      { field_name: 'tenant_id', field_value: 'stale', operator: 'equals' },
    ];
    render(
      <ProcessInstanceListTableWithFilters additionalReportFilters={incoming} />,
    );
    expect(
      JSON.parse(screen.getByTestId('upstream-pi-filters').dataset.filters!),
    ).toEqual(incoming);
  });
});
