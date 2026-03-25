/**
 * @typedef {import('@bpmn-io/feel-editor').Variable} Variable
*/

/**
 * @typedef VariableProvider
 * @property {(variables: Variable[], element) => Variable[]} getVariables
 */

export class VariableResolver {
  constructor() {
    this._providers = [];
  }

  /**
   * @param {VariableProvider} provider
   */
  registerProvider(provider) {
    this._providers.push(provider);
  }

  getVariables(element) {
    return this._providers.reduce(
      (variables, provider) => provider.getVariables(variables, element), []
    );
  }
}
