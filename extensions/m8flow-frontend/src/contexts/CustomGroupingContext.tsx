/**
 * m8 Extension: Custom Grouping Context
 * 
 * Provides a way to extend grouping functionality without duplicating
 * entire components. Components can register custom grouping options
 * and handlers through this context.
 */

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';

export type CustomGroupingHandler = (tasks: any[]) => Record<string, any[]>;

interface CustomGroupingOption {
  label: string;
  handler: CustomGroupingHandler;
  headerText?: string;
}

interface CustomGroupingContextType {
  customOptions: CustomGroupingOption[];
  registerOption: (option: CustomGroupingOption) => void;
  getHandler: (label: string) => CustomGroupingHandler | undefined;
  getHeaderText: (label: string) => string | undefined;
  isCustomOption: (label: string) => boolean;
}

const CustomGroupingContext = createContext<CustomGroupingContextType | null>(null);

export function CustomGroupingProvider({ children }: { children: ReactNode }) {
  const [customOptions, setCustomOptions] = useState<CustomGroupingOption[]>([
    // Default custom option: Group by Process Model Name
    {
      label: 'Custom Grouping',
      handler: (tasks: any[]) => {
        return tasks.reduce((acc: Record<string, any[]>, task: any) => {
          const processModelName = task.process_model_identifier?.split('/').pop() || 'Unknown';
          if (!acc[processModelName]) {
            acc[processModelName] = [];
          }
          acc[processModelName].push(task);
          return acc;
        }, {});
      },
      headerText: 'Tasks from process model: ',
    },
  ]);

  const registerOption = useCallback((option: CustomGroupingOption) => {
    setCustomOptions(prev => {
      // Don't add duplicates
      if (prev.some(o => o.label === option.label)) {
        return prev;
      }
      return [...prev, option];
    });
  }, []);

  const getHandler = useCallback((label: string) => {
    return customOptions.find(o => o.label === label)?.handler;
  }, [customOptions]);

  const getHeaderText = useCallback((label: string) => {
    return customOptions.find(o => o.label === label)?.headerText;
  }, [customOptions]);

  const isCustomOption = useCallback((label: string) => {
    return customOptions.some(o => o.label === label);
  }, [customOptions]);

  return (
    <CustomGroupingContext.Provider value={{
      customOptions,
      registerOption,
      getHandler,
      getHeaderText,
      isCustomOption,
    }}>
      {children}
    </CustomGroupingContext.Provider>
  );
}

export function useCustomGrouping() {
  const context = useContext(CustomGroupingContext);
  if (!context) {
    // Return a no-op version if not wrapped in provider
    return {
      customOptions: [],
      registerOption: () => {},
      getHandler: () => undefined,
      getHeaderText: () => undefined,
      isCustomOption: () => false,
    };
  }
  return context;
}

export default CustomGroupingContext;
