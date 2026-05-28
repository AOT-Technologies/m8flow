import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from './App';

const mockUseConfig = vi.fn();
const mockDoLogin = vi.fn();
const mockIsLoggedIn = vi.fn();
const mockGetAuthenticationIdentifier = vi.fn();
const mockHasSelectedTenantCookie = vi.fn();

vi.mock('./utils/useConfig', () => ({
  useConfig: () => mockUseConfig(),
}));

vi.mock('./services/UserService', () => ({
  default: {
    doLogin: (...args: unknown[]) => mockDoLogin(...args),
    getAuthenticationIdentifier: () => mockGetAuthenticationIdentifier(),
    hasSelectedTenantCookie: () => mockHasSelectedTenantCookie(),
    isLoggedIn: () => mockIsLoggedIn(),
  },
}));

vi.mock('./views/TenantSelectPage', () => ({
  M8FLOW_TENANT_STORAGE_KEY: 'm8flow_tenant',
  default: () => <div>tenant-selection-page</div>,
}));

vi.mock('./ContainerForExtensions', () => ({
  default: () => <div>container-for-extensions</div>,
}));

vi.mock('./components/RouteLoadingFallback', () => ({
  RouteLoadingFallback: () => <div>loading</div>,
}));

vi.mock('@spiffworkflow-frontend/contexts/Can', async () => {
  const ReactModule = await import('react');
  return {
    AbilityContext: ReactModule.createContext({}),
  };
});

vi.mock('@spiffworkflow-frontend/contexts/APIErrorContext', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@spiffworkflow-frontend/assets/theme/SpiffTheme', () => ({
  createSpiffTheme: () => ({}),
}));

vi.mock('@spiffworkflow-frontend/views/PublicRoutes', () => ({
  default: () => <div>public-routes</div>,
}));

vi.mock('@spiffworkflow-frontend/config', () => ({
  CONFIGURATION_ERRORS: [],
}));

vi.mock('./contexts/CustomGroupingContext', () => ({
  CustomGroupingProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('./contexts/TenantGateContext', async () => {
  const ReactModule = await import('react');
  return {
    default: ReactModule.createContext({ onTenantSelected: () => undefined }),
  };
});

describe('App', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('starts shared-realm login immediately instead of rendering the tenant landing for unauthenticated root access', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      MASTER_REALM_IDENTIFIER: 'master',
      SHARED_REALM_IDENTIFIER: 'm8flow',
    });
    mockIsLoggedIn.mockReturnValue(false);
    mockGetAuthenticationIdentifier.mockReturnValue(null);
    mockHasSelectedTenantCookie.mockReturnValue(false);

    vi.stubGlobal('location', {
      origin: 'http://localhost:7001',
      pathname: '/',
      search: '',
    });

    render(<App />);

    expect(screen.getByText('Redirecting to sign in...')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockDoLogin).toHaveBeenCalledWith(
        {
          identifier: 'm8flow',
          label: 'm8flow',
          uri: '',
        },
        'http://localhost:7001/',
      );
    });

    expect(screen.queryByText('tenant-selection-page')).not.toBeInTheDocument();
  });

  it('keeps the tenant selection page for authenticated shared-realm users without a finalized tenant', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      MASTER_REALM_IDENTIFIER: 'master',
      SHARED_REALM_IDENTIFIER: 'm8flow',
    });
    mockIsLoggedIn.mockReturnValue(true);
    mockGetAuthenticationIdentifier.mockReturnValue('m8flow');
    mockHasSelectedTenantCookie.mockReturnValue(false);

    vi.stubGlobal('location', {
      origin: 'http://localhost:7001',
      pathname: '/',
      search: '',
    });

    render(<App />);

    expect(await screen.findByText('tenant-selection-page')).toBeInTheDocument();
    expect(mockDoLogin).not.toHaveBeenCalled();
  });

  it('does not let stale local tenant storage bypass tenant selection for shared-realm users', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      MASTER_REALM_IDENTIFIER: 'master',
      SHARED_REALM_IDENTIFIER: 'm8flow',
    });
    mockIsLoggedIn.mockReturnValue(true);
    mockGetAuthenticationIdentifier.mockReturnValue('m8flow');
    mockHasSelectedTenantCookie.mockReturnValue(false);

    localStorage.setItem('m8flow_tenant', 'it');
    localStorage.setItem('m8f_tenant_id', 'tenant-it-id');

    vi.stubGlobal('location', {
      origin: 'http://localhost:7001',
      pathname: '/',
      search: '',
    });

    render(<App />);

    expect(await screen.findByText('tenant-selection-page')).toBeInTheDocument();
    expect(screen.queryByText('container-for-extensions')).not.toBeInTheDocument();
  });

  it('skips tenant selection once the selected-tenant cookie is present', async () => {
    mockUseConfig.mockReturnValue({
      ENABLE_MULTITENANT: true,
      MASTER_REALM_IDENTIFIER: 'master',
      SHARED_REALM_IDENTIFIER: 'm8flow',
    });
    mockIsLoggedIn.mockReturnValue(true);
    mockGetAuthenticationIdentifier.mockReturnValue('m8flow');
    mockHasSelectedTenantCookie.mockReturnValue(true);

    vi.stubGlobal('location', {
      origin: 'http://localhost:7001',
      pathname: '/',
      search: '',
    });

    render(<App />);

    expect(await screen.findByText('container-for-extensions')).toBeInTheDocument();
    expect(screen.queryByText('tenant-selection-page')).not.toBeInTheDocument();
  });
});
