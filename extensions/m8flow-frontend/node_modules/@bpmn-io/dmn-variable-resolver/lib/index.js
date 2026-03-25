import { DmnVariableProvider } from './DmnVariableProvider';
import { VariableResolver } from './VariableResolver';

export { resolveVariables } from './core';

export const DmnVariableResolverModule = {
  __init__: [ 'dmnVariableProvider' ],
  dmnVariableProvider: [ 'type', DmnVariableProvider ],
  variableResolver: [ 'type', VariableResolver ]
};
