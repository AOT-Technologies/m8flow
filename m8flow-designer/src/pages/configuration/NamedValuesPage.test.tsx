import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

const mockUseActiveTenant = vi.fn();
const mockUseCapabilities = vi.fn();
const mockFetchNamedValues = vi.fn();
const mockFetchNamedValue = vi.fn();
const mockCreateNamedValue = vi.fn();
const mockUpdateNamedValue = vi.fn();
const mockDeleteNamedValue = vi.fn();

vi.mock('@/components/session/hooks', () => ({
  useActiveTenant: () => mockUseActiveTenant(),
  useCapabilities: () => mockUseCapabilities(),
  useTenantRegistry: () => ({ tenants: [{ id: 'tenant-1', name: 'Tenant 1' }] }),
}));

vi.mock('@/lib/namedValuesApi', () => ({
  fetchNamedValues: (...args: unknown[]) => mockFetchNamedValues(...args),
  fetchNamedValue: (...args: unknown[]) => mockFetchNamedValue(...args),
  createNamedValue: (...args: unknown[]) => mockCreateNamedValue(...args),
  updateNamedValue: (...args: unknown[]) => mockUpdateNamedValue(...args),
  deleteNamedValue: (...args: unknown[]) => mockDeleteNamedValue(...args),
  namedValuesErrorMessage: (_error: unknown, fallback: string) => fallback,
}));

import NamedValueEditPage from './NamedValueEditPage';
import NamedValuesPage from './NamedValuesPage';

const ROW = {
  id: 'var-1', tenantId: 'tenant-1', name: 'api_endpoint', description: 'Endpoint',
  isSensitive: false, isConfigured: true, value: 'https://example.test',
  createdAt: null, updatedAt: null,
};

function renderAt(
  path: string,
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
  afterEach(() => vi.clearAllMocks());

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

  it('creates a sensitive value and navigates to the saved entry', async () => {
    mockCreateNamedValue.mockResolvedValue({ ...ROW, id: 'new-var', isSensitive: true, value: null });
    mockFetchNamedValue.mockResolvedValue({ ...ROW, id: 'new-var', isSensitive: true, value: null });
    const router = renderAt('/configuration/named-values/new', {
      canCreateNamedValues: true,
    });
    fireEvent.change(await screen.findByTestId('named-value-name'), { target: { value: 'api_token' } });
    fireEvent.click(screen.getByTestId('named-value-sensitive'));
    fireEvent.change(screen.getByTestId('named-value-value'), { target: { value: 'token-value' } });
    fireEvent.click(screen.getByTestId('named-value-save'));
    await waitFor(() => expect(mockCreateNamedValue).toHaveBeenCalledWith({
      name: 'api_token', description: null, is_sensitive: true, value: 'token-value',
    }, null));
    await waitFor(() => expect(router.state.location.pathname).toBe('/configuration/named-values/new-var'));
    expect(screen.queryByText('token-value')).not.toBeInTheDocument();
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
});
