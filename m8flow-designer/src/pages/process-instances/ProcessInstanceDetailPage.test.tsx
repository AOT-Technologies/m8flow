import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SessionFixtureContext } from '@/components/session/testSupport';
import { activeTenantFromContext, capabilitiesFromContext } from '@/components/session/testSupport';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => ({
    tenants: [],
    refreshTenants: () => {},
    organizationMemberships: [],
    activeTenantLabel: null,
  }),
}));
import ProcessInstanceDetailPage from './ProcessInstanceDetailPage';

// bpmn-js's raw ESM doesn't resolve under Vitest's Node-based SSR runner.
// These tests stay on states that never mount <InstanceDiagramViewer>
// (invalid id, tenant gate, 404, fetch error, no-bpmn_xml).
function renderWithOutlet(context: SessionFixtureContext, initial = '/process-instances/7') {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/process-instances/:instanceId" element={<ProcessInstanceDetailPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

function mockDetail(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 7,
    process_model_identifier: 'finance/invoice-approval',
    process_model_display_name: 'Invoice Approval',
    status: 'waiting',
    started_by: 'editor',
    start_in_seconds: 1_700_000_000,
    end_in_seconds: null,
    updated_at_in_seconds: 1_700_000_100,
    last_milestone_bpmn_name: null,
    bpmn_xml: null,
    tasks: [],
    ...overrides,
  };
}

function emptyList() {
  return { results: [] };
}

function stubFetches(detail: Record<string, unknown> | { errorStatus: number }) {
  return vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const path = String(url);
    const method = (init?.method ?? 'GET').toUpperCase();
    if (method === 'POST') {
      return Promise.resolve({
        ok: true,
        json: async () => ({ id: 7, status: 'terminated' }),
      });
    }
    if (path.includes('/completable-tasks')) {
      return Promise.resolve({ ok: true, json: async () => emptyList() });
    }
    if (path.includes('/completed-tasks')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ completed_by_me: [], all_completed: [] }),
      });
    }
    if (path.includes('/events') || path.includes('/milestones')) {
      return Promise.resolve({ ok: true, json: async () => emptyList() });
    }
    if ('errorStatus' in detail) {
      return Promise.resolve({ ok: false, status: detail.errorStatus });
    }
    return Promise.resolve({
      ok: true,
      json: async () => detail,
    });
  });
}

const editorCtx: SessionFixtureContext = {
  scopedTenantId: 't1',
  selectedTenantId: 't1',
  isSuperAdmin: false,
  canManageProcesses: true,
};

