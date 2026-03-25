import {
  getBusinessObject,
  is
} from 'bpmn-js/lib/util/ModelUtil';

import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

import { without } from 'min-dash';

import { getExtensionElementsList } from '../util/ExtensionElementsUtil';

const HIGH_PRIORITY = 5000;

/**
 * Zeebe BPMN behavior ensuring that bpmn:AdHocSubProcess is cleaned up
 * when zeebe:TaskDefinition is added or removed.
 */
export default class CleanUpAdHocSubProcessBehavior extends CommandInterceptor {
  constructor(eventBus, modeling) {
    super(eventBus);

    /**
     * Remove zeebe:AdHoc properties (zeebe:activeElementsCollection, zeebe:completionCondition)
     * and remove bpmn:cancelRemainingInstances when zeebe:TaskDefinition is added.
     */
    this.postExecute('element.updateModdleProperties', HIGH_PRIORITY, function(context) {
      const {
        element,
        moddleElement
      } = context;

      const businessObject = getBusinessObject(element);

      if (
        !is(businessObject, 'bpmn:AdHocSubProcess')
        || !is(moddleElement, 'bpmn:ExtensionElements')
        || !getTaskDefinition(element)
      ) {
        return;
      }

      modeling.updateModdleProperties(element, businessObject, {
        cancelRemainingInstances: undefined,
        completionCondition: undefined
      });

      const adHoc = getAdHoc(element);

      if (adHoc) {
        modeling.updateModdleProperties(element, adHoc, {
          activeElementsCollection: undefined,
        });
      }
    }, true);

    /**
     * Remove zeebe:TaskHeaders when zeebe:TaskDefinition is removed.
     */
    this.postExecute('element.updateModdleProperties', HIGH_PRIORITY, function(context) {
      const {
        element,
        moddleElement
      } = context;

      if (
        !is(element, 'bpmn:AdHocSubProcess')
        || !is(moddleElement, 'bpmn:ExtensionElements')
        || getTaskDefinition(element)
      ) {
        return;
      }

      const taskHeaders = getTaskHeaders(element);

      if (taskHeaders) {
        modeling.updateModdleProperties(element, moddleElement, {
          values: without(moddleElement.get('values'), taskHeaders)
        });
      }
    }, true);
  }
}

CleanUpAdHocSubProcessBehavior.$inject = [
  'eventBus',
  'modeling'
];


// helpers //////////

function getAdHoc(element) {
  const businessObject = getBusinessObject(element);

  return getExtensionElementsList(businessObject, 'zeebe:AdHoc')[ 0 ];
}

function getTaskHeaders(element) {
  const businessObject = getBusinessObject(element);

  return getExtensionElementsList(businessObject, 'zeebe:TaskHeaders')[ 0 ];
}

function getTaskDefinition(element) {
  const businessObject = getBusinessObject(element);

  return getExtensionElementsList(businessObject, 'zeebe:TaskDefinition')[ 0 ];
}