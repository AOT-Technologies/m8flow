import React, { createContext, useContext, useState } from 'react';

const GLOBAL_TENANT_STORAGE_KEY = 'm8flow_global_selected_tenant';

interface GlobalTenantContextType {
  selectedTenantId: string;
  setSelectedTenantId: (id: string) => void;
}

const GlobalTenantContext = createContext<GlobalTenantContextType>({
  selectedTenantId: '',
  setSelectedTenantId: () => {},
});

export function GlobalTenantProvider({ children }: { children: React.ReactNode }) {
  const [selectedTenantId, setSelectedTenantIdState] = useState<string>(
    () => localStorage.getItem(GLOBAL_TENANT_STORAGE_KEY) || '',
  );

  const setSelectedTenantId = (id: string) => {
    if (id) {
      localStorage.setItem(GLOBAL_TENANT_STORAGE_KEY, id);
    } else {
      localStorage.removeItem(GLOBAL_TENANT_STORAGE_KEY);
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
