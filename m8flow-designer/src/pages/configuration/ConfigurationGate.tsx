import type { ReactNode } from 'react';

import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { Card } from '@/components/ui/card';

export function useConfigurationContext() {
  const { scopedTenantId, isSuperAdmin, needsTenant, needsTenantForWrite } = useActiveTenant();
  const { canReadSecrets, canManageSecrets } = useCapabilities();
  return {
    scopedTenantId,
    isSuperAdmin,
    canReadSecrets,
    canManageSecrets,
    needsTenant,
    needsTenantForWrite,
    /** All-Tenants super-admin read: show the owning tenant per row. */
    allTenants: isSuperAdmin && !scopedTenantId,
  };
}

export function ConfigurationUnavailable({ title }: { title: string }) {
  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
      </div>
      <Card variant="bordered" className="max-w-lg p-6">
        <p className="text-[15px] font-semibold text-foreground">Not available</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Secrets are for integrators, viewers, and tenant admins. Your role cannot
          list or manage them.
        </p>
      </Card>
    </main>
  );
}

export function ConfigurationNeedsTenant({ title }: { title: string }) {
  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
      </div>
      <Card variant="bordered" className="max-w-lg p-6">
        <p className="text-[15px] font-semibold text-foreground">Choose a tenant</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Secrets are tenant-scoped. Select a concrete tenant in the sidebar —
          All Tenants is not supported here.
        </p>
      </Card>
    </main>
  );
}

export function ConfigurationGate({
  title,
  children,
  requireTenant = false,
}: {
  title: string;
  children: ReactNode;
  /** Only write/detail surfaces need a concrete tenant. The secrets LIST
   * renders under All Tenants (records carry no secret value), same posture
   * as ConnectorsGate. */
  requireTenant?: boolean;
}) {
  const { canReadSecrets, needsTenant } = useConfigurationContext();
  if (!canReadSecrets) {
    return <ConfigurationUnavailable title={title} />;
  }
  if (requireTenant && needsTenant) {
    return <ConfigurationNeedsTenant title={title} />;
  }
  return children;
}
