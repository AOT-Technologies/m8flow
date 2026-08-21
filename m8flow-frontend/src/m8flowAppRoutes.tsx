/**
 * Primary React Router tree for the m8flow shell (lazy pages + gated routes).
 */
import { lazy, ReactElement, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Extension from '@spiffworkflow-frontend/views/Extension';
import BaseRoutes from '@spiffworkflow-frontend/views/BaseRoutes';
import { UiSchemaUxElement } from '@spiffworkflow-frontend/extension_ui_schema_interfaces';
import { RouteLoadingFallback } from './components/RouteLoadingFallback';
import UserService from './services/UserService';
import TenantAwareLogin from './views/TenantAwareLogin';
import TenantSelectPage from './views/TenantSelectPage';
import { MultitenantRootGate, RoleBasedRootGate, RootGateSharedProps } from './rootGates';

const ReportsPage = lazy(() => import('./views/ReportsPage'));
const TenantManagementPage = lazy(() => import('./views/TenantManagementPage'));
const TenantPage = lazy(() => import('./views/TenantPage'));
const TemplateGalleryPage = lazy(() => import('./views/TemplateGalleryPage'));
const TemplateModelerPage = lazy(() => import('./views/TemplateModelerPage'));
const TemplateFileDiagramPage = lazy(() => import('./views/TemplateFileDiagramPage'));
const TemplateFileFormPage = lazy(() => import('./views/TemplateFileFormPage'));
const ProcessModelShowWithSaveAsTemplate = lazy(
  () => import('./views/ProcessModelShowWithSaveAsTemplate'),
);
const ConnectorsPage = lazy(() => import('./views/Connectors'));
const ConnectorConfigurePage = lazy(() => import('./views/ConnectorConfigure'));
const McpConnectionPage = lazy(() => import('./views/McpConnection'));
const ManageTokenPage = lazy(() => import('./views/ManageToken'));
const MonitoringCeleryPage = lazy(() => import('./views/MonitoringCeleryPage'));
const MonitoringNatsPage = lazy(() => import('./views/MonitoringNatsPage'));
const ExternalFormAwareTaskShow = lazy(
  () => import('./views/ExternalFormAwareTaskShow'),
);

type AppRouteFlags = {
  ENABLE_MULTITENANT: boolean;
  NATS_MONITORING_ENABLED: boolean;
  MCP_CONNECTION_ENABLED: boolean;
};

type AppRouteAbility = RootGateSharedProps['ability'];
type AppRouteUris = RootGateSharedProps['targetUris'] & {
  processInstanceListForMePath: string;
  m8flowNatsEventsPath: string;
};

export type M8flowAppRoutesProps = {
  flags: AppRouteFlags;
  gateProps: RootGateSharedProps;
  ability: AppRouteAbility;
  targetUris: AppRouteUris;
  permissionsLoaded: boolean;
};

function gatedPage(
  permissionsLoaded: boolean,
  allowed: boolean,
  page: ReactElement,
): ReactElement | null {
  if (!permissionsLoaded) {
    return null;
  }
  return allowed ? page : <Navigate to="/" replace />;
}

function RootPathRoute({
  multitenant,
  gateProps,
}: {
  multitenant: boolean;
  gateProps: RootGateSharedProps;
}) {
  if (multitenant) {
    return <MultitenantRootGate {...gateProps} />;
  }
  return <RoleBasedRootGate {...gateProps} />;
}

type StaticRouteDef = {
  path: string;
  element: ReactElement;
  when?: boolean;
};

export function M8flowAppRoutes({
  flags,
  gateProps,
  ability,
  targetUris,
  permissionsLoaded,
}: M8flowAppRoutesProps) {
  const {
    ENABLE_MULTITENANT,
    NATS_MONITORING_ENABLED,
    MCP_CONNECTION_ENABLED,
  } = flags;

  const staticRoutes: StaticRouteDef[] = [
    { path: 'reports', element: <ReportsPage /> },
    {
      path: 'templates/:templateId/files/:fileName',
      element: <TemplateFileDiagramPage />,
    },
    {
      path: 'templates/:templateId/form/:fileName',
      element: <TemplateFileFormPage />,
    },
    { path: 'templates/:templateId', element: <TemplateModelerPage /> },
    { path: 'templates', element: <TemplateGalleryPage /> },
    {
      path: 'connectors/:connectorId/configure',
      element: <ConnectorConfigurePage />,
    },
    { path: 'connectors', element: <ConnectorsPage /> },
    {
      path: 'mcp-connection',
      element: <McpConnectionPage />,
      when: MCP_CONNECTION_ENABLED,
    },
    { path: 'manage-token', element: <ManageTokenPage /> },
    {
      path: 'process-models/:process_model_id',
      element: <ProcessModelShowWithSaveAsTemplate />,
    },
    { path: 'extensions/:page_identifier', element: <Extension /> },
    { path: 'login', element: <TenantAwareLogin /> },
    {
      path: 'tasks/:process_instance_id/:task_guid',
      element: <ExternalFormAwareTaskShow />,
    },
  ];

  const blockProcessInstances =
    permissionsLoaded &&
    !ability.can('GET', targetUris.processInstanceListForMePath) &&
    !ability.can('GET', targetUris.processInstanceListPath);

  return (
    <Suspense fallback={<RouteLoadingFallback />}>
      <Routes>
        <Route
          path="/"
          element={
            <RootPathRoute
              multitenant={ENABLE_MULTITENANT}
              gateProps={gateProps}
            />
          }
        />
        <Route
          path="tenant"
          element={
            ENABLE_MULTITENANT ? (
              <TenantSelectPage />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />

        <Route
          path="/tenant-management"
          element={gatedPage(
            permissionsLoaded,
            ability.can('GET', targetUris.m8flowTenantManagementPath),
            <TenantManagementPage />,
          )}
        />
        <Route
          path="/tenants"
          element={gatedPage(
            permissionsLoaded,
            UserService.isSuperAdmin() &&
              ability.can('GET', targetUris.m8flowTenantListPath),
            <TenantPage />,
          )}
        />

        {staticRoutes
          .filter((def) => def.when !== false)
          .map((def) => (
            <Route key={def.path} path={def.path} element={def.element} />
          ))}

        <Route
          path="monitoring/celery"
          element={gatedPage(
            permissionsLoaded,
            UserService.isSuperAdmin(),
            <MonitoringCeleryPage />,
          )}
        />
        {NATS_MONITORING_ENABLED && (
          <Route
            path="monitoring/nats"
            element={gatedPage(
              permissionsLoaded,
              // Tenant-admins get the event-history tab, so this is gated on the
              // read-nats-events grant rather than super-admin alone. The page itself
              // then hides the broker-wide tabs from non-super-admins.
              UserService.isSuperAdmin() ||
                ability.can('GET', targetUris.m8flowNatsEventsPath),
              <MonitoringNatsPage />,
            )}
          />
        )}

        {blockProcessInstances && (
          <Route
            path="process-instances/*"
            element={<Navigate to="/" replace />}
          />
        )}

        <Route
          path="*"
          element={
            <BaseRoutes
              extensionUxElements={gateProps.extensionUxElements}
              setAdditionalNavElement={gateProps.setAdditionalNavElement}
              isMobile={gateProps.isMobile}
            />
          }
        />
      </Routes>
    </Suspense>
  );
}
