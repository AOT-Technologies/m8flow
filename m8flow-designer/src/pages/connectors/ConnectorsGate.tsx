import type { ReactNode } from 'react';

import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { Card } from '@/components/ui/card';

export function useConnectorsContext() {
  const { scopedTenantId, isSuperAdmin, needsTenant } = useActiveTenant();
  const { canReadConnectors, canManageConnectorProfiles } = useCapabilities();
  return {
    scopedTenantId,
    isSuperAdmin,
    canReadConnectors,
    canManageConnectorProfiles,
    needsTenant,
  };
}

export function ConnectorsUnavailable({ title }: { title: string }) {
  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
      </div>
      <Card variant="bordered" className="max-w-lg p-6">
        <p className="text-[15px] font-semibold text-foreground">Not available</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Connectors are for tenant admins, editors, and integrators. Your role cannot
          open this catalog.
        </p>
      </Card>
    </main>
  );
}

export function ConnectorsNeedsTenant({ title }: { title: string }) {
  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
      </div>
      <Card variant="bordered" className="max-w-lg p-6">
        <p className="text-[15px] font-semibold text-foreground">Choose a tenant</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Connector profiles are tenant-scoped. Select a concrete tenant in the sidebar —
          All Tenants is not supported here.
        </p>
      </Card>
    </main>
  );
}

export function ConnectorsGate({
  title,
  children,
  requireTenant = false,
}: {
  title: string;
  children: ReactNode;
  requireTenant?: boolean;
}) {
  const { canReadConnectors, needsTenant } = useConnectorsContext();
  if (!canReadConnectors) {
    return <ConnectorsUnavailable title={title} />;
  }
  if (requireTenant && needsTenant) {
    return <ConnectorsNeedsTenant title={title} />;
  }
  return children;
}
