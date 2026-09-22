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
import ProcessesPage from './ProcessesPage';

function renderWithOutlet(context: SessionFixtureContext, initial = '/processes') {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/processes" element={<ProcessesPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProcessesPage', () => {
  afterEach(() => {
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
          last_run_in_seconds: null,
          runs_30d: 0,
        },
        {
          id: 'hr/onboarding',
          tenant_id: 't2',
          tenant_name: 'Tenant Two',
          display_name: 'Onboarding',
          group_id: 'hr',
          group_display_name: 'HR',
          last_run_in_seconds: null,
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
            last_run_in_seconds: null,
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
        return Promise.resolve({ ok: true, json: async () => ({ owners: ['editor', 'admin'] }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [
          {
            id: 'finance/invoice-approval',
            display_name: 'Invoice Approval',
            group_id: 'finance',
            group_display_name: 'Finance',
            last_run_in_seconds: null,
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
    await user.click(screen.getByRole('button', { name: 'Owner: All owners' }));
    await user.click(await screen.findByRole('menuitem', { name: 'editor' }));

    await waitFor(() => {
      const modelRequests = fetchMock.mock.calls
        .map((call) => String(call[0]))
        .filter((url) => url.includes('/v1.0/m8flow/process-models?'));
      expect(modelRequests[modelRequests.length - 1]).toContain('started_by=editor');
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
            last_run_in_seconds: null,
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

  it('opens the groups picker and applies a group filter', async () => {
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
                last_run_in_seconds: null,
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
              last_run_in_seconds: null,
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

    // "Browse groups" was removed; the "Showing [scope]" pill opens the picker.
    fireEvent.click(screen.getByRole('button', { name: /All groups/ }));

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: 'Process groups' })).toBeInTheDocument();
    });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/v1.0/m8flow/process-groups'),
      expect.anything(),
    );

    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /Finance/ }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();
  });

  it('hides New group for All-Tenants super-admin and shows it when a tenant is selected', async () => {
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
                last_run_in_seconds: null,
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
              last_run_in_seconds: null,
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
    fireEvent.click(screen.getByRole('button', { name: /All groups/ }));
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Process groups' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /New group/i })).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', { name: /All groups/ }));
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Process groups' })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /New group/i })).toBeInTheDocument();
  });

  it('hides publish lifecycle actions from a viewer (M8F-508)', async () => {
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
            last_run_in_seconds: null,
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
});
