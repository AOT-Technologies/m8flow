import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import * as api from '@/lib/api';
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
import ProcessesPage from './ProcessesPage';

function renderWithOutlet(context: SessionFixtureContext, initial = '/processes') {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  const page = (session: SessionFixtureContext) => (
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route element={<Outlet context={session} />}>
          <Route path="/processes" element={<ProcessesPage />} />
          <Route path="/process-instances/12" element={<p>Started instance 12</p>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
  const view = render(page(context));
  return {
    ...view,
    rerenderWithContext(next: SessionFixtureContext) {
      mockUseActiveTenant.mockReturnValue(activeTenantFromContext(next));
      mockUseCapabilities.mockReturnValue(capabilitiesFromContext(next));
      view.rerender(page(next));
    },
  };
}

describe('ProcessesPage', () => {
  afterEach(() => {
    // Unmount before restoring: a late fetch would otherwise re-render the page against reset session-hook mocks.
    cleanup();
    vi.restoreAllMocks();
  });

  it('lists models across tenants for an All-Tenants super-admin', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        {
          id: 'finance/invoice-approval',
          tenant_id: 't1',
          tenant_name: 'Tenant One',
          display_name: 'Invoice Approval',
          group_id: 'finance',
          group_display_name: 'Finance',
          last_run_at: null,
          runs_30d: 0,
        },
        {
          id: 'hr/onboarding',
          tenant_id: 't2',
          tenant_name: 'Tenant Two',
          display_name: 'Onboarding',
          group_id: 'hr',
          group_display_name: 'HR',
          last_run_at: null,
          runs_30d: 0,
        },
      ],
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithOutlet({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: true,
    });

    await waitFor(() => {
      expect(screen.getByText('Invoice Approval')).toBeInTheDocument();
    });
    expect(screen.getByText('Onboarding')).toBeInTheDocument();
    expect(screen.queryByText('Choose a tenant')).not.toBeInTheDocument();
    // Tenant column disambiguates rows that can share a model identifier.
    expect(screen.getByText('Tenant One')).toBeInTheDocument();
    expect(screen.getByText('Tenant Two')).toBeInTheDocument();
    // All Tenants means "no tenant filter" -- the param must be omitted.
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('tenantId=');
  });

  it('fetches and renders models for a concrete tenant', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            id: 'finance/invoice-approval',
            display_name: 'Invoice Approval',
            group_id: 'finance',
            group_display_name: 'Finance',
            last_run_at: null,
            runs_30d: 0,
            status: 'published',
          },
        ],
      }),
    );

    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: true,
    });

    await waitFor(() => {
      expect(screen.getByText('Invoice Approval')).toBeInTheDocument();
    });
    expect(fetch).toHaveBeenCalled();
    const url = String(vi.mocked(fetch).mock.calls[0][0]);
    expect(url).toContain('/v1.0/m8flow/process-models');
    expect(url).toContain('tenantId=t1');
  });

  it('loads process owners and applies the selected owner to the model query', async () => {
    const fetchMock = vi.fn().mockImplementation((input: unknown) => {
      const url = String(input);
      if (url.includes('/process-instances/owners')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            owners: ['editor', 'admin'],
            owner_options: [
              { id: 11, username: 'editor' },
              { id: 12, username: 'admin' },
            ],
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [
          {
            id: 'finance/invoice-approval',
            display_name: 'Invoice Approval',
            group_id: 'finance',
            group_display_name: 'Finance',
            last_run_at: null,
            runs_30d: 0,
            status: 'published',
          },
        ],
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: true,
    });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Owner: All' }));
    await user.click(await screen.findByRole('menuitemradio', { name: 'editor' }));

    await waitFor(() => {
      const modelRequests = fetchMock.mock.calls
        .map((call) => String(call[0]))
        .filter((url) => url.includes('/v1.0/m8flow/process-models?'));
      expect(modelRequests[modelRequests.length - 1]).toContain('started_by_id=11');
    });
  });

  function stubOneModel() {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            id: 'finance/invoice-approval',
            display_name: 'Invoice Approval',
            group_id: 'finance',
            group_display_name: 'Finance',
            last_run_at: null,
            runs_30d: 0,
            status: 'published',
          },
        ],
      }),
    );
  }

  it('hides Start for users who cannot manage processes', async () => {
    stubOneModel();
    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: false,
      canManageProcesses: false,
    });
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument();
    // The overflow menu also offers no Delete for these users.
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }));
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).not.toBeInTheDocument();
  });

  it('shows Start for users who can manage processes', async () => {
    stubOneModel();
    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: false,
      canManageProcesses: true,
    });
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  });

  it('lets users with start permission start without catalog write actions', async () => {
    stubOneModel();
    renderWithOutlet({
      scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false,
      canManageProcesses: false, canStartProcesses: true,
    });
    expect(await screen.findByRole('button', { name: 'Start' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /new process model/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }));
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).not.toBeInTheDocument();
  });

  const modelPath = '/v1.0/m8flow/process-models/finance:invoice-approval';
  const collaborationDetail = {
    collaboration_participants: [
      { id: 'Order', name: 'Order', startable: true },
      { id: 'Fulfilment', name: 'Fulfilment', startable: false },
    ],
  };

  function renderStartFlow(loadDetail: () => Response | Promise<Response>) {
    const startRequests = vi.fn();
    const detailRequests = vi.fn<(url: string) => Response | Promise<Response>>(loadDetail);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo, init: RequestInit) => {
      const url = String(input);
      if (url.includes('/process-instances/owners')) return Response.json({ owner_options: [] });
      if (url.includes('/process-groups')) return Response.json([]);
      if (url.endsWith('/process-models?tenantId=t1')) {
        const model = {
          id: 'finance/invoice-approval', tenant_id: 't1', display_name: 'Invoice Approval',
          group_id: 'finance', group_display_name: 'Finance', status: 'published',
          last_run_at: null, runs_30d: 0,
        };
        return Response.json([model, { ...model, id: 'finance/expenses', display_name: 'Expenses' }]);
      }
      if (init.method === 'POST') {
        startRequests(url, init.body);
        return Response.json({ id: 12 });
      }
      return detailRequests(url);
    }));
    renderWithOutlet({
      scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false, canStartProcesses: true,
    });
    return { detailRequests, startRequests };
  }

  async function invoiceStartButton() {
    const row = await screen.findByRole('button', { name: /Invoice Approval/ });
    return within(row).getByRole('button', { name: 'Start' });
  }

  it('loads only the selected model detail on Start and starts a single-process model without options', async () => {
    let resolveDetail!: (detail: Response) => void;
    const detail = new Promise<Response>((resolve) => { resolveDetail = resolve; });
    const { detailRequests, startRequests } = renderStartFlow(() => detail);
    const startButton = await invoiceStartButton();
    expect(detailRequests).not.toHaveBeenCalled();

    await userEvent.click(startButton);
    expect(detailRequests).toHaveBeenCalledExactlyOnceWith(expect.stringContaining(`${modelPath}?tenantId=t1`));
    expect(startRequests).not.toHaveBeenCalled();
    for (const button of screen.getAllByRole('button', { name: 'Start' })) {
      expect(button).toBeDisabled();
    }

    resolveDetail(Response.json({ collaboration_participants: null }));
    expect(await screen.findByText('Started instance 12')).toBeInTheDocument();
    expect(startRequests).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining(`${modelPath}/start?tenantId=t1`), undefined,
    );
  });

  it('starts the participant chosen from the detail response', async () => {
    const { startRequests } = renderStartFlow(() => Response.json(collaborationDetail));
    const user = userEvent.setup();
    await user.click(await invoiceStartButton());

    const picker = within(await screen.findByRole('dialog', { name: 'Start a collaboration participant' }));
    expect(startRequests).not.toHaveBeenCalled();
    await user.selectOptions(picker.getByRole('combobox', { name: 'Executable pool' }), 'Order');
    await user.type(picker.getByLabelText(/Correlation key/), 'Order 123');
    await user.click(picker.getByRole('button', { name: 'Start' }));

    expect(await screen.findByText('Started instance 12')).toBeInTheDocument();
    expect(startRequests).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining(`${modelPath}/start?tenantId=t1`),
      JSON.stringify({ bpmn_process_id: 'Order', collaboration_correlation_key: 'Order 123' }),
    );
  });

  it('reenables Start without posting when the participant picker is cancelled', async () => {
    const { startRequests } = renderStartFlow(() => Response.json(collaborationDetail));
    const user = userEvent.setup();
    const startButton = await invoiceStartButton();
    await user.click(startButton);
    const picker = within(await screen.findByRole('dialog', { name: 'Start a collaboration participant' }));
    await user.click(picker.getByRole('button', { name: 'Cancel' }));

    expect(startRequests).not.toHaveBeenCalled();
    expect(startButton).toBeEnabled();
  });

  it('shows a detail lookup failure and reenables Start without posting', async () => {
    const { startRequests } = renderStartFlow(() => Response.json({ message: 'Process model not found' }, { status: 404 }));
    const startButton = await invoiceStartButton();
    await userEvent.click(startButton);

    expect(await screen.findByRole('alert')).toHaveTextContent('Process model not found');
    expect(startRequests).not.toHaveBeenCalled();
    expect(startButton).toBeEnabled();
  });

  it('filters by group from the Group dropdown and clears it', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input);
        if (url.includes('/v1.0/m8flow/process-groups')) {
          return {
            ok: true,
            json: async () => [
              {
                id: 'finance',
                display_name: 'Finance',
                description: 'Invoice approvals',
                model_count: 1,
                last_run_at: null,
              },
            ],
          };
        }
        return {
          ok: true,
          json: async () => [
            {
              id: 'finance/invoice-approval',
              display_name: 'Invoice Approval',
              group_id: 'finance',
              group_display_name: 'Finance',
              last_run_at: null,
              runs_30d: 0,
              status: 'published',
            },
          ],
        };
      }),
    );

    renderWithOutlet(
      {
        scopedTenantId: 't1',
        selectedTenantId: 't1',
        isSuperAdmin: true,
      },
      '/processes',
    );

    await waitFor(() => {
      expect(screen.getByText('Invoice Approval')).toBeInTheDocument();
    });

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/v1.0/m8flow/process-groups'),
      expect.anything(),
    );

    await user.click(screen.getByRole('button', { name: 'Group: All groups' }));
    await user.type(await screen.findByRole('searchbox', { name: 'Search groups' }), 'fin');
    await user.click(screen.getByRole('menuitemradio', { name: 'Finance' }));

    expect(await screen.findByRole('button', { name: 'Group: Finance' })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(await screen.findByRole('button', { name: 'Group: All groups' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument();
  });

  it.each(['/processes', '/processes?group=finance'])(
    'lets a read-only user recover from group load failures at %s',
    async (initial) => {
      const user = userEvent.setup();
      let finishRetry!: (response: Response) => void;
      const pendingRetry = new Promise<Response>((resolve) => { finishRetry = resolve; });
      const groupRequest = vi.fn()
        .mockResolvedValueOnce(Response.json({ message: 'Groups unavailable' }, { status: 503 }))
        .mockReturnValueOnce(pendingRetry)
        .mockResolvedValueOnce(Response.json([
          {
            id: 'finance',
            tenant_id: 't1',
            display_name: 'Finance',
            description: '',
            model_count: 1,
            last_run_at: null,
          },
        ]));
      vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo) => {
        const url = String(input);
        if (url.includes('/v1.0/m8flow/process-groups')) return groupRequest(url);
        if (url.includes('/v1.0/m8flow/process-models')) {
          return Response.json([
            {
              id: 'finance/invoice-approval',
              display_name: 'Invoice Approval',
              group_id: 'finance',
              group_display_name: 'Finance',
              last_run_at: null,
              runs_30d: 0,
              status: 'published',
            },
          ]);
        }
        return Response.json([]);
      }));

      renderWithOutlet({
        scopedTenantId: 't1',
        selectedTenantId: 't1',
        isSuperAdmin: false,
        canReadProcesses: true,
        canManageProcesses: false,
        canManageProcessModels: false,
        canCreateProcessGroups: false,
        canUpdateProcessGroups: false,
        canDeleteProcessGroups: false,
      }, initial);

      expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load process groups');
      expect(screen.getByText('Invoice Approval')).toBeInTheDocument();
      expect(screen.queryByTestId('processes-new-group-button')).not.toBeInTheDocument();
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      const groupLabel = initial.includes('?group=') ? 'Finance' : 'All groups';
      expect(screen.getByRole('button', { name: `Group: ${groupLabel}` })).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: 'Retry' }));
      expect(screen.getByRole('status')).toHaveTextContent(/Group: Loading/);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
      expect(screen.getByText('Invoice Approval')).toBeInTheDocument();
      expect(groupRequest).toHaveBeenCalledTimes(2);

      await act(async () => {
        finishRetry(Response.json({ message: 'Still unavailable' }, { status: 503 }));
      });
      expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load process groups');
      if (initial.includes('?group=')) {
        expect(screen.getByRole('button', { name: 'Group: Finance' })).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Clear' }));
        expect(screen.getByRole('button', { name: 'Group: All groups' })).toBeInTheDocument();
        expect(screen.getByRole('alert')).toHaveTextContent('Failed to load process groups');
      }

      await user.click(screen.getByRole('button', { name: 'Retry' }));
      await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
      expect(groupRequest).toHaveBeenCalledTimes(3);
      for (const [url] of groupRequest.mock.calls) {
        expect(url).toContain('/v1.0/m8flow/process-groups?tenantId=t1');
      }
      await user.click(screen.getByRole('button', { name: 'Group: All groups' }));
      await user.click(await screen.findByRole('menuitemradio', { name: 'Finance' }));
      expect(screen.getByRole('button', { name: 'Group: Finance' })).toBeInTheDocument();
      expect(screen.getByText('Invoice Approval')).toBeInTheDocument();
      expect(screen.queryByTestId('processes-new-group-button')).not.toBeInTheDocument();
    },
  );

  it.each([
    { lateFails: false, afterRecovery: false },
    { lateFails: true, afterRecovery: false },
    { lateFails: false, afterRecovery: true },
    { lateFails: true, afterRecovery: true },
  ])('scopes group options during tenant switches (late failure: $lateFails, after recovery: $afterRecovery)', async ({ lateFails, afterRecovery }) => {
    const user = userEvent.setup();
    const groupRequests = vi.spyOn(api, 'fetchProcessGroups');
    const finishModelRequests: ((response: Response) => void)[] = [];
    let finishOldRequest!: (response: Response) => void;
    let finishCurrentRequest!: (response: Response) => void;
    const oldRequest = new Promise<Response>((resolve) => { finishOldRequest = resolve; });
    const currentRequest = new Promise<Response>((resolve) => { finishCurrentRequest = resolve; });
    const group = (id: string, display_name: string) => ({
      id, display_name, description: '', model_count: 1, last_run_at: null,
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/process-groups')) {
        if (url.includes('tenantId=t2')) return oldRequest;
        if (url.includes('tenantId=t3')) return currentRequest;
        return Promise.resolve(Response.json([
          group('finance', 'Tenant One Finance'), group('private', 'Tenant One Only'),
        ]));
      }
      if (url.includes('/process-models')) {
        // Leave the previous tenant's models in state while the new list loads.
        if (!url.includes('tenantId=t1')) {
          return new Promise<Response>((resolve) => { finishModelRequests.push(resolve); });
        }
        return Promise.resolve(Response.json([{
          id: 'finance/invoice', display_name: 'Invoice Approval', group_id: 'finance',
          group_display_name: 'Tenant One Finance', last_run_at: null, runs_30d: 0,
        }]));
      }
      return Promise.resolve(Response.json([]));
    });
    vi.stubGlobal('fetch', fetchMock);
    const session: SessionFixtureContext = {
      scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false,
      canReadProcesses: true, canManageProcesses: false, canManageProcessModels: false,
      canCreateProcessGroups: false, canUpdateProcessGroups: false, canDeleteProcessGroups: false,
    };
    const view = renderWithOutlet(session, '/processes?group=finance');
    await screen.findByRole('button', { name: 'Group: Tenant One Finance' });
    await screen.findByText('Invoice Approval');
    expect(screen.queryByTestId('processes-new-group-button')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Group: Tenant One Finance' }));
    expect(await screen.findByRole('menuitemradio', { name: 'Tenant One Only' })).toBeInTheDocument();

    view.rerenderWithContext({ ...session, scopedTenantId: 't2', selectedTenantId: 't2' });
    expect(screen.queryByRole('menuitemradio', { name: /Tenant One/ })).not.toBeInTheDocument();
    expect(screen.getByRole('menu')).toHaveAccessibleName('Group: finance');
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Group: finance' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(/Group: Loading/);
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();

    view.rerenderWithContext({ ...session, scopedTenantId: 't3', selectedTenantId: 't3' });
    await user.click(screen.getByRole('button', { name: 'Group: finance' }));
    const recover = async () => {
      await act(async () => {
        finishCurrentRequest(Response.json([group('finance', 'Tenant Three Finance')]));
      });
      expect(await screen.findByRole('menuitemradio', { name: 'Tenant Three Finance' })).toBeInTheDocument();
      expect(screen.getByRole('menu')).toHaveAccessibleName('Group: Tenant Three Finance');
      expect(screen.queryByRole('status', { hidden: true })).not.toBeInTheDocument();
    };
    if (afterRecovery) await recover();

    await act(async () => {
      finishOldRequest(lateFails
        ? Response.json({ message: 'Old tenant failed' }, { status: 503 })
        : Response.json([group('finance', 'Late Tenant Two Finance'), group('late', 'Late Tenant Two Only')]));
      // Wait for JSON parsing and the cancelled request's handlers before asserting.
      await Promise.allSettled([groupRequests.mock.results[1].value]);
    });
    expect(screen.queryByRole('menuitemradio', { name: /Tenant One|Tenant Two/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('alert', { hidden: true })).not.toBeInTheDocument();
    if (afterRecovery) {
      expect(screen.getByRole('menu')).toHaveAccessibleName('Group: Tenant Three Finance');
      expect(screen.queryByRole('status', { hidden: true })).not.toBeInTheDocument();
    } else {
      expect(screen.getByRole('menu')).toHaveAccessibleName('Group: finance');
      expect(screen.getByRole('status', { hidden: true })).toHaveTextContent(/Group: Loading/);
      await recover();
    }
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/process-groups'))
      .map(([url]) => String(url))).toEqual([
      expect.stringContaining('tenantId=t1'),
      expect.stringContaining('tenantId=t2'),
      expect.stringContaining('tenantId=t3'),
    ]);
    await user.click(screen.getByRole('menuitemradio', { name: 'All groups' }));
    expect(screen.getByRole('button', { name: 'Group: All groups' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Clear' })).not.toBeInTheDocument();
    await act(async () => {
      finishModelRequests.forEach((finish) => finish(Response.json([])));
    });
    await screen.findByText('No process models');
  });

  it('clears a previous tenant group error while the next tenant loads', async () => {
    let finishGroups!: (response: Response) => void;
    const pendingGroups = new Promise<Response>((resolve) => { finishGroups = resolve; });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/process-groups')) {
        return url.includes('tenantId=t1')
          ? Promise.resolve(Response.json({}, { status: 503 })) : pendingGroups;
      }
      return Promise.resolve(Response.json([]));
    }));
    const session: SessionFixtureContext = {
      scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false,
      canManageProcesses: false,
    };
    const view = renderWithOutlet(session);
    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load process groups');

    view.rerenderWithContext({ ...session, scopedTenantId: 't2', selectedTenantId: 't2' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(/Group: Loading/);
    await act(async () => { finishGroups(Response.json([])); });
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('hides the previous tenant groups in an open Manage groups dialog', async () => {
    let finishGroups!: (response: Response) => void;
    const pendingGroups = new Promise<Response>((resolve) => { finishGroups = resolve; });
    const group = (display_name: string) => ({
      id: 'finance', display_name, description: '', model_count: 0, last_run_at: null,
    });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/process-groups')) {
        return url.includes('tenantId=t1')
          ? Promise.resolve(Response.json([group('Tenant One Finance')])) : pendingGroups;
      }
      return Promise.resolve(Response.json([]));
    }));
    const session: SessionFixtureContext = {
      scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false, canManageProcesses: true,
    };
    const view = renderWithOutlet(session);
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
    fireEvent.click(screen.getByTestId('processes-new-group-button'));
    const form = await screen.findByRole('dialog', { name: 'New process group' });
    fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }));
    const dialog = await screen.findByRole('dialog', { name: 'Manage groups' });
    expect(within(dialog).getByText('Tenant One Finance')).toBeInTheDocument();

    view.rerenderWithContext({ ...session, scopedTenantId: 't2', selectedTenantId: 't2' });
    expect(within(dialog).queryByText('Tenant One Finance')).not.toBeInTheDocument();
    await act(async () => { finishGroups(Response.json([group('Tenant Two Finance')])); });
    expect(await within(dialog).findByText('Tenant Two Finance')).toBeInTheDocument();
    expect(within(dialog).queryByText('Tenant One Finance')).not.toBeInTheDocument();
  });

  it('hides Manage groups for All-Tenants super-admin and shows it when a tenant is selected', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input);
        if (url.includes('/v1.0/m8flow/process-groups')) {
          return {
            ok: true,
            json: async () => [
              {
                id: 'finance',
                display_name: 'Finance',
                description: 'Invoice approvals',
                model_count: 1,
                last_run_at: null,
              },
            ],
          };
        }
        return {
          ok: true,
          json: async () => [
            {
              id: 'finance/invoice-approval',
              display_name: 'Invoice Approval',
              group_id: 'finance',
              group_display_name: 'Finance',
              last_run_at: null,
              runs_30d: 0,
              status: 'published',
            },
          ],
        };
      }),
    );

    const allTenants = renderWithOutlet(
      {
        scopedTenantId: null,
        selectedTenantId: null,
        isSuperAdmin: true,
        canManageProcesses: true,
      },
      '/processes',
    );
    // The list now renders under All Tenants; only the WRITE affordances stay
    // hidden, because a create must land in exactly one tenant.
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'New process model' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('processes-new-group-button')).not.toBeInTheDocument();
    allTenants.unmount();

    const scopedSa = renderWithOutlet(
      {
        scopedTenantId: 't1',
        selectedTenantId: 't1',
        isSuperAdmin: true,
        canManageProcesses: true,
      },
      '/processes',
    );
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'New process model' })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('processes-new-group-button'));
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'New process group' })).toBeInTheDocument());
    scopedSa.unmount();

    renderWithOutlet(
      {
        scopedTenantId: 't1',
        selectedTenantId: 't1',
        isSuperAdmin: false,
        canManageProcesses: true,
      },
      '/processes',
    );
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'New process model' })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('processes-new-group-button'));
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'New process group' })).toBeInTheDocument());
  });

  it('hides publish lifecycle actions from a viewer', async () => {
    // A viewer has canManageProcesses=true (it holds `create` on
    // /process-instances) but cannot write process models. Gating the
    // lifecycle on canManageProcesses showed viewers a Publish/Pause they
    // would get a 403 on.
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [
          {
            id: 'finance/invoice-approval',
            display_name: 'Invoice Approval',
            group_id: 'finance',
            group_display_name: 'Finance',
            last_run_at: null,
            runs_30d: 0,
            status: 'published',
          },
        ],
      }),
    );

    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: false,
      canManageProcesses: true,
      canManageProcessModels: false,
    });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());

    await user.click(screen.getAllByRole('button', { name: 'More actions' })[0]);
    await screen.findByRole('menuitem', { name: 'Open' });
    expect(screen.queryByRole('menuitem', { name: 'Pause' })).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Unpublish' })).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Publish' })).not.toBeInTheDocument();
  });

  it('keeps Publish for a versioned model while its permissions are re-checked', async () => {
    // A status change refetches the list. Publish must not vanish until the
    // new permissions-check answers: the grant doesn't depend on the status.
    const user = userEvent.setup();
    let status = 'published';
    let permissionChecks = 0;
    const reply = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => body });
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/permissions-check')) {
        permissionChecks += 1;
        if (permissionChecks > 1) return new Promise(() => {}); // the re-check is still pending
        const paths = Object.keys(JSON.parse(String(init?.body)).requests_to_check);
        return reply({ results: Object.fromEntries(paths.map((path) => [path, { POST: true }])) });
      }
      if (init?.method === 'PUT') {
        status = 'draft';
        return reply({});
      }
      return reply(url.includes('/process-models') ? [{
        id: 'finance/invoice-approval', display_name: 'Invoice Approval', group_id: 'finance',
        group_display_name: 'Finance', last_run_at: null, runs_30d: 0, status, working_revision: 'r1',
      }] : []);
    }));
    renderWithOutlet({
      scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false,
      canManageProcesses: true, canManageProcessModels: true,
    });
    await screen.findByRole('button', { name: 'Start' });

    await user.click(screen.getByRole('button', { name: 'More actions' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Unpublish' }));
    await screen.findByText('Draft');
    await waitFor(() => expect(permissionChecks).toBe(2));

    await user.click(screen.getByRole('button', { name: 'More actions' }));
    expect(await screen.findByRole('menuitem', { name: 'Publish' })).toBeInTheDocument();
  });

  it('opens the New process group form from the page header; Cancel shows Manage groups', async () => {
    stubOneModel();
    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: false,
      canManageProcesses: true,
    });
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('processes-new-group-button'));
    const form = await screen.findByRole('dialog', { name: 'New process group' });
    fireEvent.click(within(form).getByRole('button', { name: 'Cancel' }));

    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: 'Manage groups' })).toBeInTheDocument(),
    );
  });

  it('closes the groups modal after creating a group and filters to it', async () => {
    const created = {
      id: 'operations',
      display_name: 'Operations',
      description: '',
      model_count: 0,
      last_run_at: null,
    };
    const finance = { ...created, id: 'finance', display_name: 'Finance', model_count: 1 };
    let groupGets = 0;
    let serverGroups: (typeof created)[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input);
        if (url.includes('/v1.0/m8flow/process-groups')) {
          if (init?.method === 'POST') {
            // Server-side list now includes a concurrently created group too.
            serverGroups = [finance, created];
            return { ok: true, json: async () => created };
          }
          groupGets += 1;
          return { ok: true, json: async () => serverGroups };
        }
        if (url.includes('operations')) {
          return { ok: true, json: async () => [] };
        }
        return {
          ok: true,
          json: async () => [
            {
              id: 'finance/invoice-approval',
              display_name: 'Invoice Approval',
              group_id: 'finance',
              group_display_name: 'Finance',
              last_run_at: null,
              runs_30d: 0,
              status: 'published',
            },
          ],
        };
      }),
    );
    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: false,
      canManageProcesses: true,
    });
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('processes-new-group-button'));
    const dialog = await screen.findByRole('dialog', { name: 'New process group' });
    fireEvent.change(within(dialog).getByLabelText('Process group display name'), {
      target: { value: 'Operations' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create group' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(await screen.findByText('No models in this group')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();

    expect(screen.getByRole('button', { name: 'Group: Operations' })).toBeInTheDocument();

    // Create refetches the list, so the server list (not the local merge) wins.
    await waitFor(() => expect(groupGets).toBe(2));
    fireEvent.click(screen.getByTestId('processes-new-group-button'));
    const reopened = await screen.findByRole('dialog', { name: 'New process group' });
    fireEvent.click(within(reopened).getByRole('button', { name: 'Cancel' }));
    const picker = await screen.findByRole('dialog', { name: 'Manage groups' });
    expect(await within(picker).findByText('Finance')).toBeInTheDocument();
    expect(within(picker).getByText('Operations')).toBeInTheDocument();
  });

  it('hides the header Manage groups action without group write permissions', async () => {
    stubOneModel();
    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: false,
      canManageProcesses: false,
    });
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.queryByTestId('processes-new-group-button')).not.toBeInTheDocument();
  });

  it('offers a way out of New process model when no process groups exist', async () => {
    // Both the page's model list and the dialog's group list come back empty.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: false,
      canManageProcesses: true,
    });

    await waitFor(() => expect(screen.getByText('No process models')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: 'New process model' })[0]);

    // Dead end without this: the empty group list left nothing to click.
    const escape = await screen.findByTestId('create-process-model-new-group-button');
    fireEvent.click(escape);

    // Lands straight on the create form, not on the empty group list.
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: 'New process group' })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('button', { name: 'Create process model' })).not.toBeInTheDocument();
  });
});
