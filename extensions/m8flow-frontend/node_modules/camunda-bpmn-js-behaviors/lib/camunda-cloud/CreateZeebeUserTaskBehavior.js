import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil';
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

import { createElement } from '../util/ElementUtil';
import { getExtensionElementsList } from '../util/ExtensionElementsUtil';

const HIGH_PRIORITY = 5000;

/**
 * Zeebe BPMN specific behavior for creating user tasks.
 */
export default class CreateZeebeUserTaskBehavior extends CommandInterceptor {
  constructor(bpmnFactory, eventBus, modeling) {
    super(eventBus);

    /**
     * Add zeebe:userTask extension element when creating bpmn:UserTask.
     */
    this.postExecuted(
      [ 'shape.create', 'shape.replace' ],
      HIGH_PRIORITY,
      function(context) {
        const shape = context.shape || context.newShape;
        const explicitlyDisabled = context.hints && context.hints.createElementsBehavior === false;

        if (!is(shape, 'bpmn:UserTask') || explicitlyDisabled) {
          return;
        }

        let userTaskElement = getZeebeUserTask(shape);
        if (userTaskElement) {
          return;
        }

        const businessObject = getBusinessObject(shape);
        let extensionElements = businessObject.get('extensionElements');

        if (!extensionElements) {
          extensionElements = createElement(
            'bpmn:ExtensionElements',
            {
              values: [],
            },
            businessObject,
            bpmnFactory
          );

          modeling.updateProperties(shape, { extensionElements });
        }

        userTaskElement = createElement(
          'zeebe:UserTask',
          {},
          extensionElements,
          bpmnFactory
        );

        modeling.updateModdleProperties(shape, extensionElements, {
          values: [ ...(extensionElements.values || []), userTaskElement ],
        });
      },
      true
    );
  }
}

CreateZeebeUserTaskBehavior.$inject = [ 'bpmnFactory', 'eventBus', 'modeling' ];

/**
 * Get zeebe:userTask extension.
 *
 * @param {djs.model.Base|ModdleElement} element
 *
 * @returns {ModdleElement|null}
 */
function getZeebeUserTask(element) {
  const businessObject = getBusinessObject(element);
  const userTaskElements = getExtensionElementsList(businessObject, 'zeebe:UserTask');

  return userTaskElements[0] || null;
}
