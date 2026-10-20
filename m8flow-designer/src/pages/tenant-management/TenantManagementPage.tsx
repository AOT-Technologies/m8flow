import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
  const { tenantId: routeTenantId } = useParams<{ tenantId: string }>();
  const location = useLocation();
  const { isSuperAdmin, activeTenantId } = useActiveTenant();
  const {
    canAccessTenantManagement,
    canUpdateTenants,
    canAddTenantMembers,
    canRemoveTenantMembers,
    canCreateTenantGroups,
    canUpdateTenantGroups,
    canDeleteTenantGroups,
    canUpdateTenantGroupMemberships,
    canUpdateTenantGroupRoles,
  } = useCapabilities();
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
  const needsTenant = canAccessTenantManagement && !tenantId;

  if (!canAccessTenantManagement) {
    return (
      <main className="flex-1 px-11 py-10">
        <div className="mb-7">
          <h1 className="font-display text-[32px] font-semibold tracking-tight">
            {t('tenantManagement.page.title')}
          </h1>
        </div>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">
            {t('tenantManagement.page.notAvailableTitle')}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {t('tenantManagement.page.notAvailableBody')}
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
            {t('tenantManagement.page.title')}
          </h1>
        </div>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">
            {t('tenantManagement.page.chooseTenantTitle')}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {t('tenantManagement.page.chooseTenantBody')}
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
      canUpdateTenant={canUpdateTenants}
      canAddMembers={canAddTenantMembers}
      canRemoveMembers={canRemoveTenantMembers}
      canUpdateMemberships={canUpdateTenantGroupMemberships}
      canCreateGroups={canCreateTenantGroups}
      canUpdateGroups={canUpdateTenantGroups}
      canDeleteGroups={canDeleteTenantGroups}
      canUpdateGroupRoles={canUpdateTenantGroupRoles}
    />
  );
}
