import { Navigate, useLocation, useParams } from 'react-router-dom';

import { useActiveTenant, useCapabilities, useTenantRegistry } from '@/components/session/hooks';
import { Card } from '@/components/ui/card';
import { getActiveTenantDisplayLabel } from '@/lib/auth';
import type { TenantStatus } from '@/lib/tenantsApi';
import TenantAdminPanel from './TenantAdminPanel';

type TenantManagementLocationState = {
  tenantName?: string;
  /**
   * Carried from `TenantsPage`'s already-fetched registry row (super-admin
   * only) so the header can show the mockup's alias/status without a
   * second fetch. Absent on the tenant-admin's own-tenant path (bare
   * `/tenant-management`) and on direct navigation to a super-admin URL —
   * `TenantAdminPanel` renders without them rather than fetching, since
   * `/v1.0/m8flow/tenants` is registry-scoped (super-admin only).
   */
  tenantSlug?: string;
  tenantStatus?: TenantStatus;
};

/**
 * Tenant admin for one tenant.
 *
 * Tenant-admin: `/tenant-management` uses the active-tenant cookie.
 * Super-admin: `/tenant-management/:tenantId` after picking a row on `/tenants`.
 * Bare `/tenant-management` for a super-admin redirects to the registry.
 * Does not set `m8flow_selected_tenant`.
 */
export default function TenantManagementPage() {
  const { tenantId: routeTenantId } = useParams<{ tenantId: string }>();
  const location = useLocation();
  const { isSuperAdmin, activeTenantId } = useActiveTenant();
  const { canManageTenant } = useCapabilities();
  const { refreshTenants, tenants } = useTenantRegistry();

  if (isSuperAdmin && !routeTenantId) {
    return <Navigate to="/tenants" replace />;
  }

  const tenantId = isSuperAdmin ? routeTenantId : activeTenantId;
  const locationState = location.state as TenantManagementLocationState | null;
  const tenantName = isSuperAdmin
    ? locationState?.tenantName
      || tenants.find((row) => row.id === tenantId)?.name
      || tenantId
    : getActiveTenantDisplayLabel() ?? tenantId;
  const needsTenant = canManageTenant && !tenantId;

  if (!canManageTenant) {
    return (
      <main className="flex-1 px-11 py-10">
        <div className="mb-7">
          <h1 className="font-display text-[32px] font-semibold tracking-tight">
            Tenant Management
          </h1>
        </div>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">Not available</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Tenant Management is for tenant admins and platform admins. Your role
            cannot list or manage members.
          </p>
        </Card>
      </main>
    );
  }

  if (needsTenant || !tenantId) {
    return (
      <main className="flex-1 px-11 py-10">
        <div className="mb-7">
          <h1 className="font-display text-[32px] font-semibold tracking-tight">
            Tenant Management
          </h1>
        </div>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">Choose a tenant</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Members are tenant-scoped. Sign in with an active tenant to manage members,
            groups, and roles.
          </p>
        </Card>
      </main>
    );
  }

  return (
    <TenantAdminPanel
      tenantId={tenantId}
      tenantName={tenantName ?? tenantId}
      tenantSlug={isSuperAdmin ? locationState?.tenantSlug : undefined}
      tenantStatus={isSuperAdmin ? locationState?.tenantStatus : undefined}
      isSuperAdmin={isSuperAdmin}
      refreshTenants={refreshTenants}
    />
  );
}
