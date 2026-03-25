import { is } from 'bpmn-js/lib/util/ModelUtil';
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';
import { without } from 'min-dash';

import { getExtensionElementsList } from '../util/ExtensionElementsUtil';


export default class CleanUpTaskListenersBehavior extends CommandInterceptor {
  constructor(eventBus, modeling) {
    super(eventBus);

    // remove task listeners of disallowed type on shape replace
    this.postExecuted('shape.replace', function(event) {
      const element = event.context.newShape;

      updateListeners(element, modeling);
    });

    // remove task listeners of disallowed type on user task properties update
    this.postExecuted('element.updateModdleProperties', function(event) {
      const element = event.context.element;

      if (!is(element, 'bpmn:UserTask')) {
        return;
      }

      updateListeners(element, modeling);
    });

    // remove empty task listener container
    this.postExecuted('element.updateModdleProperties', function(event) {
      const {
        element,
        moddleElement
      } = event.context;

      if (!is(moddleElement, 'zeebe:TaskListeners')) {
        return;
      }

      const listeners = moddleElement.get('listeners');
      if (listeners.length) {
        return;
      }

      const extensionElements = moddleElement.$parent;
      modeling.updateModdleProperties(element, extensionElements, { values: without(extensionElements.get('values'), moddleElement) });
    });
  }
}

CleanUpTaskListenersBehavior.$inject = [
  'eventBus',
  'modeling'
];

// helpers //////////
function updateListeners(element, modeling) {
  const taskListenersContainer = getTaskListenersContainer(element);
  if (!taskListenersContainer) {
    return;
  }

  const listeners = taskListenersContainer.get('listeners');
  const newListeners = withoutDisallowedListeners(element, listeners);

  if (newListeners.length !== listeners.length) {
    modeling.updateModdleProperties(element, taskListenersContainer, { listeners: newListeners });
  }
}

function withoutDisallowedListeners(element, listeners) {
  return listeners.filter(listener => {
    if (
      !is(element, 'bpmn:UserTask') ||
      !hasZeebeTaskExtensionElement(element)
    ) {
      return false;
    }
    return true;
  });
}

function getTaskListenersContainer(element) {
  return getExtensionElementsList(element, 'zeebe:TaskListeners')[0];
}

function hasZeebeTaskExtensionElement(element) {
  return getExtensionElementsList(element, 'zeebe:UserTask').length > 0;
}
