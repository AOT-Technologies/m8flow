/**
 * Catalog of service-task operators returned on `spiff.service_tasks.returned`.
 *
 * bpmn-js-spiffworkflow's ServiceTaskOperatorSelect keeps a module-level
 * cache that *ignores* an empty array (`if (event.serviceTaskOperators.length
 * > 0)`), then re-fires `spiff.service_tasks.requested` on every render while
 * that cache is still empty. An empty host catalog (connector-proxy down,
 * or `M8FLOW_BACKEND_CONNECTOR_PROXY_URL` unset) therefore looks like a
 * blank <select> and hammers `GET /connectors-grouped`. This store caches
 * the returned list *including empty* so the Action tab can skip mounting
 * that select when there is nothing to pick.
 *
 * Same pub-sub shape as `elementScopedTabState.ts`: a plain factory (tested
 * without Preact) plus a thin `useServiceTaskOperatorCatalog` adapter.
 */
import { useEffect, useState } from 'preact/hooks';

export type ServiceTaskOperatorParameter = { id: string; type: string };

export type ServiceTaskOperator = {
  id: string;
  parameters: ServiceTaskOperatorParameter[];
};

export type ServiceTaskOperatorCatalogState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; operators: ServiceTaskOperator[] };

export type ServiceTaskOperatorCatalog = {
  getState(): ServiceTaskOperatorCatalogState;
  /** Idle → loading. Returns true only on that transition so the caller
   * fires `spiff.service_tasks.requested` once. */
  markLoading(): boolean;
  setLoaded(operators: unknown): void;
  subscribe(listener: () => void): () => void;
  reset(): void;
};

function normalizeOperators(operators: unknown): ServiceTaskOperator[] {
  if (!Array.isArray(operators)) {
    return [];
  }
  return operators.map((operator) => {
    const record = operator as { id?: unknown; parameters?: unknown };
    return {
      id: String(record?.id ?? ''),
      parameters: Array.isArray(record?.parameters)
        ? record.parameters.map((parameter) => {
            const param = parameter as { id?: unknown; type?: unknown };
            return { id: String(param?.id ?? ''), type: String(param?.type ?? 'string') };
          })
        : [],
    };
  });
}

export function createServiceTaskOperatorCatalog(): ServiceTaskOperatorCatalog {
  let state: ServiceTaskOperatorCatalogState = { status: 'idle' };
  const listeners = new Set<() => void>();

  const notify = () => {
    listeners.forEach((listener) => listener());
  };

  return {
    getState() {
      return state;
    },
    markLoading() {
      if (state.status !== 'idle') {
        return false;
      }
      state = { status: 'loading' };
      notify();
      return true;
    },
    setLoaded(operators) {
      state = { status: 'loaded', operators: normalizeOperators(operators) };
      notify();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    reset() {
      state = { status: 'idle' };
      notify();
    },
  };
}

export const serviceTaskOperatorCatalog = createServiceTaskOperatorCatalog();

export function catalogHasOperators(state: ServiceTaskOperatorCatalogState): boolean {
  return state.status === 'loaded' && state.operators.length > 0;
}

export function useServiceTaskOperatorCatalog(
  catalog: ServiceTaskOperatorCatalog = serviceTaskOperatorCatalog,
): ServiceTaskOperatorCatalogState {
  const [, forceUpdate] = useState(0);
  useEffect(() => catalog.subscribe(() => forceUpdate((n) => n + 1)), [catalog]);
  return catalog.getState();
}
