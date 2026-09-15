import type { ReactNode } from 'react';

import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { Card } from '@/components/ui/card';

export function useConfigurationContext() {
  const { scopedTenantId, isSuperAdmin, needsTenant } = useActiveTenant();
  const { canReadSecrets, canManageSecrets } = useCapabilities();
  return {
    scopedTenantId,
    isSuperAdmin,
    canReadSecrets,
    canManageSecrets,
    needsTenant,
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
}: {
  title: string;
  children: ReactNode;
}) {
  const { canReadSecrets, needsTenant } = useConfigurationContext();
  if (!canReadSecrets) {
    return <ConfigurationUnavailable title={title} />;
  }
  if (needsTenant) {
    return <ConfigurationNeedsTenant title={title} />;
  }
  return children;
}
