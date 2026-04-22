import { createContext, useContext } from 'react';

/** Called when user has selected a tenant (so parent can re-render and show full app). */
export type OnTenantSelected = () => void;

const TenantGateContext = createContext<{ onTenantSelected?: OnTenantSelected } | null>(null);

export function useTenantGate() {
  return useContext(TenantGateContext);
}

export default TenantGateContext;
