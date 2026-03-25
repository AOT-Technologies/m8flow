import { isDefined } from 'min-dash';

import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

import {
  getBusinessObject,
  is
} from 'bpmn-js/lib/util/ModelUtil';


/**
 * Camunda BPMN specific behavior ensuring camunda:initiator property is removed
 * when start event is created in or moved to sub process.
 */
export default class RemoveInitiatorBehaviour extends CommandInterceptor {
  constructor(eventBus, modeling) {
    super(eventBus);

    this.postExecuted([ 'shape.create','shape.move' ], (context) => {
      const {
        shape,
        parent,
        newParent = parent
      } = context;

      const businessObject = getBusinessObject(shape);

      if (is(shape, 'bpmn:StartEvent') && isDefined(businessObject.get('camunda:initiator'))) {
        if ((is(newParent || parent, 'bpmn:SubProcess'))) {
          modeling.updateProperties(shape, { 'camunda:initiator': undefined });
        }
      }
    }, true);
  }
}

RemoveInitiatorBehaviour.$inject = [
  'eventBus',
  'modeling'
];