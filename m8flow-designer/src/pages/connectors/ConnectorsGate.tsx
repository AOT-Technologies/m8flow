import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useActiveTenant, useCapabilities } from '@/components/session/hooks';
import { Card } from '@/components/ui/card';

export function useConnectorsContext() {
  const { scopedTenantId, isSuperAdmin, needsTenant, needsTenantForWrite } = useActiveTenant();
  const {
    canReadConnectors,
    canCreateConnectorProfiles,
    canUpdateConnectorProfiles,
    canDeleteConnectorProfiles,
    canCreateSecrets,
    canUpdateSecrets,
  } = useCapabilities();
  return {
    scopedTenantId,
    isSuperAdmin,
    canReadConnectors,
    // Profile writes must target one tenant; the list reads across tenants.
    canCreateConnectorProfiles: canCreateConnectorProfiles && !needsTenantForWrite,
    canUpdateConnectorProfiles: canUpdateConnectorProfiles && !needsTenantForWrite,
    canDeleteConnectorProfiles: canDeleteConnectorProfiles && !needsTenantForWrite,
    allTenants: isSuperAdmin && !scopedTenantId,
    // Configure on a connector card either opens profile configuration or tenant
    // secrets. Use the permission for those writes, not a role/capability flag.
    canConfigureProfiles:
      (canCreateConnectorProfiles || canUpdateConnectorProfiles) && !needsTenantForWrite,
    canConfigureSecrets: (canCreateSecrets || canUpdateSecrets) && !needsTenantForWrite,
    needsTenant,
    needsTenantForWrite,
  };
}

export function ConnectorsUnavailable({ title }: { title: string }) {
  const { t } = useTranslation();
  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
      </div>
      <Card variant="bordered" className="max-w-lg p-6">
        <p className="text-[15px] font-semibold text-foreground">{t('connectors.gate.unavailableTitle')}</p>
        <p className="mt-2 text-sm text-muted-foreground">
          {t('connectors.gate.unavailableBody')}
        </p>
      </Card>
    </main>
  );
}

export function ConnectorsNeedsTenant({ title }: { title: string }) {
  const { t } = useTranslation();
  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
      </div>
      <Card variant="bordered" className="max-w-lg p-6">
        <p className="text-[15px] font-semibold text-foreground">{t('connectors.gate.needsTenantTitle')}</p>
        <p className="mt-2 text-sm text-muted-foreground">
          {t('connectors.gate.needsTenantBody')}
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
