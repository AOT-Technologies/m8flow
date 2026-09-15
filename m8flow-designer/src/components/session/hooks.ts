import { useContext } from 'react';

import {
  SessionContext,
  type ActiveTenant,
  type CapabilityFlags,
  type TenantRegistry,
} from './SessionContext';

function useSessionContext() {
  const context = useContext(SessionContext);
  if (context === null) {
    throw new Error('useActiveTenant/useCapabilities/useTenantRegistry must be used within a <SessionProvider>');
  }
  return context;
}

/**
 * The single active-tenant seam. Every page that used to re-derive
 * `needsTenant = isSuperAdmin && !scopedTenantId` reads it from here instead.
 */
export function useActiveTenant(): ActiveTenant {
  return useSessionContext().activeTenant;
}

/** The six backend capability flags, fetched once by the provider. */
export function useCapabilities(): CapabilityFlags {
  return useSessionContext().capabilities;
}

/** Super-admin tenant registry + non-admin organization display. */
export function useTenantRegistry(): TenantRegistry {
  return useSessionContext().registry;
}
