import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TenantSelectPage, { M8FLOW_TENANT_STORAGE_KEY } from './TenantSelectPage';
import TenantGateContext from '../contexts/TenantGateContext';

const mockUseConfig = vi.fn();
const mockIsLoggedIn = vi.fn();
const mockGetOrganizationMemberships = vi.fn();

vi.mock('../utils/useConfig', () => ({
  useConfig: () => mockUseConfig(),
}));

vi.mock('../services/UserService', () => ({
  default: {
    getOrganizationMemberships: () => mockGetOrganizationMemberships(),
    isLoggedIn: () => mockIsLoggedIn(),
  },
}));

describe('TenantSelectPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
    document.cookie = 'm8flow_selected_tenant=; Max-Age=0; Path=/';
  });

  it('starts shared-realm login before any tenant is selected', () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      BACKEND_BASE_URL: '/v1.0',
      MASTER_REALM_IDENTIFIER: 'ops-admin',
      SHARED_REALM_IDENTIFIER: 'shared-users',
    });
    mockIsLoggedIn.mockReturnValue(false);
    mockGetOrganizationMemberships.mockReturnValue([]);

    const assignMock = vi.fn();
    vi.stubGlobal('location', {
      origin: 'http://localhost',
      pathname: '/',
      search: '',
      assign: assignMock,
      replace: vi.fn(),
      href: 'http://localhost/',
    });
    document.cookie = 'm8flow_selected_tenant=tenant-a-id';
    localStorage.setItem(M8FLOW_TENANT_STORAGE_KEY, 'tenant-a');
    localStorage.setItem('m8f_tenant_id', 'tenant-a-id');

    render(<TenantSelectPage />);

    fireEvent.click(screen.getByTestId('shared-realm-sign-in-button'));

    expect(localStorage.getItem(M8FLOW_TENANT_STORAGE_KEY)).toBeNull();
    expect(localStorage.getItem('m8f_tenant_id')).toBeNull();
    expect(document.cookie).not.toContain('m8flow_selected_tenant=');
    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining('/v1.0/login?redirect_url='),
    );
    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining('authentication_identifier=shared-users'),
    );
    expect(assignMock).not.toHaveBeenCalledWith(
      expect.stringContaining('tenant='),
    );
  });

  it('auto-finalizes the only available organization after login', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      BACKEND_BASE_URL: '/v1.0',
      MASTER_REALM_IDENTIFIER: 'ops-admin',
      SHARED_REALM_IDENTIFIER: 'shared-users',
    });
    mockIsLoggedIn.mockReturnValue(true);
    mockGetOrganizationMemberships.mockReturnValue([
      { alias: 'tenant-a', id: 'tenant-a-id', name: 'Tenant A' },
    ]);

    const assignMock = vi.fn();
    vi.stubGlobal('location', {
      origin: 'http://localhost',
      pathname: '/',
      search: '',
      assign: assignMock,
      replace: vi.fn(),
      href: 'http://localhost/',
    });

    const onTenantSelected = vi.fn();
    render(
      <TenantGateContext.Provider value={{ onTenantSelected }}>
        <TenantSelectPage />
      </TenantGateContext.Provider>,
    );

    await waitFor(() => {
      expect(assignMock).toHaveBeenCalledWith(
        expect.stringContaining('/v1.0/login?redirect_url='),
      );
    });
    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining('authentication_identifier=shared-users'),
    );
    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining('tenant=tenant-a'),
    );
    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining('tenant_finalization=1'),
    );
    expect(onTenantSelected).not.toHaveBeenCalled();
    expect(localStorage.getItem(M8FLOW_TENANT_STORAGE_KEY)).toBe('tenant-a');
    expect(localStorage.getItem('m8f_tenant_id')).toBe('tenant-a-id');
    expect(document.cookie).toContain('m8flow_selected_tenant=tenant-a-id');
  });

  it('lets a multi-organization user choose which tenant to enter', () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      BACKEND_BASE_URL: '/v1.0',
      MASTER_REALM_IDENTIFIER: 'ops-admin',
      SHARED_REALM_IDENTIFIER: 'shared-users',
    });
    mockIsLoggedIn.mockReturnValue(true);
    mockGetOrganizationMemberships.mockReturnValue([
      { alias: 'tenant-a', id: 'tenant-a-id', name: 'Tenant A' },
      { alias: 'tenant-b', id: 'tenant-b-id', name: 'Tenant B' },
    ]);

    const assignMock = vi.fn();
    vi.stubGlobal('location', {
      origin: 'http://localhost',
      pathname: '/',
      search: '',
      assign: assignMock,
      replace: vi.fn(),
      href: 'http://localhost/',
    });

    const onTenantSelected = vi.fn();
    render(
      <TenantGateContext.Provider value={{ onTenantSelected }}>
        <TenantSelectPage />
      </TenantGateContext.Provider>,
    );

    fireEvent.click(screen.getByTestId('organization-option-tenant-b'));

    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining('authentication_identifier=shared-users'),
    );
    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining('tenant=tenant-b'),
    );
    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining('tenant_finalization=1'),
    );
    expect(onTenantSelected).not.toHaveBeenCalled();
    expect(localStorage.getItem(M8FLOW_TENANT_STORAGE_KEY)).toBe('tenant-b');
    expect(localStorage.getItem('m8f_tenant_id')).toBe('tenant-b-id');
    expect(document.cookie).toContain('m8flow_selected_tenant=tenant-b-id');
  });

  it('routes platform admin sign-in through the configured master realm', () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      BACKEND_BASE_URL: '/v1.0',
      MASTER_REALM_IDENTIFIER: 'ops-admin',
      SHARED_REALM_IDENTIFIER: 'shared-users',
    });
    mockIsLoggedIn.mockReturnValue(false);
    mockGetOrganizationMemberships.mockReturnValue([]);

    const assignMock = vi.fn();
    vi.stubGlobal('location', {
      origin: 'http://localhost',
      pathname: '/',
      search: '',
      assign: assignMock,
      replace: vi.fn(),
      href: 'http://localhost/',
    });

    render(<TenantSelectPage />);

    fireEvent.click(screen.getByTestId('global-admin-sign-in-button'));

    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining('authentication_identifier=ops-admin'),
    );
    expect(assignMock).toHaveBeenCalledWith(
      expect.stringContaining(encodeURIComponent('http://localhost/tenants')),
    );
  });
});
