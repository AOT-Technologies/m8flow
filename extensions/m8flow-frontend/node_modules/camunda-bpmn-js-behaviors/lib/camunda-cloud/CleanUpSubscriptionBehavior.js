import {
  getBusinessObject,
  is
} from 'bpmn-js/lib/util/ModelUtil';

import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

import { getExtensionElementsList, removeExtensionElements } from '../util/ExtensionElementsUtil';

/**
 * Zeebe BPMN behavior ensuring that zeebe:subscription is removed from bpmn:Message
 * when it has no properties anymore.
 */
export default class CleanUpSubscriptionBehavior extends CommandInterceptor {
  constructor(eventBus, commandStack) {
    super(eventBus);

    this.postExecuted([
      'element.updateProperties',
      'element.updateModdleProperties'
    ], context => {
      const element = context.shape || context.newShape || context.element;

      if (element.labelTarget) {
        return;
      }

      if (!is(element, 'bpmn:Event')) {
        return;
      }

      const messageEventDefinition = getMessageEventDefinition(element);

      if (!messageEventDefinition) {
        return;
      }

      const message = messageEventDefinition.get('messageRef');

      if (!message) {
        return;
      }

      const subscription = getSubscription(message);

      if (!subscription) {
        return;
      }

      if (!hasNoProperties(subscription)) {
        return;
      }

      removeExtensionElements(element, message, subscription, commandStack);
    }, true);
  }
}

CleanUpSubscriptionBehavior.$inject = [
  'eventBus',
  'commandStack'
];


// helpers //////////

function getMessageEventDefinition(event) {
  const businessObject = getBusinessObject(event);

  return businessObject.get('eventDefinitions').find(eventDefinition => {
    return is(eventDefinition, 'bpmn:MessageEventDefinition');
  });
}

function getSubscription(message) {
  return getExtensionElementsList(message, 'zeebe:Subscription')[ 0 ];
}

function hasNoProperties(element) {
  const descriptor = element.$descriptor;

  return descriptor.properties.every(property => {
    return element.get(property.name) === undefined;
  });
}
