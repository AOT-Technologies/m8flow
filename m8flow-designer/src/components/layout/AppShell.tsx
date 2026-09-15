import { Outlet } from 'react-router-dom';

import { getCurrentUser, logout } from '@/lib/auth';
import { useActiveTenant, useCapabilities, useTenantRegistry } from '@/components/session/hooks';
import { Sidebar } from './Sidebar';

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
  const { canReadSecrets, canReadConnectors, canManageTenant } = useCapabilities();
  const { tenants, organizationMemberships, activeTenantLabel } = useTenantRegistry();

  const userLabel = user?.username ?? user?.email ?? 'unknown user';
  const tenantOptions =
    selectedTenantId && !tenants.some((t) => t.id === selectedTenantId)
      ? [{ id: selectedTenantId, name: selectedTenantId }, ...tenants]
      : tenants;

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar
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
        showTenantsNav={superAdmin}
        showTenantManagement={canManageTenant && !superAdmin}
      />
      <Outlet />
    </div>
  );
}
