import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
import SecretListPage from './SecretListPage';
import SecretNewPage from './SecretNewPage';
import SecretShowPage from './SecretShowPage';

const mockFetchSecrets = vi.fn();
const mockFetchSecret = vi.fn();
const mockCreateSecret = vi.fn();
const mockUpdateSecret = vi.fn();
const mockDeleteSecret = vi.fn();

vi.mock('@/lib/secretsApi', async () => {
  const actual = await vi.importActual<typeof import('@/lib/secretsApi')>('@/lib/secretsApi');
  return {
    ...actual,
    fetchSecrets: (...args: unknown[]) => mockFetchSecrets(...args),
    fetchSecret: (...args: unknown[]) => mockFetchSecret(...args),
    createSecret: (...args: unknown[]) => mockCreateSecret(...args),
    updateSecret: (...args: unknown[]) => mockUpdateSecret(...args),
    deleteSecret: (...args: unknown[]) => mockDeleteSecret(...args),
  };
});

const ROW = {
  id: 1,
  key: 'SMTP_PASSWORD',
  user_id: 3,
  created_at_in_seconds: 1,
  updated_at_in_seconds: 2,
  username: 'integrator',
  tenantId: 't1',
  tenantName: 'Acme',
};

function renderAt(path: string, context: SessionFixtureContext) {
  mockUseActiveTenant.mockReturnValue(activeTenantFromContext(context));
  mockUseCapabilities.mockReturnValue(capabilitiesFromContext(context));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={context} />}>
          <Route path="/configuration/secrets" element={<SecretListPage />} />
          <Route path="/configuration/secrets/new" element={<SecretNewPage />} />
          <Route path="/configuration/secrets/:key" element={<SecretShowPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const MANAGE: SessionFixtureContext = {
  scopedTenantId: 't1',
  selectedTenantId: 't1',
  isSuperAdmin: true,
  canReadSecrets: true,
  canManageSecrets: true,
};

const VIEW: SessionFixtureContext = {
  scopedTenantId: null,
  selectedTenantId: null,
  isSuperAdmin: false,
  canReadSecrets: true,
  canManageSecrets: false,
};

describe('Configuration secrets UI', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('explains denial when the role cannot read secrets', () => {
    renderAt('/configuration/secrets', {
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: false,
      canReadSecrets: false,
      canManageSecrets: false,
    });
    expect(screen.getByText('Not available')).toBeInTheDocument();
    expect(mockFetchSecrets).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: /Add a secret/i })).not.toBeInTheDocument();
  });

  it('prompts super-admin when All Tenants is selected', () => {
    renderAt('/configuration/secrets', {
      scopedTenantId: null,
      selectedTenantId: null,
      isSuperAdmin: true,
      canReadSecrets: true,
      canManageSecrets: true,
    });
    expect(screen.getByText('Choose a tenant')).toBeInTheDocument();
    expect(mockFetchSecrets).not.toHaveBeenCalled();
  });

  it('lists keys as links for a viewer without add or delete', async () => {
    mockFetchSecrets.mockResolvedValue({
      results: [ROW],
      pagination: { count: 1, total: 1, pages: 1 },
    });
    renderAt('/configuration/secrets', VIEW);

    expect(await screen.findByRole('link', { name: 'SMTP_PASSWORD' })).toHaveAttribute(
      'href',
      '/configuration/secrets/SMTP_PASSWORD',
    );
    expect(screen.getByText('integrator')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Add a secret/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('secret-list-tenant-cell')).not.toBeInTheDocument();
    expect(mockFetchSecrets).toHaveBeenCalledWith({
      page: 1,
      perPage: 10,
      tenantId: null,
    });
  });

  it('passes tenantId and shows the tenant column for super-admin', async () => {
    mockFetchSecrets.mockResolvedValue({
      results: [ROW],
      pagination: { count: 1, total: 1, pages: 1 },
    });
    renderAt('/configuration/secrets', MANAGE);
    expect(await screen.findByTestId('secret-list-tenant-cell')).toHaveTextContent('Acme');
    expect(mockFetchSecrets).toHaveBeenCalledWith({
      page: 1,
      perPage: 10,
      tenantId: 't1',
    });
  });

  it('creates a secret and never redisplays the value', async () => {
    mockCreateSecret.mockResolvedValue({ ...ROW, key: 'API_TOKEN', username: undefined });
    mockFetchSecret.mockResolvedValue({ ...ROW, key: 'API_TOKEN' });
    renderAt('/configuration/secrets/new', MANAGE);

    fireEvent.change(screen.getByTestId('secret-key'), { target: { value: 'API_TOKEN' } });
    fireEvent.change(screen.getByTestId('secret-value'), { target: { value: 'super-secret' } });
    fireEvent.click(screen.getByTestId('secret-create'));

    await waitFor(() => {
      expect(mockCreateSecret).toHaveBeenCalledWith('API_TOKEN', 'super-secret', 't1');
    });
    expect(await screen.findByTestId('secret-show-key')).toHaveTextContent('API_TOKEN');
    expect(screen.queryByDisplayValue('super-secret')).not.toBeInTheDocument();
    expect(screen.queryByText('super-secret')).not.toBeInTheDocument();
  });

  it('loads show metadata and PUTs only { value } on blind edit', async () => {
    mockFetchSecret.mockResolvedValue(ROW);
    mockUpdateSecret.mockResolvedValue(undefined);
    renderAt('/configuration/secrets/SMTP_PASSWORD', MANAGE);

    expect(await screen.findByTestId('secret-show-key')).toHaveTextContent('SMTP_PASSWORD');
    expect(mockFetchSecret).toHaveBeenCalledWith('SMTP_PASSWORD', 't1');
    expect(String(mockFetchSecret.mock.calls[0][0])).not.toContain('show');

    fireEvent.click(screen.getByTestId('secret-edit'));
    fireEvent.change(screen.getByTestId('secret-value'), { target: { value: 'rotated' } });
    fireEvent.click(screen.getByTestId('secret-update'));

    await waitFor(() => {
      expect(mockUpdateSecret).toHaveBeenCalledWith('SMTP_PASSWORD', 'rotated', 't1');
    });
    expect(await screen.findByTestId('secret-updated')).toBeInTheDocument();
    expect(screen.queryByTestId('secret-value')).not.toBeInTheDocument();
  });

  it('hides edit and delete on show for a viewer', async () => {
    mockFetchSecret.mockResolvedValue(ROW);
    renderAt('/configuration/secrets/SMTP_PASSWORD', VIEW);
    expect(await screen.findByTestId('secret-show-key')).toBeInTheDocument();
    expect(screen.queryByTestId('secret-edit')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  });

  it('deletes from the list after confirm', async () => {
    mockFetchSecrets.mockResolvedValue({
      results: [ROW],
      pagination: { count: 1, total: 1, pages: 1 },
    });
    mockDeleteSecret.mockResolvedValue(undefined);
    renderAt('/configuration/secrets', MANAGE);

    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
    expect(await screen.findByRole('heading', { name: 'Delete secret?' })).toBeInTheDocument();
    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' });
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);
    await waitFor(() => {
      expect(mockDeleteSecret).toHaveBeenCalledWith('SMTP_PASSWORD', 't1');
    });
  });
});
