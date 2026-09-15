/**
 * A per-element-id "which tab is active" store with a pub-sub, for a
 * tabbed properties-panel group whose tab strip and tab-content entries
 * are separate sibling Preact components — not children of one parent
 * component that could just hold this as local state (see the properties
 * panel's own Group/Entry render loop: there's no such parent). The Service
 * Task "Node-Wire Connectors" panel (`serviceTaskConnectorPanel.ts`) is the
 * first adapter; a second tabbed group (e.g. the Config tab's own
 * speculative per-connector profile picker) reuses this factory instead of
 * re-deriving the Map/Set trick from scratch.
 *
 * Split in two: `createElementScopedTabStore` is a plain Map + Set — no
 * Preact, no DOM — tested directly
 * (`test/elementScopedTabState.test.ts`). `useElementScopedTab` is the
 * thin `preact/hooks` adapter that subscribes a component to it; it has no
 * logic of its own worth testing separately from a real Preact render.
 */
import { useEffect, useState } from 'preact/hooks';

export type ElementScopedTabStore<T extends string> = {
  getActiveTab(elementId: string): T;
  setActiveTab(elementId: string, tab: T): void;
  subscribe(listener: () => void): () => void;
};

export function createElementScopedTabStore<T extends string>(defaultTab: T): ElementScopedTabStore<T> {
  const activeTabByElementId = new Map<string, T>();
  const listeners = new Set<() => void>();

  return {
    getActiveTab(elementId) {
      return activeTabByElementId.get(elementId) ?? defaultTab;
    },
    setActiveTab(elementId, tab) {
      activeTabByElementId.set(elementId, tab);
      listeners.forEach((listener) => listener());
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export function useElementScopedTab<T extends string>(store: ElementScopedTabStore<T>, elementId: string): T {
  const [, forceUpdate] = useState(0);
  useEffect(() => store.subscribe(() => forceUpdate((n) => n + 1)), [store]);
  return store.getActiveTab(elementId);
}
