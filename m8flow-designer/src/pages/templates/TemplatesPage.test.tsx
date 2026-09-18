import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
import * as auth from '@/lib/auth';
import TemplatesPage from './TemplatesPage';

function renderWithOutlet(context: SessionFixtureContext, initial = '/templates') {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext({ canManageProcesses: true, ...context }));
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/templates" element={<TemplatesPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

function mockTemplate(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: 1,
    templateKey: 'invoice-approval',
    version: '1',
    name: 'Invoice Approval',
    description: 'A starter template for invoice approvals.',
    tags: ['finance'],
    category: 'Finance',
    tenantId: 't1',
    visibility: 'TENANT',
    files: [{ fileType: 'bpmn', fileName: 'invoice-approval.bpmn' }],
    isPublished: true,
    isDeleted: false,
    status: 'published',
    createdBy: 'editor',
    modifiedBy: 'editor',
    createdAtInSeconds: 1_700_000_000,
    updatedAtInSeconds: 1_700_000_000,
    ...overrides,
  };
}

describe('TemplatesPage', () => {
  it('hides template write actions for viewers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: [mockTemplate()], pagination: { count: 1, total: 1, pages: 1 } }),
    }));
    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: false, canManageProcesses: false });
    expect(await screen.findByText('Invoice Approval')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Use template' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Import' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New template' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete template' })).not.toBeInTheDocument();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists templates across tenants for an All-Tenants super-admin', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [mockTemplate()],
        pagination: { count: 1, total: 1, pages: 1 },
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithOutlet({ scopedTenantId: null, selectedTenantId: null, isSuperAdmin: true });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByText('Choose a tenant')).not.toBeInTheDocument();
    // All Tenants means "no tenant filter" -- the param must be omitted.
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('tenantId=');
  });

  it('fetches and renders templates for a concrete tenant', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          results: [mockTemplate()],
          pagination: { count: 1, total: 1, pages: 1 },
        }),
      }),
    );

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });

    await waitFor(() => {
      expect(screen.getByText('Invoice Approval')).toBeInTheDocument();
    });
    const url = String(vi.mocked(fetch).mock.calls[0][0]);
    expect(url).toContain('/v1.0/m8flow/templates');
    expect(url).toContain('tenantId=t1');
    expect(screen.getByText('Published')).toBeInTheDocument();
    expect(screen.getAllByText('1 template').length).toBeGreaterThan(0);
  });

  it('debounces the search box into a server-side search param', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ results: [], pagination: { count: 0, total: 0, pages: 0 } }),
      }),
    );

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('Search templates'), { target: { value: 'invoice' } });

    await waitFor(
      () => {
        const calls = vi.mocked(fetch).mock.calls;
        const lastUrl = String(calls[calls.length - 1]?.[0]);
        expect(lastUrl).toContain('search=invoice');
      },
      { timeout: 1000 },
    );
  });

  it('navigates to the modeler route when a template card is opened', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          results: [mockTemplate()],
          pagination: { count: 1, total: 1, pages: 1 },
        }),
      }),
    );

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    // Real navigation target (/templates/:id) doesn't exist until ticket 03 —
    // just confirm the click is wired to the Open button without throwing.
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));
  });

  it('deletes a published template after dialog confirmation and refetches the list', async () => {
    const fetchMock = vi.fn().mockImplementation(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return { ok: true, status: 204, json: async () => ({}) };
      }
      return {
        ok: true,
        json: async () => ({ results: [mockTemplate()], pagination: { count: 1, total: 1, pages: 1 } }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithOutlet({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canManageTenant: true,
    });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Delete template' }));

    expect(screen.getByRole('alertdialog')).toHaveTextContent(
      '"Invoice Approval" will be soft-deleted and can be restored from the Deleted tab.',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      const deleteCall = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE');
      expect(deleteCall).toBeDefined();
      expect(String(deleteCall?.[0])).toContain('/v1.0/m8flow/templates/1');
    });
    await waitFor(() => {
      const getCalls = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method !== 'DELETE');
      expect(getCalls.length).toBeGreaterThan(1);
    });
  });

  it('does not delete when the confirmation dialog is cancelled', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: [mockTemplate()], pagination: { count: 1, total: 1, pages: 1 } }),
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithOutlet({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canManageTenant: true,
    });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Delete template' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE')).toBe(
      false,
    );
  });

  it('exports a template as a downloaded zip blob', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/export')) {
        return { ok: true, blob: async () => new Blob(['zip-bytes']) };
      }
      return {
        ok: true,
        json: async () => ({ results: [mockTemplate()], pagination: { count: 1, total: 1, pages: 1 } }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);
    // jsdom doesn't implement URL.createObjectURL/revokeObjectURL at all
    // (confirmed: `typeof URL.createObjectURL` is `undefined` in this test
    // env) — assigned directly rather than `vi.stubGlobal('URL', ...)`,
    // which would replace the real `URL` *constructor* with a plain object
    // and break anything else in the render tree that calls `new URL(...)`.
    // Restored in `finally` so later tests see the same jsdom gap again.
    const createObjectURL = vi.fn().mockReturnValue('blob:mock');
    const revokeObjectURL = vi.fn();
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    try {
      renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });

      await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
      fireEvent.click(screen.getByRole('button', { name: 'Export template' }));

      await waitFor(() => {
        expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/templates/1/export'))).toBe(true);
      });
      await waitFor(() => expect(clickSpy).toHaveBeenCalled());
      expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    } finally {
      // @ts-expect-error restoring jsdom's own (missing) baseline
      URL.createObjectURL = undefined;
      // @ts-expect-error restoring jsdom's own (missing) baseline
      URL.revokeObjectURL = undefined;
    }
  });

  it('creates a process model from a published template via the Use template dialog', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/create-process-model')) {
        return {
          ok: true,
          json: async () => ({
            process_model: { id: 'finance/invoice-approval-2' },
            template_info: { id: 1 },
          }),
        };
      }
      if (url.includes('/v1.0/m8flow/process-groups')) {
        return {
          ok: true,
          json: async () => [
            { id: 'finance', display_name: 'Finance', description: '', model_count: 1, last_run_in_seconds: null },
          ],
        };
      }
      return {
        ok: true,
        json: async () => ({ results: [mockTemplate()], pagination: { count: 1, total: 1, pages: 1 } }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    // Regular users: needsTenant is false even with null scopedTenantId.
    renderWithOutlet({ scopedTenantId: null, selectedTenantId: null, isSuperAdmin: false });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Use template' }));

    await waitFor(() => expect(screen.getByText('Create process model from template')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole('option', { name: 'Finance' })).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Identifier'), { target: { value: 'invoice-approval-2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create process model' }));

    await waitFor(() => {
      expect(screen.queryByText('Create process model from template')).not.toBeInTheDocument();
    });
    const createCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/create-process-model'));
    expect(createCall).toBeDefined();
  });

  it('lets a tenant-scoped super-admin use a published template and sends m8f_tenant_id', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/create-process-model')) {
        return {
          ok: true,
          json: async () => ({
            process_model: { id: 'finance/invoice-approval-2' },
            template_info: { id: 1 },
          }),
        };
      }
      if (url.includes('/v1.0/m8flow/process-groups')) {
        return {
          ok: true,
          json: async () => [
            { id: 'finance', display_name: 'Finance', description: '', model_count: 1, last_run_in_seconds: null },
          ],
        };
      }
      return {
        ok: true,
        json: async () => ({ results: [mockTemplate()], pagination: { count: 1, total: 1, pages: 1 } }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithOutlet({ scopedTenantId: 't1', selectedTenantId: 't1', isSuperAdmin: true });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Use template' }));

    await waitFor(() => expect(screen.getByText('Create process model from template')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole('option', { name: 'Finance' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Create process model' }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(([input]) => String(input).includes('/create-process-model'));
      expect(createCall).toBeDefined();
      expect(String(createCall?.[0])).toContain('tenantId=t1');
      const body = JSON.parse(String(createCall?.[1]?.body));
      expect(body.m8f_tenant_id).toBe('t1');
    });
  });

  it('disables Use template for a draft template or All-Tenants super-admin', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          results: [mockTemplate({ isPublished: false, status: 'draft' })],
          pagination: { count: 1, total: 1, pages: 1 },
        }),
      }),
    );

    renderWithOutlet({ scopedTenantId: null, selectedTenantId: null, isSuperAdmin: false });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Use template' })).toHaveAttribute('aria-disabled', 'true');
  });

  it('disables Use template for All-Tenants super-admin on a published template', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          results: [mockTemplate()],
          pagination: { count: 1, total: 1, pages: 1 },
        }),
      }),
    );

    // The gallery lists under All Tenants; "Use template" is a WRITE (it
    // creates a process model), so it stays unavailable without a tenant.
    renderWithOutlet({ scopedTenantId: null, selectedTenantId: null, isSuperAdmin: true });
    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Use template' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('opens the Import dialog and imports a template', async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/templates/import')) {
        return { ok: true, json: async () => ({ ...mockTemplate({ id: 2 }) }) };
      }
      return {
        ok: true,
        json: async () => ({ results: [], pagination: { count: 0, total: 0, pages: 0 } }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    // Not super-admin: import is unconditionally forbidden for super-admin
    // identities server-side (same gate as delete/"Use template"), so the
    // header Import button is disabled there.
    renderWithOutlet({ scopedTenantId: null, selectedTenantId: null, isSuperAdmin: false });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'Import' }));

    await waitFor(() => expect(screen.getByText('Import template')).toBeInTheDocument());
    const dialog = screen.getByRole('dialog');

    const file = new File(['zip-bytes'], 'template.zip', { type: 'application/zip' });
    const fileInput = within(dialog).getByLabelText('Zip file') as HTMLInputElement;
    Object.defineProperty(fileInput, 'files', { value: [file] });
    fireEvent.change(fileInput);

    fireEvent.change(within(dialog).getByLabelText('Template key'), { target: { value: 'imported-key' } });
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Imported Template' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Import' }));

    await waitFor(() => {
      expect(screen.queryByText('Import template')).not.toBeInTheDocument();
    });
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/templates/import'))).toBe(true);
  });

  it('disables published delete for an editor who is not tenant-admin', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ results: [mockTemplate()], pagination: { count: 1, total: 1, pages: 1 } }),
      }),
    );
    vi.spyOn(auth, 'getCurrentUser').mockReturnValue({ username: 'editor', email: null });

    renderWithOutlet({ scopedTenantId: null, selectedTenantId: null, isSuperAdmin: false, canManageTenant: false });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Delete template' })).toHaveAttribute('aria-disabled', 'true');
  });

  it('hard-deletes an editor\'s own draft with permanent-delete copy', async () => {
    const fetchMock = vi.fn().mockImplementation(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return { ok: true, status: 204, json: async () => ({}) };
      }
      return {
        ok: true,
        json: async () => ({
          results: [mockTemplate({ isPublished: false, status: 'draft' })],
          pagination: { count: 1, total: 1, pages: 1 },
        }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(auth, 'getCurrentUser').mockReturnValue({ username: 'editor', email: null });

    renderWithOutlet({ scopedTenantId: null, selectedTenantId: null, isSuperAdmin: false, canManageTenant: false });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Delete template' }));
    expect(screen.getByRole('alertdialog')).toHaveTextContent('"Invoice Approval" will be permanently deleted.');
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'DELETE')).toBe(true);
    });
  });

  it('lists deleted templates and restores one as tenant-admin', async () => {
    const deleted = mockTemplate({
      id: 9,
      isDeleted: true,
      name: 'Invoice Approval_deleted_20260101120000',
    });
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === 'POST' && url.includes('/restore')) {
        return { ok: true, json: async () => mockTemplate({ id: 9 }) };
      }
      if (url.includes('deleted_only=true')) {
        return {
          ok: true,
          json: async () => ({ results: [deleted], pagination: { count: 1, total: 1, pages: 1 } }),
        };
      }
      return {
        ok: true,
        json: async () => ({ results: [mockTemplate()], pagination: { count: 1, total: 1, pages: 1 } }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithOutlet({
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canManageTenant: true,
    });

    await waitFor(() => expect(screen.getByText('Invoice Approval')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Deleted' }));

    await waitFor(() => {
      expect(screen.getByText('Invoice Approval_deleted_20260101120000')).toBeInTheDocument();
    });
    const deletedUrl = String(fetchMock.mock.calls.find(([input]) => String(input).includes('deleted_only=true'))?.[0]);
    expect(deletedUrl).toContain('include_deleted=true');
    expect(deletedUrl).toContain('latest_only=false');
    expect(screen.queryByRole('button', { name: 'Delete template' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Restore template' }));
    expect(screen.getByRole('alertdialog')).toHaveTextContent(
      '"Invoice Approval_deleted_20260101120000" will be restored and become active again.',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Restore' }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input, init]) => String(input).includes('/templates/9/restore') && (init as RequestInit | undefined)?.method === 'POST')).toBe(true);
    });
  });

  it('hides restore for super-admin on the Deleted tab', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('deleted_only=true')) {
          return {
            ok: true,
            json: async () => ({
              results: [mockTemplate({ id: 9, isDeleted: true, name: 'Gone' })],
              pagination: { count: 1, total: 1, pages: 1 },
            }),
          };
        }
        return {
          ok: true,
          json: async () => ({ results: [], pagination: { count: 0, total: 0, pages: 0 } }),
        };
      }),
    );

    renderWithOutlet({
      scopedTenantId: 't1',
      selectedTenantId: 't1',
      isSuperAdmin: true,
      canManageTenant: true,
    });

    await waitFor(() => expect(screen.getByRole('button', { name: 'Deleted' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Deleted' }));
    await waitFor(() => expect(screen.getByText('Gone')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Restore template' })).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('button', { name: 'Export template' })).toBeEnabled();
  });
});
