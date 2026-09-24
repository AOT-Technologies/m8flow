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
  /** Optional labels from `GET /connectors-grouped` (group id/name, operation name). */
  connectorId?: string;
  connectorName?: string;
  name?: string;
};

export type ServiceTaskConnectorOption = {
  id: string;
  name: string;
  operators: ServiceTaskOperator[];
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
    const record = operator as {
      id?: unknown;
      parameters?: unknown;
      connectorId?: unknown;
      connectorName?: unknown;
      name?: unknown;
    };
    const labels: Pick<ServiceTaskOperator, 'connectorId' | 'connectorName' | 'name'> = {};
    if (typeof record?.connectorId === 'string' && record.connectorId) labels.connectorId = record.connectorId;
    if (typeof record?.connectorName === 'string' && record.connectorName) labels.connectorName = record.connectorName;
    if (typeof record?.name === 'string' && record.name) labels.name = record.name;
    return {
      ...labels,
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

function connectorIdOf(operator: ServiceTaskOperator): string {
  if (operator.connectorId) return operator.connectorId;
  const slash = operator.id.indexOf('/');
  return slash === -1 ? operator.id : operator.id.slice(0, slash);
}

/** Action label: catalog `name`, else the part of the id after `connector/`. */
export function operatorActionLabel(operator: ServiceTaskOperator): string {
  if (operator.name) return operator.name;
  const slash = operator.id.indexOf('/');
  return slash === -1 ? operator.id : operator.id.slice(slash + 1);
}

/** Group a flat operator list by connector, preserving catalog order. */
export function groupOperatorsByConnector(operators: ServiceTaskOperator[]): ServiceTaskConnectorOption[] {
  const byId = new Map<string, ServiceTaskConnectorOption>();
  for (const operator of operators) {
    const id = connectorIdOf(operator);
    let group = byId.get(id);
    if (!group) {
      group = { id, name: operator.connectorName || id, operators: [] };
      byId.set(id, group);
    }
    group.operators.push(operator);
  }
  return [...byId.values()];
}

const SERVICE_TASK_OPERATOR_TYPE = 'spiffworkflow:ServiceTaskOperator';
const SERVICE_TASK_PARAMETERS_TYPE = 'spiffworkflow:Parameters';
const SERVICE_TASK_PARAMETER_TYPE = 'spiffworkflow:Parameter';

/** elementId → operatorId → previously used `spiffworkflow:Parameters`. */
export type OperatorParameterMemory = Record<string, Record<string, any>>;

/**
 * Port of bpmn-js-spiffworkflow's `ServiceTaskOperatorSelect.setValue`
 * (SpiffExtensionServiceProperties.js), minus the final command: swaps the
 * task's `spiffworkflow:ServiceTaskOperator` for `operator`, reusing the
 * parameter list last used for that operator on this element so switching
 * actions back and forth keeps typed values. Same moddle output as the
 * vendor select; the caller runs `element.updateModdleProperties`.
 */
export function writeServiceTaskOperator(
  businessObject: any,
  moddle: any,
  operator: ServiceTaskOperator,
  memory: OperatorParameterMemory,
): void {
  const elementMemory = (memory[businessObject.id] ??= {});
  const extensions = businessObject.extensionElements ?? moddle.create('bpmn:ExtensionElements');
  const oldOperator = (extensions.get('values') as any[]).find((ee) => ee.$type === SERVICE_TASK_OPERATOR_TYPE);

  const newOperator = moddle.create(SERVICE_TASK_OPERATOR_TYPE);
  newOperator.id = operator.id;
  let parameterList = elementMemory[operator.id];
  if (!parameterList) {
    parameterList = moddle.create(SERVICE_TASK_PARAMETERS_TYPE);
    parameterList.parameters = operator.parameters.map((stoParameter) => {
      const parameter = moddle.create(SERVICE_TASK_PARAMETER_TYPE);
      parameter.id = stoParameter.id;
      parameter.type = stoParameter.type;
      return parameter;
    });
    elementMemory[operator.id] = parameterList;
    if (oldOperator) {
      elementMemory[oldOperator.id] = oldOperator.parameterList;
    }
  }
  newOperator.parameterList = parameterList;

  const values = (extensions.get('values') as any[]).filter((ee) => ee.$type !== SERVICE_TASK_OPERATOR_TYPE);
  values.push(newOperator);
  extensions.values = values;
  businessObject.extensionElements = extensions;
}
