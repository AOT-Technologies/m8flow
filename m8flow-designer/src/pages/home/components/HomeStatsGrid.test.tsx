import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { HomeStatsGrid } from './HomeStatsGrid';

describe('HomeStatsGrid', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders provided stats without fetching', () => {
    render(
      <HomeStatsGrid
        showTotalTenants
        stats={{
          active_process_instances: 142,
          tasks_waiting_on_me: 8,
          errors_needing_review: 5,
          completed_today: 37,
          avg_completion_minutes: 4.2,
          total_tenants: 16,
        }}
      />,
    );

    expect(screen.getByText('142')).toBeInTheDocument();
    expect(screen.getByText('Active process instances')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('4.2')).toBeInTheDocument();
    expect(screen.getByText('Total tenants')).toBeInTheDocument();
  });

  it('hides Total tenants for non–super-admins even when the field is null', () => {
    render(
      <HomeStatsGrid
        showTotalTenants={false}
        stats={{
          active_process_instances: null,
          tasks_waiting_on_me: 3,
          errors_needing_review: null,
          completed_today: null,
          avg_completion_minutes: null,
          total_tenants: null,
        }}
      />,
    );

    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.queryByText('Total tenants')).not.toBeInTheDocument();
  });

  it('renders an em dash for null permission-gated fields', () => {
    render(
      <HomeStatsGrid
        showTotalTenants
        stats={{
          active_process_instances: null,
          tasks_waiting_on_me: 3,
          errors_needing_review: null,
          completed_today: null,
          avg_completion_minutes: null,
          total_tenants: null,
        }}
      />,
    );

    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Total tenants')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4);
  });

  it('fetches home-stats with tenantId when no stats override is passed', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        active_process_instances: 2,
        tasks_waiting_on_me: 1,
        errors_needing_review: 0,
        completed_today: 0,
        avg_completion_minutes: null,
        total_tenants: 4,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<HomeStatsGrid tenantId="t2" />);

    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalled();
    const calledUrl = String(fetchMock.mock.calls[0]?.[0] ?? '');
    expect(calledUrl).toContain('/v1.0/m8flow/home-stats');
    expect(calledUrl).toContain('tenantId=t2');
  });

  it('issues a single home-stats fetch when StrictMode remounts the effect', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        active_process_instances: 2,
        tasks_waiting_on_me: 1,
        errors_needing_review: 0,
        completed_today: 0,
        avg_completion_minutes: null,
        total_tenants: 4,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <React.StrictMode>
        <HomeStatsGrid tenantId="t2" />
      </React.StrictMode>,
    );

    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
