import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TenantSelectPage from './TenantSelectPage';

const mockIsLoggedIn = vi.fn();
const mockGetOrganizationMemberships = vi.fn();
const mockLogin = vi.fn();
const mockLoginAsPlatformAdmin = vi.fn();
const mockLogout = vi.fn();
const mockClearSelectedTenantCookie = vi.fn();
const mockFinalizeTenantLogin = vi.fn();
const mockFetchOrganizationMemberships = vi.fn();

vi.mock('@/lib/auth', () => ({
  isLoggedIn: () => mockIsLoggedIn(),
  getOrganizationMemberships: () => mockGetOrganizationMemberships(),
  login: (...args: unknown[]) => mockLogin(...args),
  loginAsPlatformAdmin: (...args: unknown[]) => mockLoginAsPlatformAdmin(...args),
  logout: () => mockLogout(),
  clearSelectedTenantCookie: () => mockClearSelectedTenantCookie(),
  finalizeTenantLogin: (...args: unknown[]) => mockFinalizeTenantLogin(...args),
  GLOBAL_ADMIN_LANDING_PATH: '/tenants',
}));

vi.mock('@/lib/api', () => ({
  fetchOrganizationMemberships: () => mockFetchOrganizationMemberships(),
}));

describe('TenantSelectPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
    mockGetOrganizationMemberships.mockReturnValue([]);
    mockFetchOrganizationMemberships.mockResolvedValue([]);
  });

  it('auto-redirects straight to the shared-realm Keycloak sign-in when logged out', () => {
    mockIsLoggedIn.mockReturnValue(false);
    mockGetOrganizationMemberships.mockReturnValue([]);

    render(<TenantSelectPage />);

    expect(screen.getByTestId('sign-in-redirecting')).toBeInTheDocument();
    expect(mockClearSelectedTenantCookie).toHaveBeenCalled();
    expect(mockLogin).toHaveBeenCalledTimes(1);
    expect(mockLogin).toHaveBeenCalledWith({ redirectUrl: `${window.location.origin}/` });
    expect(mockLoginAsPlatformAdmin).not.toHaveBeenCalled();
    expect(mockFinalizeTenantLogin).not.toHaveBeenCalled();
  });

  it('blocks a logged-in user with zero organizations and logs out from Back to login', async () => {
    mockIsLoggedIn.mockReturnValue(true);
    mockGetOrganizationMemberships.mockReturnValue([]);
    mockFetchOrganizationMemberships.mockResolvedValue([]);

    render(<TenantSelectPage />);

    expect(await screen.findByTestId('no-tenant-access-message')).toBeInTheDocument();
    expect(screen.queryByTestId('global-admin-sign-in-button')).not.toBeInTheDocument();
    expect(mockFinalizeTenantLogin).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('back-to-login-button'));
    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  it('auto-finalizes when the JWT omits organizations but the directory lists one', async () => {
    mockIsLoggedIn.mockReturnValue(true);
    mockGetOrganizationMemberships.mockReturnValue([]);
    mockFetchOrganizationMemberships.mockResolvedValue([
      { alias: 'acme', id: 'tenant-acme', name: 'Acme' },
    ]);

    render(<TenantSelectPage />);

    await waitFor(() => {
      expect(mockFinalizeTenantLogin).toHaveBeenCalledWith({
        alias: 'acme',
        id: 'tenant-acme',
        name: 'Acme',
      });
    });
    expect(screen.getByText('Finalizing tenant access')).toBeInTheDocument();
  });

  it('auto-finalizes the only organization through the backend hop', async () => {
    mockIsLoggedIn.mockReturnValue(true);
    mockGetOrganizationMemberships.mockReturnValue([
      { alias: 'acme', id: 'tenant-acme', name: 'Acme' },
    ]);

    render(<TenantSelectPage />);

    await waitFor(() => {
      expect(mockFinalizeTenantLogin).toHaveBeenCalledWith({
        alias: 'acme',
        id: 'tenant-acme',
        name: 'Acme',
      });
    });
    expect(screen.getByText('Finalizing tenant access')).toBeInTheDocument();
  });

  it('lets a multi-organization user pick a tenant from a dropdown and confirm', async () => {
    mockIsLoggedIn.mockReturnValue(true);
    mockGetOrganizationMemberships.mockReturnValue([
      { alias: 'acme', id: 'tenant-acme', name: null },
      { alias: 'other', id: 'tenant-other', name: null },
    ]);
    mockFetchOrganizationMemberships.mockResolvedValue([
      { alias: 'acme', id: 'tenant-acme', name: 'Acme Corp' },
      { alias: 'other', id: 'tenant-other', name: 'Other Org' },
    ]);

    render(<TenantSelectPage />);

    fireEvent.click(await screen.findByTestId('tenant-select-trigger'));

    await waitFor(() => {
      expect(screen.getByTestId('organization-option-acme')).toHaveTextContent('Acme Corp');
    });
    expect(screen.getByTestId('organization-option-other')).toHaveTextContent('Other Org');
    expect(mockFinalizeTenantLogin).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('organization-option-other'));
    fireEvent.click(screen.getByTestId('tenant-select-confirm-button'));

    expect(mockFinalizeTenantLogin).toHaveBeenCalledWith({
      alias: 'other',
      id: 'tenant-other',
      name: 'Other Org',
    });
  });
});
