import { useLayoutEffect } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, MemoryRouter, Outlet, Route, RouterProvider, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
const mockFetchNamedValues = vi.fn();
const mockFetchNamedValue = vi.fn();
const mockCreateNamedValue = vi.fn();
const mockUpdateNamedValue = vi.fn();
const mockDeleteNamedValue = vi.fn();
const mockFetchNatsEmailStatus = vi.fn();

vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => ({ tenants: [
    { id: 'tenant-1', name: 'Tenant 1' },
    { id: 'tenant-2', name: 'Tenant 2' },
  ] }),
}));

vi.mock('@/lib/namedValuesApi', () => ({
  fetchNamedValues: (...args: unknown[]) => mockFetchNamedValues(...args),
  fetchNamedValue: (...args: unknown[]) => mockFetchNamedValue(...args),
  createNamedValue: (...args: unknown[]) => mockCreateNamedValue(...args),
  updateNamedValue: (...args: unknown[]) => mockUpdateNamedValue(...args),
  deleteNamedValue: (...args: unknown[]) => mockDeleteNamedValue(...args),
  namedValuesErrorMessage: (_error: unknown, fallback: string) => fallback,
}));

vi.mock('@/lib/secretsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/secretsApi')>('@/lib/secretsApi');
  return { ...actual, fetchNatsEmailStatus: (...args: unknown[]) => mockFetchNatsEmailStatus(...args) };
});

import NamedValueEditPage from './NamedValueEditPage';
import NamedValuesPage from './NamedValuesPage';
import { ApiError } from '@/lib/api';

