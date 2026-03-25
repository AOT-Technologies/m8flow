import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil';
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';


export default class CleanUpMessageRefBehavior extends CommandInterceptor {
  constructor(eventBus, modeling) {
    super(eventBus, modeling);

    this.postExecuted('shape.replace', function(event) {
      const newShape = event.context.newShape;

      if (!is(newShape, 'bpmn:ThrowEvent')) {
        return;
      }

      const messageEventDefinition = getMessageEventDefinition(newShape);

      if (!messageEventDefinition) {
        return;
      }

      const messageRef = messageEventDefinition.get('messageRef');
      if (!messageRef) {
        return;
      }

      modeling.updateModdleProperties(newShape, messageEventDefinition, {
        messageRef: undefined
      });
    });

    this.postExecuted('shape.replace', function(event) {
      const newShape = event.context.newShape,
            bo = getBusinessObject(newShape);

      if (!is(bo, 'bpmn:SendTask')) {
        return;
      }

      const messageRef = bo.get('messageRef');
      if (!messageRef) {
        return;
      }

      modeling.updateProperties(newShape, {
        messageRef: undefined
      });
    });
  }
}

CleanUpMessageRefBehavior.$inject = [ 'eventBus', 'modeling' ];


// helpers //////////

function getMessageEventDefinition(element) {
  const businessObject = getBusinessObject(element);

  const eventDefinitions = businessObject.get('eventDefinitions') || [];

  return eventDefinitions.find(definition => {
    return is(definition, 'bpmn:MessageEventDefinition');
  });
}
