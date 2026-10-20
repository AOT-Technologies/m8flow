import { useTranslation } from 'react-i18next';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { getCurrentUser, logout } from '@/lib/auth';
import { useActiveTenant, useCapabilities, useTenantRegistry } from '@/components/session/hooks';
import { Sidebar } from './Sidebar';

const CELERY_MONITORING_URL = import.meta.env.VITE_M8FLOW_CELERY_FLOWER_URL ?? '';

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
  const { t } = useTranslation();
  const user = getCurrentUser();
  const { selectedTenantId, isSuperAdmin: superAdmin, setSelectedTenant } = useActiveTenant();
  const {
    canReadSecrets,
    canReadConnectors,
    canSubmitTaskReviews,
    canReadTaskReview,
    canReadMcpConnection,
    canReadMcpTools,
    canReadMessages,
    canReadNatsMonitoring,
    canReadNatsEvents,
    canReadTemplates,
    canAccessTenantManagement,
    canReadProcesses,
    canReadProcessInstances,
    canReadNatsApiKeys,
    status,
  } = useCapabilities();
  // Submit permission grants task work; GET permission supports read-only monitoring.
  const canOpenTaskReview = canSubmitTaskReviews || canReadTaskReview;
  const { pathname } = useLocation();
  // NATS page: broker monitoring (super-admin) and own-tenant event history (tenant-admin).
  const canUseNats = canReadNatsMonitoring || canReadNatsEvents;
  const routePermission = pathname.startsWith('/task-review')
    ? canOpenTaskReview
    : pathname.startsWith('/tenant-management')
      ? canAccessTenantManagement
    : pathname.startsWith('/messages')
      ? canReadMessages
    : pathname.startsWith('/system/nats')
      ? canUseNats
    : pathname.startsWith('/mcp-connection')
      ? canReadMcpConnection
    : pathname.startsWith('/mcp-tools')
      ? canReadMcpTools
    : pathname.startsWith('/connectors')
      ? canReadConnectors
    : pathname.startsWith('/api-keys')
      ? canReadNatsApiKeys
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

  const userLabel = user?.username ?? user?.email ?? t('shell.profile.unknownUser');
  const tenantOptions =
    selectedTenantId && !tenants.some((t) => t.id === selectedTenantId)
      ? [{ id: selectedTenantId, name: selectedTenantId }, ...tenants]
      : tenants;

  if (status === 'loading') return <p role="status">{t('shell.permissions.loading')}</p>;
  if (status === 'error') return <p role="alert">{t('shell.permissions.loadFailed')}</p>;

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar
        showProcesses={canReadProcesses}
        showProcessInstances={canReadProcessInstances}
        showTaskReview={canOpenTaskReview}
        showSystem={(superAdmin && Boolean(CELERY_MONITORING_URL)) || canUseNats}
        celeryMonitoringUrl={superAdmin ? celeryWorkersUrl(CELERY_MONITORING_URL) : ''}
        showNatsMonitoring={canUseNats}
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
        showSetup={canReadSecrets || canReadConnectors || canReadTemplates || canReadNatsApiKeys}
        showTemplates={canReadTemplates}
        showApiKeys={canReadNatsApiKeys}
        showMcpConnection={canReadMcpConnection}
        showMcpTools={canReadMcpTools}
        showMessages={canReadMessages}
        showTenantsNav={superAdmin}
        showTenantManagement={canAccessTenantManagement && !superAdmin}
      />
      {routePermission ? <Outlet /> : <Navigate to="/" replace />}
    </div>
  );
}
