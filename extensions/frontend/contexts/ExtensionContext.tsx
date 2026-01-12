import React, { createContext, useContext, ReactNode } from 'react';
import { getVariantConfig, VariantConfig } from '../config/variants';

interface ExtensionContextType {
  variant: VariantConfig;
  isFeatureEnabled: (feature: keyof VariantConfig['features']) => boolean;
}

const ExtensionContext = createContext<ExtensionContextType | undefined>(undefined);

export function ExtensionProvider({ children }: { children: ReactNode }) {
  const variant = getVariantConfig();
  
  const isFeatureEnabled = (feature: keyof VariantConfig['features']) => {
    return variant.features[feature];
  };
  
  return (
    <ExtensionContext.Provider value={{ variant, isFeatureEnabled }}>
      {children}
    </ExtensionContext.Provider>
  );
}

export function useExtension() {
  const context = useContext(ExtensionContext);
  if (!context) {
    throw new Error('useExtension must be used within ExtensionProvider');
  }
  return context;
}