describe('ProcessInstanceDetailPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows "not found" for a non-numeric id without fetching', () => {
    renderWithOutlet(
      { scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false },
      '/process-instances/not-a-number',
    );
    expect(screen.getByText('Process instance not found.')).toBeInTheDocument();
  });

  it('prompts super-admin when All Tenants is selected', () => {
    renderWithOutlet({ scopedTenantId: null, selectedTenantId: null, isSuperAdmin: true });
    expect(
      screen.getByText('Process instances are tenant-scoped. Select a concrete tenant in the sidebar.'),
    ).toBeInTheDocument();
  });

  it('shows "not found" when the backend 404s', async () => {
    vi.stubGlobal('fetch', stubFetches({ errorStatus: 404 }));

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false });

    await waitFor(() => {
      expect(screen.getByText('Process instance not found.')).toBeInTheDocument();
    });
  });

  it('shows a visible error for a non-404 fetch failure', async () => {
    vi.stubGlobal('fetch', stubFetches({ errorStatus: 500 }));

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false });

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  it('shows mockup shell: title, metadata placeholders, completable tasks, tabs; no Download', async () => {
    vi.stubGlobal('fetch', stubFetches(mockDetail()));

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Process Instance ID: 7' })).toBeInTheDocument();
    });
    expect(screen.getByText(/Invoice Approval/)).toBeInTheDocument();
    expect(screen.getByText('Started by')).toBeInTheDocument();
    expect(screen.getByText('Updated')).toBeInTheDocument();
    expect(screen.getByText('Last milestone')).toBeInTheDocument();
    expect(screen.getByText('Revision')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Tasks I can complete' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Diagram' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Milestones' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Events' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Messages' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Tasks' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy link' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Download/ })).not.toBeInTheDocument();
    expect(
      screen.getByText(
        'No BPMN diagram is available for this instance (its process definition may have been removed).',
      ),
    ).toBeInTheDocument();
  });

  it('renders Updated and Last milestone from the GET; Revision stays an em dash', async () => {
    vi.stubGlobal(
      'fetch',
      stubFetches(
        mockDetail({
          updated_at_in_seconds: 1_700_000_100,
          last_milestone_bpmn_name: 'Approval gate',
        }),
      ),
    );

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false });

    await waitFor(() => {
      expect(screen.getByText('Approval gate')).toBeInTheDocument();
    });
    expect(screen.getByText('2023-11-14 22:15:00')).toBeInTheDocument();
    expect(screen.getByText('Revision').parentElement).toHaveTextContent('Revision—');
  });

  it('shows em dash when Updated and Last milestone are unset', async () => {
    vi.stubGlobal(
      'fetch',
      stubFetches(mockDetail({ updated_at_in_seconds: null, last_milestone_bpmn_name: '   ' })),
    );

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Process Instance ID: 7' })).toBeInTheDocument();
    });
    expect(screen.getByText('Updated').parentElement).toHaveTextContent('Updated—');
    expect(screen.getByText('Last milestone').parentElement).toHaveTextContent('Last milestone—');
    expect(screen.getByText('Revision').parentElement).toHaveTextContent('Revision—');
  });

  it('copies the current URL from Copy link', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText }, userAgent: 'test' });
    vi.stubGlobal('fetch', stubFetches(mockDetail()));

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Copy link' })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Copy link' }));
    expect(writeText).toHaveBeenCalledWith(window.location.href);
  });

  it('shows Messages empty copy and Tasks completed-by-me empty copy', async () => {
    // Radix's Tabs, like its DropdownMenu, doesn't switch under a plain
    // fireEvent.click in jsdom — use @testing-library/user-event, per the
    // map's Notes.
    const user = userEvent.setup();
    vi.stubGlobal('fetch', stubFetches(mockDetail()));

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false });

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Messages' })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('tab', { name: 'Messages' }));
    expect(screen.getByText('No messages recorded for this process instance.')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Tasks' }));
    await waitFor(() => {
      expect(
        screen.getByText('You have not completed any tasks for this process instance.'),
      ).toBeInTheDocument();
    });
  });

  it('shows terminate and suspend for an editor on a waiting instance', async () => {
    vi.stubGlobal('fetch', stubFetches(mockDetail()));

    renderWithOutlet(editorCtx);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Terminate' })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Suspend' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resume' })).not.toBeInTheDocument();
  });

  it('swaps resume in for suspend when the instance is suspended', async () => {
    vi.stubGlobal('fetch', stubFetches(mockDetail({ status: 'suspended' })));

    renderWithOutlet(editorCtx);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Resume' })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Terminate' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Suspend' })).not.toBeInTheDocument();
  });

  it('hides lifecycle buttons when the caller cannot manage processes', async () => {
    vi.stubGlobal('fetch', stubFetches(mockDetail()));

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false });

    await waitFor(() => {
      expect(screen.getByText(/Invoice Approval/)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: 'Terminate' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Suspend' })).not.toBeInTheDocument();
  });

  it('hides lifecycle buttons on a completed instance', async () => {
    vi.stubGlobal('fetch', stubFetches(mockDetail({ status: 'complete' })));

    renderWithOutlet(editorCtx);

    await waitFor(() => {
      expect(screen.getByText(/Invoice Approval/)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: 'Terminate' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Suspend' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resume' })).not.toBeInTheDocument();
  });

  it('confirms terminate via the dialog then posts and refreshes', async () => {
    const fetchMock = stubFetches(mockDetail());
    vi.stubGlobal('fetch', fetchMock);

    renderWithOutlet(editorCtx);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Terminate' })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Terminate' }));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Terminate process instance?');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Terminate' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/process-instances/7/terminate'),
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('does not post terminate when the confirmation dialog is cancelled', async () => {
    const fetchMock = stubFetches(mockDetail());
    vi.stubGlobal('fetch', fetchMock);

    renderWithOutlet(editorCtx);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Terminate' })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Terminate' }));

    const dialog = await screen.findByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('posts suspend immediately without a confirmation dialog', async () => {
    const fetchMock = stubFetches(mockDetail());
    vi.stubGlobal('fetch', fetchMock);

    renderWithOutlet(editorCtx);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Suspend' })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Suspend' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/process-instances/7/suspend'),
        expect.objectContaining({ method: 'POST' }),
      );
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });
});
