import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
import ProcessModelDetailPage from './ProcessModelDetailPage';

const DETAIL = {
  id: 'finance/invoice-approval',
  display_name: 'Invoice Approval',
  description: 'Two-step',
  group_id: 'finance',
  group_display_name: 'Finance',
  last_run_in_seconds: 1_700_000_000,
  running_now: 1,
  runs_30d: 2,
  recent_instances: [],
  files: [],
};

function renderDetail(context: SessionFixtureContext, path = '/processes/finance:invoice-approval') {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/processes/:processModelId" element={<ProcessModelDetailPage />} />
          <Route path="/process-instances/:instanceId" element={<p>Instance started</p>} />
          <Route path="/templates/:templateId" element={<p>Template modeler</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProcessModelDetailPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('prompts super-admin when All Tenants is selected and does not fetch', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    renderDetail({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: true,
    });

    expect(screen.getByText('Choose a tenant')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('lets a non-admin editor open a model using the tenant cookie', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ...DETAIL,
          recent_instances: [
            {
              id: 1042,
              started_by: 'editor',
              start_in_seconds: 1_700_000_000,
              duration_seconds: 102,
              status: 'complete',
            },
          ],
          files: [
            {
              name: 'invoice-approval.bpmn',
              size_bytes: 24576,
              updated_at_in_seconds: 1_700_000_000,
              primary: true,
            },
          ],
        }),
      }),
    );

    renderDetail({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Invoice Approval' })).toBeInTheDocument();
    });
    expect(screen.getByTestId('process-model-detail')).toBeInTheDocument();
    expect(screen.getByText('Median time')).toBeInTheDocument();
    expect(screen.getByText('Errors 30d')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start process' })).toBeDisabled();
    expect(screen.getByRole('link', { name: /Open in modeler/ })).toHaveAttribute(
      'href',
      '/processes/finance:invoice-approval/modeler/invoice-approval.bpmn',
    );

    const url = String(vi.mocked(fetch).mock.calls[0][0]);
    expect(url).toContain('/v1.0/m8flow/process-models/finance:invoice-approval');
    expect(url).not.toContain('tenantId=');

    fireEvent.click(screen.getByRole('button', { name: 'Start process' }));
    expect(vi.mocked(fetch).mock.calls).toHaveLength(1);
  });

  it('fetches detail for a concrete tenant and shows the display name', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => DETAIL,
      }),
    );

    renderDetail({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: true,
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Invoice Approval' })).toBeInTheDocument();
    });
    expect(screen.getByTestId('process-model-detail')).toBeInTheDocument();
    expect(screen.getByText('Two-step')).toBeInTheDocument();
    const url = String(vi.mocked(fetch).mock.calls[0][0]);
    expect(url).toContain('/v1.0/m8flow/process-models/finance:invoice-approval');
    expect(url).toContain('tenantId=t1');
  });

  it('shows not found when the API returns 404', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error_code: 'not_found' }),
      }),
    );

    renderDetail({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: false,
    });

    await waitFor(() => {
      expect(screen.getByText('Process model not found.')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('process-model-detail')).not.toBeInTheDocument();
  });

  it('shows an error when the API fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({}),
      }),
    );

    renderDetail({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
    });

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByRole('alert').textContent).toMatch(/failed: 500/i);
  });

  it('starts an instance and navigates for a user who can start', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        if (String(url).includes('/start') || init?.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              id: 99,
              status: 'running',
              process_model_identifier: 'finance/invoice-approval',
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...DETAIL,
            files: [
              {
                name: 'invoice-approval.bpmn',
                size_bytes: 12,
                updated_at_in_seconds: 1_700_000_000,
                primary: true,
              },
            ],
          }),
        });
      }),
    );

    renderDetail({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canManageProcesses: true,
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Invoice Approval' })).toBeInTheDocument();
    });
    const start = screen.getByRole('button', { name: 'Start process' });
    expect(start).not.toBeDisabled();
    fireEvent.click(start);
    await waitFor(() => {
      expect(screen.getByText('Instance started')).toBeInTheDocument();
    });
    const startUrl = vi
      .mocked(fetch)
      .mock.calls.map((c) => String(c[0]))
      .find((url) => url.includes('/start'));
    expect(startUrl).toContain('/v1.0/m8flow/process-models/finance:invoice-approval/start');
  });

  it('saves as a draft template and opens the template modeler for a catalog manager', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string, init?: RequestInit) => {
        const path = String(url);
        if (path.includes('/v1.0/m8flow/templates') && init?.method === 'POST') {
          return Promise.resolve({
            ok: true,
            json: async () => ({ id: 42, name: 'Invoice Approval', templateKey: 'invoice-approval' }),
          });
        }
        if (path.includes('/files/')) {
          return Promise.resolve({
            ok: true,
            text: async () => '<bpmn/>',
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...DETAIL,
            files: [
              {
                name: 'invoice-approval.bpmn',
                size_bytes: 12,
                updated_at_in_seconds: 1_700_000_000,
                primary: true,
              },
              {
                name: 'notes.txt',
                size_bytes: 4,
                updated_at_in_seconds: 1_700_000_000,
                primary: false,
              },
            ],
          }),
        });
      }),
    );

    renderDetail({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canManageProcesses: true,
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Invoice Approval' })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'More actions' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Save as template' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create template' }));
    await waitFor(() => {
      expect(screen.getByText('Template modeler')).toBeInTheDocument();
    });
    const createUrl = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => String(url).includes('/v1.0/m8flow/templates') && init?.method === 'POST');
    expect(createUrl).toBeDefined();
    const fileGets = vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => String(url).includes('/files/'))
      .map(([url]) => String(url));
    expect(fileGets).toHaveLength(1);
    expect(fileGets[0]).toContain('/files/invoice-approval.bpmn');
    expect(fileGets.some((url) => url.includes('notes.txt'))).toBe(false);
  });

  it('keeps Save as template disabled for super-admin even when they can start', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ...DETAIL,
          files: [
            {
              name: 'invoice-approval.bpmn',
              size_bytes: 12,
              updated_at_in_seconds: 1_700_000_000,
              primary: true,
            },
          ],
        }),
      }),
    );

    renderDetail({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: true,
      canManageProcesses: true,
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Invoice Approval' })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'More actions' }));
    expect(await screen.findByRole('menuitem', { name: 'Save as template' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('copies a process model and navigates to the copy overview', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (String(url).includes('/copy')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              id: 'finance/invoice-approval-copy',
              display_name: 'Invoice Approval (copy)',
              description: 'Two-step',
              group_id: 'finance',
              group_display_name: 'Finance',
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...DETAIL,
            ...(String(url).includes('invoice-approval-copy')
              ? { id: 'finance/invoice-approval-copy', display_name: 'Invoice Approval (copy)' }
              : {}),
            files: [
              {
                name: 'invoice-approval.bpmn',
                size_bytes: 12,
                updated_at_in_seconds: 1_700_000_000,
                primary: true,
              },
            ],
          }),
        });
      }),
    );

    renderDetail({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canManageProcesses: true,
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Invoice Approval' })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'More actions' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Copy' }));
    fireEvent.click(screen.getByRole('button', { name: 'Copy process model' }));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Invoice Approval (copy)' })).toBeInTheDocument();
    });
    const copyUrl = vi
      .mocked(fetch)
      .mock.calls.map((c) => String(c[0]))
      .find((url) => url.includes('/copy'));
    expect(copyUrl).toContain('/v1.0/m8flow/process-models/finance:invoice-approval/copy');
  });

  it('runs BPMN tests from the overview for a catalog manager', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (String(url).includes('/tests/run')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              all_passed: true,
              passing: [{ passed: true, bpmn_file: 'invoice-approval.bpmn', test_case_identifier: 'happy_path' }],
              failing: [],
            }),
          });
        }
        if (String(url).includes('/script-unit-tests')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ tests: [] }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...DETAIL,
            files: [
              {
                name: 'invoice-approval.bpmn',
                size_bytes: 12,
                updated_at_in_seconds: 1_700_000_000,
                primary: true,
              },
              {
                name: 'test_invoice-approval.json',
                size_bytes: 40,
                updated_at_in_seconds: 1_700_000_000,
                primary: false,
              },
            ],
          }),
        });
      }),
    );

    renderDetail({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canManageProcesses: true,
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Invoice Approval' })).toBeInTheDocument();
    });
    const run = screen.getByRole('button', { name: 'Run BPMN tests' });
    expect(run).not.toBeDisabled();
    fireEvent.click(run);
    await waitFor(() => {
      expect(screen.getByText('All 1 test passed.')).toBeInTheDocument();
    });
    const testUrl = vi
      .mocked(fetch)
      .mock.calls.map((c) => String(c[0]))
      .find((url) => url.includes('/tests/run'));
    expect(testUrl).toContain('/v1.0/m8flow/process-models/finance:invoice-approval/tests/run');
  });
});
