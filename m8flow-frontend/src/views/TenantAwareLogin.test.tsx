import { render, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import TenantAwareLogin from './TenantAwareLogin';

const mockUseConfig = vi.fn();
const mockDoLogin = vi.fn();
const mockIsLoggedIn = vi.fn();

vi.mock('../utils/useConfig', () => ({
  useConfig: () => mockUseConfig(),
}));

vi.mock('../services/UserService', () => ({
  default: {
    doLogin: (...args: unknown[]) => mockDoLogin(...args),
    isLoggedIn: () => mockIsLoggedIn(),
  },
}));

describe('TenantAwareLogin', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
    document.cookie = 'm8flow_selected_tenant=; Max-Age=0; Path=/';
  });

  it('auto-redirects to the m8flow login flow when multitenant is disabled', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: false,
      MASTER_REALM_IDENTIFIER: 'ops-admin',
      SHARED_REALM_IDENTIFIER: 'shared-users',
    });
    mockIsLoggedIn.mockReturnValue(false);
    localStorage.setItem('m8flow_tenant', 'it');
    localStorage.setItem('m8f_tenant_id', 'it');

    render(
      <MemoryRouter initialEntries={['/login?original_url=/reports']}>
        <Routes>
          <Route path="/login" element={<TenantAwareLogin />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockDoLogin).toHaveBeenCalledWith(
        {
          identifier: 'shared-users',
          label: 'shared-users',
          uri: '',
        },
        '/reports',
      );
    });

    expect(localStorage.getItem('m8flow_tenant')).toBeNull();
    expect(localStorage.getItem('m8f_tenant_id')).toBeNull();
  });

  it('preserves an explicit authentication_identifier in single-tenant mode', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: false,
      MASTER_REALM_IDENTIFIER: 'ops-admin',
      SHARED_REALM_IDENTIFIER: 'shared-users',
    });
    mockIsLoggedIn.mockReturnValue(false);

    render(
      <MemoryRouter
        initialEntries={['/login?authentication_identifier=ops-admin&original_url=/tenants']}
      >
        <Routes>
          <Route path="/login" element={<TenantAwareLogin />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockDoLogin).toHaveBeenCalledWith(
        {
          identifier: 'ops-admin',
          label: 'Master',
          uri: '',
        },
        '/tenants',
      );
    });
  });

  it('starts shared-realm login directly in multitenant mode', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      MASTER_REALM_IDENTIFIER: 'ops-admin',
      SHARED_REALM_IDENTIFIER: 'shared-users',
    });
    mockIsLoggedIn.mockReturnValue(false);
    document.cookie = 'm8flow_selected_tenant=tenant-a-id';
    localStorage.setItem('m8flow_tenant', 'tenant-a');
    localStorage.setItem('m8f_tenant_id', 'tenant-a-id');

    vi.stubGlobal('location', {
      origin: 'http://localhost',
      pathname: '/login',
      search: '?original_url=/reports',
      assign: vi.fn(),
      replace: vi.fn(),
      href: 'http://localhost/login?original_url=/reports',
    });

    render(
      <MemoryRouter initialEntries={['/login?original_url=/reports']}>
        <Routes>
          <Route path="/login" element={<TenantAwareLogin />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockDoLogin).toHaveBeenCalledWith(
        {
          identifier: 'shared-users',
          label: 'shared-users',
          uri: '',
        },
        '/reports',
      );
    });

    expect(localStorage.getItem('m8flow_tenant')).toBeNull();
    expect(localStorage.getItem('m8f_tenant_id')).toBeNull();
    expect(document.cookie).not.toContain('m8flow_selected_tenant=');
  });

  it('redirects logged-in multitenant users back to the requested page', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      MASTER_REALM_IDENTIFIER: 'ops-admin',
      SHARED_REALM_IDENTIFIER: 'shared-users',
    });
    mockIsLoggedIn.mockReturnValue(true);

    const replaceMock = vi.fn();
    vi.stubGlobal('location', {
      origin: 'http://localhost',
      pathname: '/login',
      search: '?original_url=/process-instances',
      assign: vi.fn(),
      replace: replaceMock,
      href: 'http://localhost/login?original_url=/process-instances',
    });

    render(
      <MemoryRouter initialEntries={['/login?original_url=/process-instances']}>
        <Routes>
          <Route path="/login" element={<TenantAwareLogin />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/process-instances');
    });
    expect(mockDoLogin).not.toHaveBeenCalled();
  });
});
