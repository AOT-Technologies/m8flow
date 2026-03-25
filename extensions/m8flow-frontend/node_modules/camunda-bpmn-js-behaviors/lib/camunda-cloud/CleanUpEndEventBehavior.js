import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil';
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';
import { find, without } from 'min-dash';

export default class CleanUpEndEventBehavior extends CommandInterceptor {
  constructor(eventBus, modeling) {
    super(eventBus);

    this.postExecuted('shape.replace', function(event) {

      const {
        context
      } = event;

      const {
        newShape
      } = context;

      if (!is(newShape, 'bpmn:EndEvent') || !getErrorEventDefinition(newShape)) {
        return;
      }

      const ioMapping = getIoMapping(newShape);

      if (!ioMapping) {
        return;
      }

      const businessObject = getBusinessObject(newShape),
            extensionElements = businessObject.get('extensionElements'),
            values = without(extensionElements.get('values'), ioMapping);

      modeling.updateModdleProperties(newShape, extensionElements, { values });
    });
  }
}

CleanUpEndEventBehavior.$inject = [
  'eventBus',
  'modeling'
];

// helpers //////////

export function getErrorEventDefinition(element) {
  const businessObject = getBusinessObject(element);

  const eventDefinitions = businessObject.get('eventDefinitions') || [];

  return find(eventDefinitions, function(definition) {
    return is(definition, 'bpmn:ErrorEventDefinition');
  });
}

export function getIoMapping(element) {
  const bo = getBusinessObject(element);

  const extensionElements = bo.get('extensionElements');

  if (!extensionElements) {
    return null;
  }

  const values = extensionElements.get('values');

  if (!values) {
    return null;
  }

  return find(values, value => is(value, 'zeebe:IoMapping'));
}
