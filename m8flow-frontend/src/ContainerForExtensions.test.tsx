import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import type { ReactNode } from 'react';
import ContainerForExtensions from './ContainerForExtensions';

const {
  makeCallToBackend,
  can,
  isLoggedIn,
  isSuperAdmin,
  getCurrentLocation,
} = vi.hoisted(() => ({
  makeCallToBackend: vi.fn(),
  can: vi.fn(),
  isLoggedIn: vi.fn(),
  isSuperAdmin: vi.fn(),
  getCurrentLocation: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (value: string) => value }),
}));

vi.mock('react-error-boundary', () => ({
  ErrorBoundary: ({ children }: { children: ReactNode }) => children,
}));

vi.mock('@spiffworkflow-frontend/ErrorBoundaryFallack', () => ({
  ErrorBoundaryFallback: () => <div data-testid="error-boundary-fallback" />,
}));

vi.mock('./components/SideNav', () => ({
  default: () => <div data-testid="side-nav" />,
}));

vi.mock('@spiffworkflow-frontend/views/Extension', () => ({
  default: () => <div data-testid="extension-route" />,
}));

vi.mock('@spiffworkflow-frontend/views/BaseRoutes', () => ({
  default: () => <div data-testid="base-routes" />,
}));

vi.mock('@spiffworkflow-frontend/views/BackendIsDown', () => ({
  default: () => <div data-testid="backend-down" />,
}));

vi.mock('@spiffworkflow-frontend/views/FrontendAccessDenied', () => ({
  default: () => <div data-testid="frontend-access-denied" />,
}));

vi.mock('@spiffworkflow-frontend/views/Login', () => ({
  default: () => <div data-testid="login-route" />,
}));

vi.mock('./views/TenantAwareLogin', () => ({
  default: () => <div data-testid="tenant-aware-login" />,
}));

vi.mock('./views/TenantSelectPage', () => ({
  M8FLOW_TENANT_STORAGE_KEY: 'm8flow-tenant',
  default: () => <div data-testid="tenant-select-page" />,
}));

vi.mock('@spiffworkflow-frontend/components/ScrollToTop', () => ({
  default: () => null,
}));

vi.mock('@spiffworkflow-frontend/components/DynamicCSSInjection', () => ({
  default: () => null,
}));

vi.mock('@spiffworkflow-frontend/assets/theme/SpiffTheme', () => ({
  createSpiffTheme: (mode: 'light' | 'dark') => ({
    palette: {
      mode,
      background: { default: '#fff', light: '#f5f5f5' },
      primary: { main: '#1976d2' },
    },
  }),
}));

vi.mock('./components/RouteLoadingFallback', () => ({
  RouteLoadingFallback: () => <div data-testid="route-loading-fallback" />,
}));

vi.mock('./views/ReportsPage', () => ({
  default: () => <div data-testid="reports-page" />,
}));

vi.mock('./views/TenantManagementPage', () => ({
  default: () => <div data-testid="tenant-management-page" />,
}));

vi.mock('./views/TenantPage', () => ({
  default: () => <div data-testid="tenant-page" />,
}));

vi.mock('./views/TemplateGalleryPage', () => ({
  default: () => <div data-testid="template-gallery-page" />,
}));

vi.mock('./views/TemplateModelerPage', () => ({
  default: () => <div data-testid="template-modeler-page" />,
}));

vi.mock('./views/TemplateFileDiagramPage', () => ({
  default: () => <div data-testid="template-file-diagram-page" />,
}));

vi.mock('./views/TemplateFileFormPage', () => ({
  default: () => <div data-testid="template-file-form-page" />,
}));

vi.mock('./views/ProcessModelShowWithSaveAsTemplate', () => ({
  default: () => <div data-testid="process-model-show-page" />,
}));

vi.mock('./views/Connectors', () => ({
  default: () => <div data-testid="connectors-page" />,
}));

