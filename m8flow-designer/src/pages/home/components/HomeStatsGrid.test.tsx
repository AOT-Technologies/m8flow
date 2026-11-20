import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
        showTaskCount
        stats={{
          active_process_instances: 142,
          tasks_waiting_on_me: 8,
          show_tasks_waiting_on_me: true,
          errors_needing_review: 5,
          completed_today: 37,
          avg_completion_minutes: 4.2,
          total_tenants: 16,
        }}
      />,
    );

    expect(screen.getByText('142')).toBeInTheDocument();
    expect(screen.getByText('Active process instances')).toBeInTheDocument();
    expect(screen.getByText('Tasks waiting on me')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('4.2')).toBeInTheDocument();
    expect(screen.getByText('Total tenants')).toBeInTheDocument();
  });

  it('hides Total tenants for non–super-admins even when the field is null', () => {
    render(
      <HomeStatsGrid
        showTotalTenants={false}
        showTaskCount
        stats={{
          active_process_instances: null,
          tasks_waiting_on_me: 3,
          show_tasks_waiting_on_me: true,
          errors_needing_review: null,
          completed_today: null,
          avg_completion_minutes: null,
          total_tenants: null,
        }}
      />,
    );

    expect(screen.getByText('Tasks waiting on me')).toBeInTheDocument();
    expect(screen.queryByText('Total tenants')).not.toBeInTheDocument();
  });

  it('renders an em dash for null permission-gated fields', () => {
    render(
      <HomeStatsGrid
        showTotalTenants
        showTaskCount
        stats={{
          active_process_instances: null,
          tasks_waiting_on_me: 3,
          show_tasks_waiting_on_me: true,
          errors_needing_review: null,
          completed_today: null,
          avg_completion_minutes: null,
          total_tenants: null,
        }}
      />,
    );

    expect(screen.getByText('Tasks waiting on me')).toBeInTheDocument();
    expect(screen.getByText('Total tenants')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(4);
  });

  it('fetches home-stats with tenantId when no stats override is passed', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        active_process_instances: 2,
        tasks_waiting_on_me: 1,
        show_tasks_waiting_on_me: true,
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
        show_tasks_waiting_on_me: true,
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

  it('renders the task count when the backend enables it', () => {
    render(
      <HomeStatsGrid
        showTaskCount
        stats={{
          active_process_instances: 1,
          tasks_waiting_on_me: 4,
          show_tasks_waiting_on_me: true,
          errors_needing_review: 0,
          completed_today: 0,
          avg_completion_minutes: null,
          total_tenants: 1,
        }}
      />,
    );

    expect(screen.getByText('Tasks waiting on me')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('Active process instances')).toBeInTheDocument();
  });

  it('hides the task count when the backend denies task access', () => {
    render(
      <HomeStatsGrid
        stats={{
          active_process_instances: 1,
          tasks_waiting_on_me: null,
          show_tasks_waiting_on_me: false,
          errors_needing_review: 0,
          completed_today: 0,
          avg_completion_minutes: null,
          total_tenants: null,
        }}
      />,
    );

    expect(screen.queryByText('Tasks waiting on me')).not.toBeInTheDocument();
  });
  describe('clickable cards (M8F-711)', () => {
    const stats = {
      active_process_instances: 5,
      tasks_waiting_on_me: 0,
      show_tasks_waiting_on_me: true,
      errors_needing_review: 11,
      completed_today: 0,
      avg_completion_minutes: 4.4,
      total_tenants: null,
    };
    const hrefOf = (label: string) => screen.getByText(label).closest('a')?.getAttribute('href');

    it('links each card to its filtered list when permitted', () => {
      render(
        <MemoryRouter>
          <HomeStatsGrid showTaskCount canOpenInstances canOpenTasks stats={stats} />
        </MemoryRouter>,
      );

      expect(hrefOf('Active process instances')).toBe('/process-instances?status=active');
      expect(hrefOf('Errors needing review')).toBe('/process-instances?status=error');
      expect(hrefOf('Completed today')).toBe('/process-instances?status=complete&completed=today');
      // An average has no matching list, so this card stays plain.
      expect(hrefOf('Avg. completion time')).toBeUndefined();
      expect(hrefOf('Tasks waiting on me')).toBe('/task-review');
      expect(screen.getByText('Active process instances').closest('a')).toHaveAttribute(
        'title',
        'Running, waiting, or awaiting input',
      );
    });

    it('keeps cards non-clickable without list permission', () => {
      render(<HomeStatsGrid showTaskCount stats={stats} />);

      expect(screen.queryAllByRole('link')).toHaveLength(0);
    });
  });
});
