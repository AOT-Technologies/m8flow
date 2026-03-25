import { isDefined } from 'min-dash';

import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

import {
  getBusinessObject,
  is,
  isAny
} from 'bpmn-js/lib/util/ModelUtil';
import { removeExtensionElements } from '../util/ExtensionElementsUtil';

/**
 * Zeebe BPMN specific version tag behavior.
 */
export default class VersionTagBehavior extends CommandInterceptor {
  constructor(eventBus, commandStack) {
    super(eventBus);

    /**
     * Ensure that `zeebe:BindingTypeSupported` (`zeebe:CalledDecision`,
     * `zeebe:CalledElement` and `zeebe:FormDefinition`) only has
     * `zeebe:versionTag` if `zeebe:bindingType` is `versionTag`.
     */
    this.preExecute('element.updateModdleProperties', function(context) {
      const {
        moddleElement,
        properties
      } = context;

      if (!isAny(moddleElement, [
        'zeebe:CalledDecision',
        'zeebe:CalledElement',
        'zeebe:FormDefinition'
      ])) {
        return;
      }

      // unset `zeebe:versionTag` if `zeebe:bindingType` is not set to `versionTag`
      if ('bindingType' in properties
        && properties.bindingType !== 'versionTag'
        && isDefined(moddleElement.get('versionTag'))) {
        properties.versionTag = undefined;
      }

      // set `zeebe:bindingType` to `versionTag` if `zeebe:versionTag` is set
      if (isDefined(properties.versionTag) && moddleElement.get('bindingType') !== 'versionTag') {
        properties.bindingType = 'versionTag';
      }
    }, true);

    /**
     * Remove `zeebe:VersionTag` if its value is empty.
     */
    this.postExecuted('element.updateModdleProperties', function(context) {
      const {
        element,
        moddleElement
      } = context;

      if (!is(moddleElement, 'zeebe:VersionTag')) {
        return;
      }

      let businessObject = getBusinessObject(element);

      if (is(element, 'bpmn:Participant')) {
        businessObject = businessObject.get('processRef');
      }

      if (isEmpty(moddleElement.get('value'))) {
        removeExtensionElements(element, businessObject, moddleElement, commandStack);
      }
    }, true);
  }
}

VersionTagBehavior.$inject = [
  'eventBus',
  'commandStack'
];

// helpers //////////

function isEmpty(value) {
  return value == undefined || value === '';
}