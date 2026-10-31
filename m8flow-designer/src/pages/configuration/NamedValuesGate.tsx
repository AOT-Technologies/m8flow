import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useActiveTenant, useCapabilities, useTenantRegistry } from '@/components/session/hooks';
import { Card } from '@/components/ui/card';

export function useNamedValuesContext() {
  const { activeTenantId, scopedTenantId, isSuperAdmin } = useActiveTenant();
  const { tenants } = useTenantRegistry();
  const capabilities = useCapabilities();
  // A super-admin's sidebar selection is an explicit server-validated query
  // override. Check it against the backend tenant directory so stale
  // localStorage ids cannot open a tenant-scoped page. Other users must have
  // the backend-finalized selected-tenant cookie.
  const tenantId = isSuperAdmin
    ? scopedTenantId && tenants.some((tenant) => tenant.id === scopedTenantId)
      ? scopedTenantId
      : null
    : activeTenantId;
  return { ...capabilities, tenantId, isSuperAdmin };
}

function GateMessage({ title, messageTitle, body }: { title: string; messageTitle: string; body: string }) {
  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <h1 className="font-display text-[32px] font-semibold tracking-tight">{title}</h1>
      </div>
      <Card variant="bordered" className="max-w-lg p-6">
        <p className="text-[15px] font-semibold text-foreground">{messageTitle}</p>
        <p className="mt-2 text-sm text-muted-foreground">{body}</p>
      </Card>
    </main>
  );
}

export function NamedValuesGate({
  title,
  access = 'list',
  children,
}: {
  title: string;
  access?: 'list' | 'create' | 'item';
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const { canReadNamedValues, canReadNamedValueItems, canCreateNamedValues, tenantId } =
    useNamedValuesContext();
  const allowed = access === 'create'
    ? canCreateNamedValues
    : access === 'item'
      ? canReadNamedValueItems
      : canReadNamedValues;
  if (!allowed) {
    return (
      <GateMessage
        title={title}
        messageTitle={t('configuration.namedValues.gate.unavailableTitle')}
        body={t('configuration.namedValues.gate.unavailableBody')}
      />
    );
  }
  if (!tenantId) {
    return (
      <GateMessage
        title={title}
        messageTitle={t('configuration.namedValues.gate.needsTenantTitle')}
        body={t('configuration.namedValues.gate.needsTenantBody')}
      />
    );
  }
  return children;
}
