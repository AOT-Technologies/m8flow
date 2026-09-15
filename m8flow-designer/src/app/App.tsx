import { lazy, Suspense } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { shouldShowTenantSelectionGate } from '@/lib/auth';
import { AppShell } from '@/components/layout/AppShell';
import { SessionProvider } from '@/components/session/SessionProvider';
import HomePage from '@/pages/home/HomePage';
import TenantSelectPage from '@/pages/tenant-select/TenantSelectPage';
import AcceptInvitationPage from '@/pages/accept-invitation/AcceptInvitationPage';

// Lazy, not a static import: bpmn-js/dmn-js's raw ESM (no file extensions on
// their internal imports) fails to resolve under Vitest's Node-based SSR
// module runner even though it builds/runs fine in a real browser — see
// .scratch/process-modeler/assets/02-library-integration-recipe.md. A static
// import here would pull that resolution failure into every test that
// renders <App/>, not just tests of this route. Also keeps the ~2MB
// bpmn-js+dmn-js+bpmn-js-spiffworkflow bundle out of the main app chunk.
const ProcessModelModelerPage = lazy(() => import('@/pages/process-model-modeler/ProcessModelModelerPage'));

// Lazy, same reasoning as ProcessModelModelerPage above minus the Vitest
// wrinkle (these two have no bpmn-js/dmn-js dependency, so nothing breaks
// under Vitest either way): a user landing on Home doesn't need either
// bundled into the main entry chunk yet. See
// .scratch/m8flow-designer-optimization/issues/05-lazy-load-remaining-routes.md.
const ProcessesPage = lazy(() => import('@/pages/processes/ProcessesPage'));
const ProcessModelDetailPage = lazy(() => import('@/pages/process-model-detail/ProcessModelDetailPage'));
const TemplatesPage = lazy(() => import('@/pages/templates/TemplatesPage'));
const TemplateModelerPage = lazy(() => import('@/pages/templates/TemplateModelerPage'));
// Lazy, same bpmn-js/dmn-js reasoning as ProcessModelModelerPage above —
// this page reuses the same DiagramCanvas/BpmnCanvas/DmnCanvas bundle.
const TemplateFileModelerPage = lazy(() => import('@/pages/templates/TemplateFileModelerPage'));
const ProcessInstancesPage = lazy(() => import('@/pages/process-instances/ProcessInstancesPage'));
// Lazy, same bpmn-js reasoning as ProcessModelModelerPage / TemplateFileModelerPage.
const ProcessInstanceDetailPage = lazy(() => import('@/pages/process-instances/ProcessInstanceDetailPage'));
// Task Review — inbox list + single-task review detail. Lazy to keep them out
// of the main entry chunk (same reasoning as the other page routes above).
const TaskReviewInboxPage = lazy(() => import('@/pages/task-review/TaskReviewInboxPage'));
const TaskReviewDetailPage = lazy(() => import('@/pages/task-review/TaskReviewDetailPage'));
const TenantsPage = lazy(() => import('@/pages/tenants/TenantsPage'));
const TenantManagementPage = lazy(() => import('@/pages/tenant-management/TenantManagementPage'));
const SecretListPage = lazy(() => import('@/pages/configuration/SecretListPage'));
const SecretNewPage = lazy(() => import('@/pages/configuration/SecretNewPage'));
const SecretShowPage = lazy(() => import('@/pages/configuration/SecretShowPage'));
const ConnectorsPage = lazy(() => import('@/pages/connectors/ConnectorsPage'));
const ConnectorProfilesPage = lazy(() => import('@/pages/connectors/ConnectorProfilesPage'));
const ConnectorProfileEditPage = lazy(() => import('@/pages/connectors/ConnectorProfileEditPage'));

const GATE_PATHS = new Set(['/', '/tenant']);

function LoadingFallback({ label }: { label: string }) {
  return <p className="p-6 text-sm text-muted-foreground">{label}</p>;
}