const ROW = {
  id: 'var-1', tenantId: 'tenant-1', name: 'api_endpoint', description: 'Endpoint',
  isSensitive: false, isConfigured: true, value: 'https://example.test',
  createdAt: null, updatedAt: null,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function renderWithTenant(path: string, admin: boolean, editable = false) {
  const commits: string[] = [];
  mockUseCapabilities.mockReturnValue({
    canReadNamedValues: true,
    canReadNamedValueItems: true,
    canCreateNamedValues: editable,
    canUpdateNamedValues: editable,
    canDeleteNamedValues: editable,
  });
  function TenantPage({ tenantId }: { tenantId: string }) {
    mockUseActiveTenant.mockReturnValue({
      activeTenantId: admin ? null : tenantId,
      scopedTenantId: admin ? tenantId : null,
      isSuperAdmin: admin,
    });
    // Capture the committed DOM before passive fetch effects can hide stale data.
    useLayoutEffect(() => {
      commits.push([
        document.body.textContent,
        ...Array.from(document.querySelectorAll('input, textarea'), (input) =>
          (input as HTMLInputElement | HTMLTextAreaElement).value),
      ].join('\n'));
    });
    return (
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/configuration/named-values" element={<NamedValuesPage />} />
          <Route path="/configuration/named-values/new" element={<NamedValueEditPage />} />
          <Route path="/configuration/named-values/:id" element={<NamedValueEditPage />} />
        </Routes>
      </MemoryRouter>
    );
  }
  const view = render(<TenantPage tenantId="tenant-1" />);
  return {
    commits,
    switchTenant(tenantId: string) {
      commits.length = 0;
      view.rerender(<TenantPage tenantId={tenantId} />);
    },
  };
}

const NATS_CONFIGURED = {
  configured: true,
  requiredKeys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  optionalKeys: [],
  missingKeys: [],
  unreadableKeys: [],
  configuredKeys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  waitingCount: 0,
};

const NATS_MISSING = {
  ...NATS_CONFIGURED,
  configured: false,
  missingKeys: ['NATS_SMTP_HOST', 'NATS_SMTP_FROM_EMAIL'],
  configuredKeys: [],
};

function renderAt(
  path: string | { pathname: string; state: unknown },
  options: {
    admin?: boolean;
    activeTenant?: string | null;
    scopedTenant?: string | null;
    [key: string]: unknown;
  } = {},
) {
  const { admin = false, activeTenant = 'tenant-1', scopedTenant = null, ...caps } = options;
  mockUseActiveTenant.mockReturnValue({
    activeTenantId: activeTenant,
    scopedTenantId: scopedTenant,
    isSuperAdmin: admin,
  });
  mockUseCapabilities.mockReturnValue({
    canReadNamedValues: false,
    canReadNamedValueItems: false,
    canCreateNamedValues: false,
    canUpdateNamedValues: false,
    canDeleteNamedValues: false,
    ...caps,
  });
  const router = createMemoryRouter(
    [{ element: <Outlet />, children: [
      { path: '/configuration/named-values', element: <NamedValuesPage /> },
      { path: '/configuration/named-values/new', element: <NamedValueEditPage /> },
      { path: '/configuration/named-values/:id', element: <NamedValueEditPage /> },
    ] }],
    { initialEntries: [path] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

describe('named value pages', () => {
  beforeEach(() => {
    mockFetchNatsEmailStatus.mockResolvedValue(NATS_CONFIGURED);
  });
  afterEach(() => {
    cleanup();
    vi.resetAllMocks();
  });

  describe.each([false, true])('tenant switches (super-admin: %s)', (admin) => {
    it('hides the old list and delete dialog before effects while the next fetch is pending', async () => {
      const next = deferred<typeof ROW[]>();
      mockFetchNamedValues.mockResolvedValueOnce([ROW]).mockReturnValueOnce(next.promise);
      const view = renderWithTenant('/configuration/named-values', admin, true);
      fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();

      view.switchTenant('tenant-2');

      expect(view.commits).toHaveLength(1);
      expect(view.commits[0]).not.toContain(ROW.name);
      expect(screen.queryByText(ROW.name)).not.toBeInTheDocument();
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
      expect(screen.getByText('Loading configuration variables…')).toBeInTheDocument();
      expect(mockFetchNamedValues).toHaveBeenLastCalledWith(admin ? 'tenant-2' : null);
      await act(async () => next.resolve([{ ...ROW, tenantId: 'tenant-2', name: 'tenant_two_endpoint' }]));
      expect(await screen.findByText('tenant_two_endpoint')).toBeInTheDocument();
      expect(screen.queryByText(ROW.name)).not.toBeInTheDocument();
    });

    it.each([false, true])('hides old details before effects (editable: %s)', async (editable) => {
      const next = deferred<typeof ROW>();
      mockFetchNamedValue.mockResolvedValueOnce(ROW).mockReturnValueOnce(next.promise);
      const view = renderWithTenant('/configuration/named-values/var-1', admin, editable);
      if (editable) {
        expect(await screen.findByTestId('named-value-value')).toHaveValue(ROW.value);
      } else {
        expect(await screen.findByText(ROW.value)).toBeInTheDocument();
      }

      view.switchTenant('tenant-2');

      expect(view.commits).toHaveLength(1);
      expect(view.commits[0]).not.toContain(ROW.name);
      expect(view.commits[0]).not.toContain(ROW.description);
      expect(view.commits[0]).not.toContain(ROW.value);
      expect(screen.queryByTestId('named-value-save')).not.toBeInTheDocument();
      expect(screen.getByText('Loading configuration variables…')).toBeInTheDocument();
      expect(mockFetchNamedValue).toHaveBeenLastCalledWith('var-1', admin ? 'tenant-2' : null);
      const nextValue = 'https://tenant-two.example.test';
      await act(async () => next.resolve({ ...ROW, tenantId: 'tenant-2', name: 'tenant_two_endpoint', value: nextValue }));
      if (editable) {
        expect(await screen.findByTestId('named-value-value')).toHaveValue(nextValue);
      } else {
        expect(await screen.findByText(nextValue)).toBeInTheDocument();
      }
      expect(screen.queryByText(ROW.value)).not.toBeInTheDocument();
    });

    it.each(['list', 'detail'])('ignores a late %s response from the previous tenant', async (page) => {
      const previous = deferred<typeof ROW>();
      const next = deferred<typeof ROW>();
      mockFetchNamedValues
        .mockImplementationOnce(() => previous.promise.then((row) => [row]))
        .mockImplementationOnce(() => next.promise.then((row) => [row]));
      mockFetchNamedValue.mockReturnValueOnce(previous.promise).mockReturnValueOnce(next.promise);
      const view = renderWithTenant(`/configuration/named-values${page === 'detail' ? '/var-1' : ''}`, admin);
      view.switchTenant('tenant-2');
      await act(async () => next.resolve({ ...ROW, tenantId: 'tenant-2', name: 'tenant_two_endpoint', value: 'tenant-two-value' }));
      expect(await screen.findByText('tenant_two_endpoint')).toBeInTheDocument();
      await act(async () => previous.resolve(ROW));
      expect(screen.queryByText(ROW.name)).not.toBeInTheDocument();
      expect(screen.queryByText(ROW.value)).not.toBeInTheDocument();
      expect(screen.getByText('tenant_two_endpoint')).toBeInTheDocument();
    });

    it('clears an unsaved create draft when switching tenants', () => {
      const view = renderWithTenant('/configuration/named-values/new', admin, true);
      fireEvent.change(screen.getByTestId('named-value-name'), { target: { value: 'tenant_one_draft' } });
      fireEvent.change(screen.getByTestId('named-value-value'), { target: { value: 'tenant-one-secret' } });
      view.switchTenant('tenant-2');
      expect(view.commits[0]).not.toContain('tenant_one_draft');
      expect(view.commits[0]).not.toContain('tenant-one-secret');
      expect(screen.getByTestId('named-value-name')).toHaveValue('');
      expect(screen.getByTestId('named-value-value')).toHaveValue('');
      expect(mockCreateNamedValue).not.toHaveBeenCalled();
    });
  });

  it.each([
    '/configuration/named-values',
    '/configuration/named-values/new',
    '/configuration/named-values/var-1',
  ])('denies direct access to %s without fetching data or showing actions', (path) => {
    renderAt(path);
    expect(screen.getAllByText('Access denied')).toHaveLength(1);
    expect(screen.queryByText('No configuration variables have been created for this tenant.')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Add a variable' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('named-value-save')).not.toBeInTheDocument();
    expect(mockFetchNamedValues).not.toHaveBeenCalled();
    expect(mockFetchNamedValue).not.toHaveBeenCalled();
  });

  it('shows only access denied if list permission is revoked after bootstrap', async () => {
    mockFetchNamedValues.mockRejectedValue(new ApiError('/v1.0/m8flow/named-values', 403));
    renderAt('/configuration/named-values', { canReadNamedValues: true, canCreateNamedValues: true });
    expect(await screen.findByText('Access denied')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Add a variable' })).not.toBeInTheDocument();
    expect(screen.queryByText('No configuration variables have been created for this tenant.')).not.toBeInTheDocument();
    expect(screen.queryByText('Could not load configuration variables.')).not.toBeInTheDocument();
  });

  it('shows a load error without an empty state', async () => {
    mockFetchNamedValues.mockRejectedValue(new Error('network failure'));
    renderAt('/configuration/named-values', { canReadNamedValues: true });
    expect(await screen.findByText('Could not load configuration variables.')).toBeInTheDocument();
    expect(screen.queryByText('No configuration variables have been created for this tenant.')).not.toBeInTheDocument();
  });

  it('shows the empty state only after a successful empty response', async () => {
    let resolve!: (rows: typeof ROW[]) => void;
    mockFetchNamedValues.mockReturnValue(new Promise<typeof ROW[]>((done) => { resolve = done; }));
    renderAt('/configuration/named-values', { canReadNamedValues: true });
    expect(screen.getByText('Loading configuration variables…')).toBeInTheDocument();
    expect(screen.queryByText('No configuration variables have been created for this tenant.')).not.toBeInTheDocument();
    resolve([]);
    expect(await screen.findByText('No configuration variables have been created for this tenant.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('lets a viewer open non-sensitive details without write controls', async () => {
    mockFetchNamedValues.mockResolvedValue([ROW]);
    mockFetchNamedValue.mockResolvedValue(ROW);
    renderAt('/configuration/named-values', { canReadNamedValues: true, canReadNamedValueItems: true });
    fireEvent.click(await screen.findByRole('link', { name: 'View' }));
    expect(await screen.findByText('https://example.test')).toBeInTheDocument();
    expect(screen.getByText('Endpoint')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(screen.queryByTestId('named-value-save')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(mockCreateNamedValue).not.toHaveBeenCalled();
    expect(mockUpdateNamedValue).not.toHaveBeenCalled();
    expect(mockDeleteNamedValue).not.toHaveBeenCalled();
  });

  it('never renders a sensitive value in viewer details, even if returned by the API', async () => {
    mockFetchNamedValue.mockResolvedValue({ ...ROW, isSensitive: true, value: 'sensitive-sentinel' });
    renderAt('/configuration/named-values/var-1', { canReadNamedValueItems: true });
    expect(await screen.findByText('Sensitive values are stored in the configured secret provider and can never be viewed after saving.')).toBeInTheDocument();
    expect(screen.queryByText('sensitive-sentinel')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it.each([403, 404, 500])('does not render an edit form after an item load fails with %s', async (status) => {
    mockFetchNamedValue.mockRejectedValue(new ApiError('/v1.0/m8flow/named-values/var-1', status));
    renderAt('/configuration/named-values/var-1', { canReadNamedValueItems: true, canUpdateNamedValues: true });
    expect(await screen.findByText(status === 403 ? 'Access denied' : 'Could not load this configuration variable.')).toBeInTheDocument();
    expect(screen.queryByTestId('named-value-save')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it.each(['tenant-admin', 'integrator'])('allows all authorized actions for %s', async () => {
    mockFetchNamedValues.mockResolvedValue([ROW]);
    mockDeleteNamedValue.mockResolvedValue(undefined);
    renderAt('/configuration/named-values', {
      canReadNamedValues: true, canReadNamedValueItems: true,
      canCreateNamedValues: true, canUpdateNamedValues: true, canDeleteNamedValues: true,
    });
    expect(await screen.findByRole('link', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Add a variable' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(mockDeleteNamedValue).toHaveBeenCalledWith('var-1', null));
    await waitFor(() => expect(mockFetchNamedValues).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('api_endpoint')).toBeInTheDocument();
  });

  it('keeps the loaded list visible when deletion fails', async () => {
    mockFetchNamedValues.mockResolvedValue([ROW]);
    mockDeleteNamedValue.mockRejectedValue(new Error('delete failed'));
    renderAt('/configuration/named-values', { canReadNamedValues: true, canDeleteNamedValues: true });
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Could not delete this configuration variable.')).toBeInTheDocument();
    expect(screen.getByText('api_endpoint')).toBeInTheDocument();
    expect(screen.queryByText('No configuration variables have been created for this tenant.')).not.toBeInTheDocument();
  });

  it('requires a finalized tenant for a regular user', () => {
    renderAt('/configuration/named-values', { activeTenant: null, canReadNamedValues: true });
    expect(screen.getByText('Choose a tenant')).toBeInTheDocument();
    expect(mockFetchNamedValues).not.toHaveBeenCalled();
  });

  it('requires a valid concrete tenant for a super-admin write form', () => {
    renderAt('/configuration/named-values/new', {
      admin: true, scopedTenant: null, canCreateNamedValues: true,
    });
    expect(screen.getByText('Choose a tenant')).toBeInTheDocument();
  });

  it('lists values and shows only backend-authorized actions', async () => {
    mockFetchNamedValues.mockResolvedValue([ROW]);
    renderAt('/configuration/named-values', {
      canReadNamedValues: true, canReadNamedValueItems: true, canUpdateNamedValues: true,
    });
    expect(await screen.findByText('api_endpoint')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edit' })).toHaveAttribute(
      'href', '/configuration/named-values/var-1',
    );
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(mockFetchNamedValues).toHaveBeenCalledWith(null);
  });

  it('creates a sensitive value and returns directly to the list', async () => {
    mockCreateNamedValue.mockResolvedValue({ ...ROW, id: 'new-var', isSensitive: true, value: null });
    mockFetchNamedValues.mockResolvedValue([{ ...ROW, id: 'new-var', name: 'api_token', isSensitive: true, value: null }]);
    const router = renderAt('/configuration/named-values/new', {
      canCreateNamedValues: true, canReadNamedValues: true,
    });
    fireEvent.change(await screen.findByTestId('named-value-name'), { target: { value: 'api_token' } });
    fireEvent.click(screen.getByTestId('named-value-sensitive'));
    fireEvent.change(screen.getByTestId('named-value-value'), { target: { value: 'token-value' } });
    fireEvent.click(screen.getByTestId('named-value-save'));
    await waitFor(() => expect(mockCreateNamedValue).toHaveBeenCalledWith({
      name: 'api_token', description: null, is_sensitive: true, value: 'token-value',
    }, null));
    await waitFor(() => expect(router.state.location.pathname).toBe('/configuration/named-values'));
    expect(await screen.findByText('api_token')).toBeInTheDocument();
    expect(screen.queryByText('token-value')).not.toBeInTheDocument();
  });

  it('saves edits when item read and update are both permitted', async () => {
    mockFetchNamedValue.mockResolvedValue(ROW);
    mockUpdateNamedValue.mockResolvedValue({ ...ROW, value: 'https://updated.example.test' });
    mockFetchNamedValues.mockResolvedValue([ROW]);
    const router = renderAt('/configuration/named-values/var-1', {
      canReadNamedValues: true, canReadNamedValueItems: true, canUpdateNamedValues: true,
    });
    fireEvent.change(await screen.findByTestId('named-value-value'), {
      target: { value: 'https://updated.example.test' },
    });
    fireEvent.click(screen.getByTestId('named-value-save'));
    await waitFor(() => expect(mockUpdateNamedValue).toHaveBeenCalledWith('var-1', {
      name: 'api_endpoint', description: 'Endpoint', is_sensitive: false,
      value: 'https://updated.example.test',
    }, null));
    await waitFor(() => expect(router.state.location.pathname).toBe('/configuration/named-values'));
    expect(await screen.findByText('api_endpoint')).toBeInTheDocument();
  });

  it('does not prefill or expose a stored sensitive value while editing', async () => {
    mockFetchNamedValue.mockResolvedValue({ ...ROW, isSensitive: true, value: null });
    renderAt('/configuration/named-values/var-1', {
      canReadNamedValueItems: true, canUpdateNamedValues: true,
    });
    expect(await screen.findByTestId('named-value-name')).toHaveValue('api_endpoint');
    expect(screen.getByTestId('named-value-value')).toHaveValue('');
    expect(mockFetchNamedValue).toHaveBeenCalledWith('var-1', null);
  });

  it('reminds about NATS email and offers Configure NATS until it is set up', async () => {
    mockFetchNamedValues.mockResolvedValue([]);
    mockFetchNatsEmailStatus.mockResolvedValue(NATS_MISSING);
    renderAt('/configuration/named-values', {
      canReadNamedValues: true,
      canReadSecrets: true,
      canCreateNamedValues: true,
      canUpdateNamedValues: true,
    });

    expect(await screen.findByTestId('configure-nats')).toHaveAttribute('href', '/configuration/nats');
    expect(screen.getByTestId('nats-email-setup')).toHaveTextContent('NATS_SMTP_HOST');
    expect(mockFetchNatsEmailStatus).toHaveBeenCalledWith(null);
  });

  it('drops the reminder once NATS email is set up; the variables are listed like any other', async () => {
    mockFetchNamedValues.mockResolvedValue([
      { ...ROW, id: 'var-host', name: 'NATS_SMTP_HOST', isSensitive: true, value: null },
    ]);
    renderAt('/configuration/named-values', { canReadNamedValues: true, canReadSecrets: true });

    expect(await screen.findByText('NATS_SMTP_HOST')).toBeInTheDocument();
    await waitFor(() => expect(mockFetchNatsEmailStatus).toHaveBeenCalled());
    expect(screen.queryByTestId('configure-nats')).not.toBeInTheDocument();
    expect(screen.queryByTestId('nats-email-setup')).not.toBeInTheDocument();
  });

  it('skips the NATS status without secrets read', async () => {
    mockFetchNamedValues.mockResolvedValue([]);
    renderAt('/configuration/named-values', { canReadNamedValues: true });

    await waitFor(() => expect(mockFetchNamedValues).toHaveBeenCalled());
    expect(mockFetchNatsEmailStatus).not.toHaveBeenCalled();
    expect(screen.queryByTestId('configure-nats')).not.toBeInTheDocument();
  });

  it('confirms a save from the Configure NATS page', async () => {
    mockFetchNamedValues.mockResolvedValue([]);
    renderAt(
      { pathname: '/configuration/named-values', state: { natsEmailSaved: true } },
      { canReadNamedValues: true, canReadSecrets: true },
    );

    expect(await screen.findByTestId('nats-email-saved')).toHaveTextContent('NATS email settings saved.');
  });

  it('shows the reminder but no Configure NATS to a role that cannot save variables', async () => {
    mockFetchNamedValues.mockResolvedValue([]);
    mockFetchNatsEmailStatus.mockResolvedValue(NATS_MISSING);
    renderAt('/configuration/named-values', { canReadNamedValues: true, canReadSecrets: true });

    expect(await screen.findByTestId('nats-email-setup')).toBeInTheDocument();
    expect(screen.queryByTestId('configure-nats')).not.toBeInTheDocument();
  });

  it('still offers Configure NATS when the status cannot be read', async () => {
    mockFetchNamedValues.mockResolvedValue([]);
    mockFetchNatsEmailStatus.mockRejectedValue(new Error('down'));
    renderAt('/configuration/named-values', {
      canReadNamedValues: true,
      canReadSecrets: true,
      canCreateNamedValues: true,
      canUpdateNamedValues: true,
    });

    expect(await screen.findByTestId('configure-nats')).toBeInTheDocument();
    expect(screen.queryByTestId('nats-email-setup')).not.toBeInTheDocument();
  });

  it('brings the reminder back after a required NATS variable is deleted', async () => {
    mockFetchNamedValues.mockResolvedValue([
      { ...ROW, id: 'var-host', name: 'NATS_SMTP_HOST', isSensitive: true, value: null },
    ]);
    mockFetchNatsEmailStatus.mockResolvedValueOnce(NATS_CONFIGURED).mockResolvedValue(NATS_MISSING);
    mockDeleteNamedValue.mockResolvedValue(undefined);
    renderAt('/configuration/named-values', {
      canReadNamedValues: true,
      canReadSecrets: true,
      canDeleteNamedValues: true,
    });

    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));

    expect(await screen.findByTestId('nats-email-setup')).toBeInTheDocument();
    expect(mockFetchNatsEmailStatus).toHaveBeenCalledTimes(2);
  });
});
