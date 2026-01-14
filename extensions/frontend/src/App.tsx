import { defineAbility } from '@casl/ability';
import { createBrowserRouter, Outlet, RouterProvider } from 'react-router-dom';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AbilityContext } from '@spiffworkflow-frontend/contexts/Can';
import APIErrorProvider from '@spiffworkflow-frontend/contexts/APIErrorContext';
// M8Flow Extension: Import local override of ContainerForExtensions
import ContainerForExtensions from './ContainerForExtensions';
import PublicRoutes from '@spiffworkflow-frontend/views/PublicRoutes';
import { CONFIGURATION_ERRORS } from '@spiffworkflow-frontend/config';
// M8Flow Extension: Custom grouping context
import { CustomGroupingProvider } from './contexts/CustomGroupingContext';

const queryClient = new QueryClient();

export default function App() {
  const ability = defineAbility(() => {});
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
