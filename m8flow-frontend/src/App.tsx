import { defineAbility } from '@casl/ability';
import {
  createBrowserRouter,
  Outlet,
  RouterProvider,
} from 'react-router-dom';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense, lazy, useEffect, useState } from 'react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Typography from '@mui/material/Typography';
import { AbilityContext } from '@spiffworkflow-frontend/contexts/Can';
import APIErrorProvider from '@spiffworkflow-frontend/contexts/APIErrorContext';
import { createSpiffTheme } from '@spiffworkflow-frontend/assets/theme/SpiffTheme';
// m8 Extension: Import local override of ContainerForExtensions
import ContainerForExtensions from './ContainerForExtensions';
import { RouteLoadingFallback } from './components/RouteLoadingFallback';
import PublicRoutes from '@spiffworkflow-frontend/views/PublicRoutes';
import { CONFIGURATION_ERRORS } from '@spiffworkflow-frontend/config';
// m8 Extension: Custom grouping context
import { CustomGroupingProvider } from './contexts/CustomGroupingContext';
import TenantGateContext from './contexts/TenantGateContext';
import { useConfig } from './utils/useConfig';
import UserService from './services/UserService';

const queryClient = new QueryClient();

const TenantSelectPage = lazy(() => import('./views/TenantSelectPage'));

function hasFinalizedTenantSelection(): boolean {
  if (typeof globalThis === 'undefined') return false;
  return UserService.hasSelectedTenantCookie();
}

function getCurrentPathname(): string {
  if (typeof globalThis === 'undefined' || !globalThis.location) {
    return '/';
  }
  return globalThis.location.pathname;
}

function getCurrentLocation(): string {
  if (typeof globalThis === 'undefined' || !globalThis.location) {
    return '/';
  }
  return `${globalThis.location.origin}${globalThis.location.pathname}${globalThis.location.search || ''}`;
}

function isTenantSelectionExemptPath(pathname: string): boolean {
  return (
    pathname === '/login' ||
    pathname === '/tenants' ||
    pathname.startsWith('/public/')
  );
}

function shouldShowTenantSelectionGate(
  pathname: string,
  masterRealmIdentifier: string,
): boolean {
  if (isTenantSelectionExemptPath(pathname)) {
    return false;
  }

  if (!UserService.isLoggedIn()) {
    return true;
  }

  if (UserService.getAuthenticationIdentifier() === masterRealmIdentifier) {
    return false;
  }

  return !hasFinalizedTenantSelection();
}

function AutoLoginRedirect({
  sharedRealmIdentifier,
}: {
  sharedRealmIdentifier: string;
}) {
  useEffect(() => {
    UserService.doLogin(
      {
        identifier: sharedRealmIdentifier,
        label: sharedRealmIdentifier,
        uri: '',
      },
      getCurrentLocation(),
    );
  }, [sharedRealmIdentifier]);

  return <Typography align="center">Redirecting to sign in...</Typography>;
}

export default function App() {
  const ability = defineAbility(() => {});
  const { ENABLE_MULTITENANT, MASTER_REALM_IDENTIFIER, SHARED_REALM_IDENTIFIER } = useConfig();
  const [hasTenant, setHasTenant] = useState(hasFinalizedTenantSelection);
  const currentPathname = getCurrentPathname();
  const showTenantSelectionGate = shouldShowTenantSelectionGate(
    currentPathname,
    MASTER_REALM_IDENTIFIER,
  );

  // When multitenant is on and no tenant is stored, avoid mounting the main app.
  // Unauthenticated users go straight into the shared-realm login flow; authenticated
  // shared-realm users without a finalized tenant still see the tenant-selection page.
  // This avoids mounting ContainerForExtensions (and its permission check), which would 401 and redirect to login.
  if (ENABLE_MULTITENANT && !hasTenant && showTenantSelectionGate) {
    const minimalTheme = createTheme(
      createSpiffTheme(
        (typeof globalThis !== 'undefined' &&
          (localStorage.getItem('theme') as 'light' | 'dark')) ||
          'light'
      )
    );
    return (
      <div className="cds--white">
        <ThemeProvider theme={minimalTheme}>
          <CssBaseline />
          <QueryClientProvider client={queryClient}>
            <APIErrorProvider>
              <AbilityContext.Provider value={ability}>
                <TenantGateContext.Provider
                  value={{ onTenantSelected: () => setHasTenant(true) }}
                >
                  <Suspense fallback={<RouteLoadingFallback />}>
                    {UserService.isLoggedIn() ? (
                      <TenantSelectPage />
                    ) : (
                      <AutoLoginRedirect
                        sharedRealmIdentifier={SHARED_REALM_IDENTIFIER}
                      />
                    )}
                  </Suspense>
                </TenantGateContext.Provider>
              </AbilityContext.Provider>
            </APIErrorProvider>
          </QueryClientProvider>
        </ThemeProvider>
      </div>
    );
  }

  const routeComponents = () => {
    return [
      { path: 'public/*', element: <PublicRoutes /> },
      {
        path: '*',
        element: <ContainerForExtensions />,
      },
    ];
  };

  /**
   * Note that QueryClientProvider and ReactQueryDevTools
   * are React Query, now branded under the Tanstack packages.
   * https://tanstack.com/query/latest
   */
  const layout = () => {
    if (CONFIGURATION_ERRORS.length > 0) {
      return (
        <div style={{ padding: '20px', color: 'red' }}>
          <h2>Configuration Errors</h2>
          <ul>
            {CONFIGURATION_ERRORS.map((error: string, index: number) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      );
    }
    return (
      <div className="cds--white">
        <QueryClientProvider client={queryClient}>
          <APIErrorProvider>
            <AbilityContext.Provider value={ability}>
              {/* m8 Extension: Wrap with custom grouping provider */}
              <CustomGroupingProvider>
                <Outlet />
              </CustomGroupingProvider>
              <ReactQueryDevtools initialIsOpen={false} />
            </AbilityContext.Provider>
          </APIErrorProvider>
        </QueryClientProvider>
      </div>
    );
  };
  const router = createBrowserRouter([
    {
      path: '*',
      Component: layout,
      children: routeComponents(),
    },
  ]);
  return <RouterProvider router={router} />;
}
