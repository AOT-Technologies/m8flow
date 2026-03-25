import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

import {
  getBusinessObject,
  is
} from 'bpmn-js/lib/util/ModelUtil';


/**
 * Camunda BPMN specific behavior ensuring camunda:variableEvents property is
 * removed when start event is moved out of event sub process.
 */
export default class RemoveVariableEventBehaviour extends CommandInterceptor {
  constructor(bpmnFactory, eventBus, moddleCopy, modeling) {
    super(eventBus);

    this.postExecuted([ 'shape.create', 'shape.move' ], (context) => {
      const {
        parent,
        newParent = parent,
        shape
      } = context;

      const newParentBusinessObject = getBusinessObject(newParent),
            shapeBusinessObject = getBusinessObject(shape);

      if (is(shape, 'bpmn:StartEvent')) {

        if (!(is(newParent, 'bpmn:SubProcess') && newParentBusinessObject.get('triggeredByEvent'))) {
          const eventDefinitions = shapeBusinessObject.get('eventDefinitions').slice();

          const update = eventDefinitions.reduce((update, eventDefinition, index) => {
            if (!is(eventDefinition, 'bpmn:ConditionalEventDefinition')) {
              return;
            }

            if (eventDefinition.get('camunda:variableEvents')) {
              const conditionalEventDefinition = bpmnFactory.create('bpmn:ConditionalEventDefinition');

              moddleCopy.copyElement(eventDefinition, conditionalEventDefinition);

              conditionalEventDefinition.$parent = eventDefinition.$parent;

              // remove camunda:variableEvents property
              conditionalEventDefinition.variableEvents = undefined;

              eventDefinitions[ index ] = conditionalEventDefinition;

              return true;
            }

            return update;
          }, false);

          if (update) {
            modeling.updateProperties(shape, {
              eventDefinitions: eventDefinitions
            });
          }
        }
      }
    }, true);
  }
}

RemoveVariableEventBehaviour.$inject = [
  'bpmnFactory',
  'eventBus',
  'moddleCopy',
  'modeling'
];