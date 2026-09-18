import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { getCurrentUser, logout } from '@/lib/auth';
import { useActiveTenant, useCapabilities, useTenantRegistry } from '@/components/session/hooks';
import { Sidebar } from './Sidebar';

const CELERY_MONITORING_URL = import.meta.env.VITE_M8FLOW_CELERY_FLOWER_URL ?? '';
const NATS_MONITORING_URL = import.meta.env.VITE_M8FLOW_NATS_UI_URL ?? '';

function celeryWorkersUrl(baseUrl: string): string {
  return baseUrl ? `${baseUrl.replace(/\/+$/, '')}/workers` : '';
}

/**
 * Shared chrome: Sidebar + tenant/logout wiring + `<Outlet />` for page content.
 *
 * Layout only. Session state lives in `SessionProvider` (mounted above this in
 * App.tsx); pages read it through `useActiveTenant` / `useCapabilities` /
 * `useTenantRegistry`. AppShell reads the same hooks purely to drive the sidebar
 * chrome — it no longer provides an outlet context.
 */
export function AppShell() {
  const user = getCurrentUser();
  const { selectedTenantId, isSuperAdmin: superAdmin, setSelectedTenant } = useActiveTenant();
  const {
    canReadSecrets,
    canReadConnectors,
    canReviewTasks,
    canReadMcpConnection,
    canReadMessages,
    canReadTemplates,
    canManageTenant,
    canReadProcesses,
    canReadProcessInstances,
    status,
  } = useCapabilities();
  const { pathname } = useLocation();
  const routePermission = pathname.startsWith('/task-review')
    ? canReviewTasks
    : pathname.startsWith('/messages')
      ? canReadMessages
    : pathname.startsWith('/mcp-connection')
      ? canReadMcpConnection
    : pathname.startsWith('/connectors')
      ? canReadConnectors
      : pathname.startsWith('/configuration')
        ? canReadSecrets
        : pathname.startsWith('/templates')
          ? canReadTemplates
          : pathname.startsWith('/process-instances')
            ? canReadProcessInstances
            : pathname.startsWith('/processes')
              ? canReadProcesses
              : true;
  const { tenants, organizationMemberships, activeTenantLabel } = useTenantRegistry();

  const userLabel = user?.username ?? user?.email ?? 'unknown user';
  const tenantOptions =
    selectedTenantId && !tenants.some((t) => t.id === selectedTenantId)
      ? [{ id: selectedTenantId, name: selectedTenantId }, ...tenants]
      : tenants;

  if (status === 'loading') return <p role="status">Loading permissions…</p>;
  if (status === 'error') return <p role="alert">Unable to load permissions. Reload to try again.</p>;

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar
        showProcesses={canReadProcesses}
        showProcessInstances={canReadProcessInstances}
        showTaskReview={canReviewTasks}
        showSystem={superAdmin && Boolean(CELERY_MONITORING_URL || NATS_MONITORING_URL)}
        celeryMonitoringUrl={celeryWorkersUrl(CELERY_MONITORING_URL)}
        natsMonitoringUrl={NATS_MONITORING_URL}
        showTenantSelector={superAdmin}
        selectedTenantId={selectedTenantId}
        onTenantChange={setSelectedTenant}
        tenants={tenantOptions}
        activeTenantLabel={activeTenantLabel}
        organizations={organizationMemberships}
        onLogout={logout}
        userLabel={userLabel}
        showConfiguration={canReadSecrets}
        showConnectors={canReadConnectors}
        showSetup={canReadSecrets || canReadConnectors || canReadTemplates}
        showTemplates={canReadTemplates}
        showMcpConnection={canReadMcpConnection}
        showMessages={canReadMessages}
        showTenantsNav={superAdmin}
        showTenantManagement={canManageTenant && !superAdmin}
      />
      {routePermission ? <Outlet /> : <Navigate to="/" replace />}
    </div>
  );
}
