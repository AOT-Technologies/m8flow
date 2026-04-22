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

vi.mock('@spiffworkflow-frontend/views/Login', () => ({
  default: () => <div>Login chooser</div>,
}));

describe('TenantAwareLogin', () => {
  afterEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('auto-redirects to the m8flow login flow when multitenant is disabled', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: false,
      BACKEND_BASE_URL: '/v1.0',
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
          identifier: 'm8flow',
          label: 'M8Flow Realm',
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
      BACKEND_BASE_URL: '/v1.0',
    });
    mockIsLoggedIn.mockReturnValue(false);

    render(
      <MemoryRouter initialEntries={['/login?authentication_identifier=master&original_url=/tenants']}>
        <Routes>
          <Route path="/login" element={<TenantAwareLogin />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockDoLogin).toHaveBeenCalledWith(
        {
          identifier: 'master',
          label: 'Master',
          uri: '',
        },
        '/tenants',
      );
    });
  });
});