vi.mock('./hooks/M8flowUriListForPermissions', () => ({
  useM8flowUriListForPermissions: () => ({
    targetUris: {
      connectorsPath: '/connectors',
      dataStoreListPath: '/data-stores',
      extensionListPath: '/extensions',
      m8flowTenantListPath: '/tenants',
      m8flowTenantManagementPath: '/tenant-management',
      m8flowTemplateListPath: '/templates',
      messageInstanceListPath: '/messages',
      processGroupListPath: '/process-groups',
      processInstanceListForMePath: '/process-instances/for-me',
      processInstanceListPath: '/process-instances',
      secretListPath: '/secrets',
      statusPath: '/status',
    },
  }),
}));

vi.mock('@spiffworkflow-frontend/hooks/PermissionService', () => ({
  usePermissionFetcher: () => ({
    ability: { can },
    permissionsLoaded: true,
  }),
}));

vi.mock('./services/HttpService', () => ({
  default: {
    makeCallToBackend,
  },
}));

vi.mock('./services/UserService', () => ({
  default: {
    doLogout: vi.fn(),
    getCurrentLocation,
    hasSelectedTenantCookie: vi.fn(() => false),
    isLoggedIn,
    isSuperAdmin,
  },
}));

vi.mock('./utils/useConfig', () => ({
  useConfig: () => ({
    ENABLE_MULTITENANT: false,
  }),
}));

vi.mock('@spiffworkflow-frontend/hooks/UseApiError', () => ({
  default: () => ({
    removeError: vi.fn(),
  }),
}));

function LocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="location-probe">
      {location.pathname}
      {location.search}
    </div>
  );
}

const renderContainer = (initialEntry: string) => {
  return render(
    <ThemeProvider theme={createTheme()}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <LocationProbe />
        <ContainerForExtensions />
      </MemoryRouter>
    </ThemeProvider>,
  );
};

describe('ContainerForExtensions session recovery', () => {
  beforeEach(() => {
    can.mockReset();
    can.mockImplementation(() => true);
    isLoggedIn.mockReset();
    isSuperAdmin.mockReset();
    getCurrentLocation.mockReset();
    makeCallToBackend.mockReset();

    isSuperAdmin.mockReturnValue(true);
    getCurrentLocation.mockReturnValue(
      encodeURIComponent('http://localhost:3000/tenants'),
    );
    makeCallToBackend.mockImplementation(
      ({
        path,
        successCallback,
      }: {
        path: string;
        successCallback?: (payload: any) => void;
      }) => {
        if (path === '/status' && successCallback) {
          successCallback({ ok: true, can_access_frontend: false });
        }
        if (path === '/extensions' && successCallback) {
          successCallback([]);
        }
      },
    );
  });

  it('redirects an expired session on a protected route to the login route', async () => {
    isLoggedIn.mockReturnValue(false);

    renderContainer('/tenants');

    await screen.findByTestId('tenant-aware-login');
    const locationProbe = screen.getByTestId('location-probe');
    expect(locationProbe.textContent).toContain('/login');
    expect(locationProbe.textContent).toContain(
      'original_url=http%3A%2F%2Flocalhost%3A3000%2Ftenants',
    );
    expect(screen.queryByTestId('frontend-access-denied')).not.toBeInTheDocument();
  });

  it('allows the login route to render when the frontend access check fails for an expired session', async () => {
    isLoggedIn.mockReturnValue(false);

    renderContainer(
      '/login?original_url=http%3A%2F%2Flocalhost%3A3000%2Ftenants',
    );

    await screen.findByTestId('tenant-aware-login');
    expect(screen.getByTestId('location-probe').textContent).toContain('/login');
    expect(screen.queryByTestId('frontend-access-denied')).not.toBeInTheDocument();
  });

  it('keeps showing access denied for a still-logged-in user who truly lacks frontend access', async () => {
    isLoggedIn.mockReturnValue(true);

    renderContainer('/tenants');

    expect(
      await screen.findByTestId('frontend-access-denied'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('tenant-aware-login')).not.toBeInTheDocument();
  });
});
