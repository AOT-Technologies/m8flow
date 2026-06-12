import React, { createContext, useContext, useState } from 'react';

const GLOBAL_TENANT_STORAGE_KEY = 'm8flow_global_selected_tenant';

// localStorage can be unavailable (no window) or throw (private mode, quota,
// disabled storage) in some runtimes/tests. Guard all access defensively.
function safeGet(key: string): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage.getItem(key) || '';
  } catch {
    return '';
  }
}

function safeSet(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

function safeRemove(key: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

interface GlobalTenantContextType {
  selectedTenantId: string;
  setSelectedTenantId: (id: string) => void;
}

const GlobalTenantContext = createContext<GlobalTenantContextType>({
  selectedTenantId: '',
  setSelectedTenantId: () => {},
});

export function GlobalTenantProvider({ children }: { children: React.ReactNode }) {
  const [selectedTenantId, setSelectedTenantIdState] = useState<string>(() =>
    safeGet(GLOBAL_TENANT_STORAGE_KEY),
  );

  const setSelectedTenantId = (id: string) => {
    if (id) {
      safeSet(GLOBAL_TENANT_STORAGE_KEY, id);
    } else {
      safeRemove(GLOBAL_TENANT_STORAGE_KEY);
    }
    setSelectedTenantIdState(id);
  };

  return (
    <GlobalTenantContext.Provider value={{ selectedTenantId, setSelectedTenantId }}>
      {children}
    </GlobalTenantContext.Provider>
  );
}

export function useGlobalTenant(): GlobalTenantContextType {
  return useContext(GlobalTenantContext);
}

export { GLOBAL_TENANT_STORAGE_KEY };
