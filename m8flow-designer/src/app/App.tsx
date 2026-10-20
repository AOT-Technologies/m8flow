import { lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import {
  createBrowserRouter,
  Navigate,
  Route,
  RouterProvider,
  Routes,
  useLocation,
  type RouteObject,
} from 'react-router-dom';

import { loadPageStrings } from '@/i18n';
import type { Translation } from '@/locales';
import { shouldShowTenantSelectionGate } from '@/lib/auth';
import { AppShell } from '@/components/layout/AppShell';
import { SessionProvider } from '@/components/session/SessionProvider';
import HomePage from '@/pages/home/HomePage';

// Lazy pages also need the lazily loaded English page strings; fetch both in parallel.
const lazyPage: typeof lazy = (load) =>
  lazy(() => Promise.all([load(), loadPageStrings()]).then(([module]) => module));

// Lazy, not a static import: bpmn-js/dmn-js's raw ESM (no file extensions on
// their internal imports) fails to resolve under Vitest's Node-based SSR
// module runner even though it builds/runs fine in a real browser — see
// .scratch/process-modeler/assets/02-library-integration-recipe.md. A static
// import here would pull that resolution failure into every test that
// renders <App/>, not just tests of this route. Also keeps the ~2MB
// bpmn-js+dmn-js+bpmn-js-spiffworkflow bundle out of the main app chunk.
const ProcessModelModelerPage = lazyPage(() => import('@/pages/process-model-modeler/ProcessModelModelerPage'));

// Lazy, same reasoning as ProcessModelModelerPage above minus the Vitest
// wrinkle (these two have no bpmn-js/dmn-js dependency, so nothing breaks
// under Vitest either way): a user landing on Home doesn't need either
// bundled into the main entry chunk yet. See
// .scratch/m8flow-designer-optimization/issues/05-lazy-load-remaining-routes.md.
const ProcessesPage = lazyPage(() => import('@/pages/processes/ProcessesPage'));
const ProcessModelDetailPage = lazyPage(() => import('@/pages/process-model-detail/ProcessModelDetailPage'));
const TemplatesPage = lazyPage(() => import('@/pages/templates/TemplatesPage'));
const TemplateModelerPage = lazyPage(() => import('@/pages/templates/TemplateModelerPage'));
// Lazy, same bpmn-js/dmn-js reasoning as ProcessModelModelerPage above —
// this page reuses the same DiagramCanvas/BpmnCanvas/DmnCanvas bundle.
const TemplateFileModelerPage = lazyPage(() => import('@/pages/templates/TemplateFileModelerPage'));
const ProcessInstancesPage = lazyPage(() => import('@/pages/process-instances/ProcessInstancesPage'));
// Lazy, same bpmn-js reasoning as ProcessModelModelerPage / TemplateFileModelerPage.
const ProcessInstanceDetailPage = lazyPage(() => import('@/pages/process-instances/ProcessInstanceDetailPage'));
// Task Review — inbox list + single-task review detail. Lazy to keep them out
// of the main entry chunk (same reasoning as the other page routes above).
const TaskReviewInboxPage = lazyPage(() => import('@/pages/task-review/TaskReviewInboxPage'));
const TaskReviewDetailPage = lazyPage(() => import('@/pages/task-review/TaskReviewDetailPage'));
const TenantsPage = lazyPage(() => import('@/pages/tenants/TenantsPage'));
const TenantManagementPage = lazyPage(() => import('@/pages/tenant-management/TenantManagementPage'));
const SecretListPage = lazyPage(() => import('@/pages/configuration/SecretListPage'));
const SecretNewPage = lazyPage(() => import('@/pages/configuration/SecretNewPage'));
const SecretShowPage = lazyPage(() => import('@/pages/configuration/SecretShowPage'));
const ConnectorsPage = lazyPage(() => import('@/pages/connectors/ConnectorsPage'));
const ConnectorProfilesPage = lazyPage(() => import('@/pages/connectors/ConnectorProfilesPage'));
const ConnectorProfileEditPage = lazyPage(() => import('@/pages/connectors/ConnectorProfileEditPage'));
const McpConnectionPage = lazyPage(() => import('@/pages/mcp-connection/McpConnectionPage'));
const McpToolsPage = lazyPage(() => import('@/pages/mcp-tools/McpToolsPage'));
const MessagesPage = lazyPage(() => import('@/pages/messages/MessagesPage'));
const NatsMonitorPage = lazyPage(() => import('@/pages/nats/NatsMonitorPage'));
const ApiKeysPage = lazyPage(() => import('@/pages/api-keys/ApiKeysPage'));
// Lazy: an invite link and the one-time tenant choice are rare entry points,
// so most visits shouldn't download them with the first page.
const TenantSelectPage = lazyPage(() => import('@/pages/tenant-select/TenantSelectPage'));
const AcceptInvitationPage = lazyPage(() => import('@/pages/accept-invitation/AcceptInvitationPage'));

const GATE_PATHS = new Set(['/', '/tenant']);

// A fallback renders before its page's strings load (en-pages), so it may only use the
// eagerly bundled shell keys; anything else would show as a raw key.
type RouteLoadingKey = `shell.routeLoading.${keyof Translation['shell']['routeLoading']}`;

function LoadingFallback({ labelKey }: { labelKey: RouteLoadingKey }) {
  const { t } = useTranslation();
  return <p className="p-6 text-sm text-muted-foreground">{t(labelKey)}</p>;
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
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.processes" />}>
              <ProcessesPage />
            </Suspense>
          }
        />
        <Route
          path="processes/:processModelId"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.process" />}>
              <ProcessModelDetailPage />
            </Suspense>
          }
        />
        <Route
          path="processes/:processModelId/modeler/:fileName"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.modeler" />}>
              <ProcessModelModelerPage />
            </Suspense>
          }
        />
        <Route
          path="templates"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.templates" />}>
              <TemplatesPage />
            </Suspense>
          }
        />
        <Route
          path="templates/:templateId/modeler/:fileName"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.templateFile" />}>
              <TemplateFileModelerPage />
            </Suspense>
          }
        />
        <Route
          path="templates/:templateId"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.template" />}>
              <TemplateModelerPage />
            </Suspense>
          }
        />
        <Route
          path="process-instances"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.processInstances" />}>
              <ProcessInstancesPage />
            </Suspense>
          }
        />
        <Route
          path="process-instances/:instanceId"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.processInstance" />}>
              <ProcessInstanceDetailPage />
            </Suspense>
          }
        />
        <Route
          path="task-review"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.tasks" />}>
              <TaskReviewInboxPage />
            </Suspense>
          }
        />
        <Route
          path="task-review/:taskId"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.task" />}>
              <TaskReviewDetailPage />
            </Suspense>
          }
        />
        <Route
          path="tenants"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.tenants" />}>
              <TenantsPage />
            </Suspense>
          }
        />
        <Route
          path="tenant-management"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.tenantManagement" />}>
              <TenantManagementPage />
            </Suspense>
          }
        />
        <Route
          path="tenant-management/:tenantId"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.tenantManagement" />}>
              <TenantManagementPage />
            </Suspense>
          }
        />
        <Route path="configuration" element={<Navigate to="/configuration/secrets" replace />} />
        <Route
          path="configuration/secrets"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.secrets" />}>
              <SecretListPage />
            </Suspense>
          }
        />
        <Route
          path="configuration/secrets/new"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.secrets" />}>
              <SecretNewPage />
            </Suspense>
          }
        />
        <Route
          path="configuration/secrets/:key"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.secret" />}>
              <SecretShowPage />
            </Suspense>
          }
        />
        <Route
          path="connectors"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.connectors" />}>
              <ConnectorsPage />
            </Suspense>
          }
        />
        <Route
          path="connectors/:connectorId/profiles/new"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.profile" />}>
              <ConnectorProfileEditPage />
            </Suspense>
          }
        />
        <Route
          path="connectors/:connectorId/profiles/:profileId/edit"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.profile" />}>
              <ConnectorProfileEditPage />
            </Suspense>
          }
        />
        <Route
          path="connectors/:connectorId/profiles"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.profiles" />}>
              <ConnectorProfilesPage />
            </Suspense>
          }
        />
        <Route
          path="mcp-connection"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.mcpConnection" />}>
              <McpConnectionPage />
            </Suspense>
          }
        />
        <Route
          path="mcp-tools"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.mcpTools" />}>
              <McpToolsPage />
            </Suspense>
          }
        />
        <Route
          path="messages"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.messages" />}>
              <MessagesPage />
            </Suspense>
          }
        />
        <Route
          path="system/nats"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.nats" />}>
              <NatsMonitorPage />
            </Suspense>
          }
        />
        <Route
          path="api-keys"
          element={
            <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.apiKeys" />}>
              <ApiKeysPage />
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
    return (
      <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.invitation" />}>
        <AcceptInvitationPage />
      </Suspense>
    );
  }

  if (shouldShowTenantSelectionGate(pathname)) {
    if (!GATE_PATHS.has(pathname)) {
      return <Navigate to="/" replace />;
    }
    return (
      <Suspense fallback={<LoadingFallback labelKey="shell.routeLoading.tenants" />}>
        <TenantSelectPage />
      </Suspense>
    );
  }

  return <AppShellRoutes />;
}

// A data router rather than <BrowserRouter> so pages can use useBlocker (guards
// browser Back/Forward, not just link clicks). The existing <Routes> tree is
// mounted unchanged under one catch-all route: React Router's documented
// incremental-migration pattern (descendant <Routes> are supported; only
// loaders/actions need routes lifted into this list, and none are used).
// Exported so App.test builds its memory router from the same list.
export const appRoutes: RouteObject[] = [{ path: '*', element: <AppRoutes /> }];

const router = createBrowserRouter(appRoutes);

export default function App() {
  return <RouterProvider router={router} />;
}