function AppShellRoutes() {
  return (
    <Routes>
      <Route
        element={
          <SessionProvider>
            <AppShell />
          </SessionProvider>
        }
      >
        <Route index element={<HomePage />} />
        <Route
          path="processes"
          element={
            <Suspense fallback={<LoadingFallback label="Loading processes…" />}>
              <ProcessesPage />
            </Suspense>
          }
        />
        <Route
          path="processes/:processModelId"
          element={
            <Suspense fallback={<LoadingFallback label="Loading process…" />}>
              <ProcessModelDetailPage />
            </Suspense>
          }
        />
        <Route
          path="processes/:processModelId/modeler/:fileName"
          element={
            <Suspense fallback={<LoadingFallback label="Loading modeler…" />}>
              <ProcessModelModelerPage />
            </Suspense>
          }
        />
        <Route
          path="templates"
          element={
            <Suspense fallback={<LoadingFallback label="Loading templates…" />}>
              <TemplatesPage />
            </Suspense>
          }
        />
        <Route
          path="templates/:templateId/modeler/:fileName"
          element={
            <Suspense fallback={<LoadingFallback label="Loading template file…" />}>
              <TemplateFileModelerPage />
            </Suspense>
          }
        />
        <Route
          path="templates/:templateId"
          element={
            <Suspense fallback={<LoadingFallback label="Loading template…" />}>
              <TemplateModelerPage />
            </Suspense>
          }
        />
        <Route
          path="process-instances"
          element={
            <Suspense fallback={<LoadingFallback label="Loading process instances…" />}>
              <ProcessInstancesPage />
            </Suspense>
          }
        />
        <Route
          path="process-instances/:instanceId"
          element={
            <Suspense fallback={<LoadingFallback label="Loading process instance…" />}>
              <ProcessInstanceDetailPage />
            </Suspense>
          }
        />
        <Route
          path="task-review"
          element={
            <Suspense fallback={<LoadingFallback label="Loading tasks…" />}>
              <TaskReviewInboxPage />
            </Suspense>
          }
        />
        <Route
          path="task-review/:taskId"
          element={
            <Suspense fallback={<LoadingFallback label="Loading task…" />}>
              <TaskReviewDetailPage />
            </Suspense>
          }
        />
        <Route
          path="tenants"
          element={
            <Suspense fallback={<LoadingFallback label="Loading tenants…" />}>
              <TenantsPage />
            </Suspense>
          }
        />
        <Route
          path="tenant-management"
          element={
            <Suspense fallback={<LoadingFallback label="Loading tenant management…" />}>
              <TenantManagementPage />
            </Suspense>
          }
        />
        <Route
          path="tenant-management/:tenantId"
          element={
            <Suspense fallback={<LoadingFallback label="Loading tenant management…" />}>
              <TenantManagementPage />
            </Suspense>
          }
        />
        <Route path="configuration" element={<Navigate to="/configuration/secrets" replace />} />
        <Route
          path="configuration/secrets"
          element={
            <Suspense fallback={<LoadingFallback label="Loading secrets…" />}>
              <SecretListPage />
            </Suspense>
          }
        />
        <Route
          path="configuration/secrets/new"
          element={
            <Suspense fallback={<LoadingFallback label="Loading secrets…" />}>
              <SecretNewPage />
            </Suspense>
          }
        />
        <Route
          path="configuration/secrets/:key"
          element={
            <Suspense fallback={<LoadingFallback label="Loading secret…" />}>
              <SecretShowPage />
            </Suspense>
          }
        />
        <Route
          path="connectors"
          element={
            <Suspense fallback={<LoadingFallback label="Loading connectors…" />}>
              <ConnectorsPage />
            </Suspense>
          }
        />
        <Route
          path="connectors/:connectorId/profiles/new"
          element={
            <Suspense fallback={<LoadingFallback label="Loading profile…" />}>
              <ConnectorProfileEditPage />
            </Suspense>
          }
        />
        <Route
          path="connectors/:connectorId/profiles/:profileId/edit"
          element={
            <Suspense fallback={<LoadingFallback label="Loading profile…" />}>
              <ConnectorProfileEditPage />
            </Suspense>
          }
        />
        <Route
          path="connectors/:connectorId/profiles"
          element={
            <Suspense fallback={<LoadingFallback label="Loading profiles…" />}>
              <ConnectorProfilesPage />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function AppRoutes() {
  const { pathname } = useLocation();

  if (pathname === '/accept-invitation' || pathname.startsWith('/accept-invitation/')) {
    return <AcceptInvitationPage />;
  }

  if (shouldShowTenantSelectionGate(pathname)) {
    if (!GATE_PATHS.has(pathname)) {
      return <Navigate to="/" replace />;
    }
    return <TenantSelectPage />;
  }

  return <AppShellRoutes />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
