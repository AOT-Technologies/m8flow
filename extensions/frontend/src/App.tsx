import { defineAbility } from '@casl/ability';
import {
  BrowserRouter,
  createBrowserRouter,
  Outlet,
  RouterProvider,
} from 'react-router-dom';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { AbilityContext } from '@spiffworkflow-frontend/contexts/Can';
import APIErrorProvider from '@spiffworkflow-frontend/contexts/APIErrorContext';
import { createSpiffTheme } from '@spiffworkflow-frontend/assets/theme/SpiffTheme';
// M8Flow Extension: Import local override of ContainerForExtensions
import ContainerForExtensions from './ContainerForExtensions';
import PublicRoutes from '@spiffworkflow-frontend/views/PublicRoutes';
import { CONFIGURATION_ERRORS } from '@spiffworkflow-frontend/config';
// M8Flow Extension: Custom grouping context
import { CustomGroupingProvider } from './contexts/CustomGroupingContext';
import TenantGateContext from './contexts/TenantGateContext';
import TenantSelectPage from './views/TenantSelectPage';
import { useConfig } from './utils/useConfig';
import { M8FLOW_TENANT_STORAGE_KEY } from './views/TenantSelectPage';

const queryClient = new QueryClient();

function getStoredTenant(): boolean {
  if (typeof window === 'undefined') return false;
  return !!localStorage.getItem(M8FLOW_TENANT_STORAGE_KEY);
}

// #region agent log
const DEBUG_LOG = (payload: Record<string, unknown>) => {
  fetch('http://127.0.0.1:7243/ingest/603ec126-81cd-4be3-ba0d-84501c09e628', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...payload,
      timestamp: Date.now(),
      sessionId: 'debug-session',
    }),
  }).catch(() => {});
};
// #endregion

export default function App() {
  const ability = defineAbility(() => {});
  const { ENABLE_MULTITENANT } = useConfig();
  const [hasTenant, setHasTenant] = useState(getStoredTenant);

  // #region agent log
  const storedRaw =
    typeof window !== 'undefined'
      ? localStorage.getItem(M8FLOW_TENANT_STORAGE_KEY)
      : null;
  DEBUG_LOG({
    hypothesisId: 'A_B_E',
    location: 'App.tsx:render',
    message: 'App render branch check',
    data: {
      ENABLE_MULTITENANT,
      hasTenant,
      storedRaw,
      takingMinimalBranch: ENABLE_MULTITENANT && !hasTenant,
    },
  });
  // #endregion

  // When multitenant is on and no tenant is stored, show only the tenant page.
  // This avoids mounting ContainerForExtensions (and its permission check), which would 401 and redirect to login.
  if (ENABLE_MULTITENANT && !hasTenant) {
    // #region agent log
    DEBUG_LOG({
      hypothesisId: 'D',
      location: 'App.tsx:minimal-branch',
      message: 'Rendering minimal view (TenantSelectPage only)',
      data: {},
    });
    // #endregion
    const minimalTheme = createTheme(
      createSpiffTheme(
        (typeof window !== 'undefined' && (localStorage.getItem('theme') as 'light' | 'dark')) || 'light'
      )
    );
    return (
      <BrowserRouter>
        <div className="cds--white">
          <ThemeProvider theme={minimalTheme}>
            <CssBaseline />
            <QueryClientProvider client={queryClient}>
              <APIErrorProvider>
                <AbilityContext.Provider value={ability}>
                  <TenantGateContext.Provider
                    value={{ onTenantSelected: () => setHasTenant(true) }}
                  >
                    <TenantSelectPage />
                  </TenantGateContext.Provider>
                </AbilityContext.Provider>
              </APIErrorProvider>
            </QueryClientProvider>
          </ThemeProvider>
        </div>
      </BrowserRouter>
    );
  }

  // #region agent log
  DEBUG_LOG({
    hypothesisId: 'D',
    location: 'App.tsx:full-router',
    message: 'Rendering full router (ContainerForExtensions will mount)',
    data: {},
  });
  // #endregion

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
            {CONFIGURATION_ERRORS.map((error, index) => (
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
              {/* M8Flow Extension: Wrap with custom grouping provider */}
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
