import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

import { is } from 'bpmn-js/lib/util/ModelUtil';

import {
  getOutputParameters,
  getIoMapping
} from './util/InputOutputUtil';

const HIGH_PRIORITY = 5000;

/**
 * Zeebe BPMN behavior for updating <bpmn:CallActivity> elements
 * ensuring that:
 *
 * - `<zeebe:Output>` elements are removed if `zeebe:propagateAllChildVariables` is set to true
 */
export default class CallActivityVariablesPropagationBehavior extends CommandInterceptor {
  constructor(eventBus, modeling) {
    super(eventBus);

    // Remove <zeebe:Output> elements if zeebe:propagateAllChildVariables is set to true.
    this.postExecute('element.updateModdleProperties' , HIGH_PRIORITY, function(context) {
      const {
        element,
        moddleElement,
        properties = {}
      } = context;

      const propagateAllChildVariables =
        properties.propagateAllChildVariables ||
        properties[ 'zeebe:propagateAllChildVariables' ];

      if (
        !is(element, 'bpmn:CallActivity')
        || !is(moddleElement, 'zeebe:CalledElement')
        || !propagateAllChildVariables
      ) {
        return;
      }

      const outputParameters = getOutputParameters(element);

      if (!outputParameters || !outputParameters.length) {
        return;
      }

      const ioMapping = getIoMapping(element);

      modeling.updateModdleProperties(element, ioMapping, {
        'zeebe:outputParameters': []
      });
    }, true);
  }
}

CallActivityVariablesPropagationBehavior.$inject = [
  'eventBus',
  'modeling'
];