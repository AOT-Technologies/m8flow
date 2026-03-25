import { resolveVariables } from './core';

export class DmnVariableProvider {

  /**
   * @param {import('./VariableResolver').VariableResolver} variableResolver
   */
  constructor(variableResolver) {
    variableResolver.registerProvider(this);
  }

  getVariables(variables, element) {
    return variables.concat(resolveVariables(element));
  }
}

DmnVariableProvider.$inject = [ 'variableResolver' ];
