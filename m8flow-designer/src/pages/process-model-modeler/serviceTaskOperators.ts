import type { ConnectorGroup } from '@/lib/api';
import type { BpmnCanvasServiceTaskOperator } from './components/BpmnCanvas';

/** Flatten `GET /connectors-grouped` into the `{id, parameters}[]` list
 * ServiceTaskOperatorSelect (and the Action tab catalog) expects. Missing
 * `parameters` becomes `[]` so HTTP V2 operators still round-trip even if a
 * group omits the field. */
export function flattenConnectorGroupsToOperators(
  groups: ConnectorGroup[],
): BpmnCanvasServiceTaskOperator[] {
  return groups.flatMap((group) =>
    group.operations.map((operation) => ({
      id: operation.id,
      parameters: operation.parameters ?? [],
    })),
  );
}
