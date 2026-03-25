import {
  find,
  matchPattern
} from 'min-dash';

import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

import {
  add as collectionAdd,
  remove as collectionRemove
} from 'diagram-js/lib/util/Collections';

import {
  getBusinessObject,
  is
} from 'bpmn-js/lib/util/ModelUtil';


const LOW_PRIORITY = 500;


/**
 * Add referenced root elements (bpmn:Error) if they don't exist.
 * Copy referenced root elements on copy & paste.
 */
export default class CopyPasteRootElementBehavior extends CommandInterceptor {
  constructor(bpmnFactory, bpmnjs, eventBus, moddleCopy) {
    super(eventBus);

    function hasRootElement(rootElement) {
      const definitions = bpmnjs.getDefinitions(),
            rootElements = definitions.get('rootElements');

      return !!find(rootElements, matchPattern({ id: rootElement.get('id') }));
    }

    // create shape
    this.executed('shape.create', (context) => {
      const { shape } = context;

      const businessObject = getBusinessObject(shape);

      if (!canHaveNestedRootElementReference(businessObject)) {
        return;
      }

      const referencedRootElements = getRootElements(businessObject, getReferencingElement(shape)),
            rootElements = bpmnjs.getDefinitions().get('rootElements');

      context.addedRootElements = [];

      referencedRootElements.forEach((reference) => {
        const { referencedElement } = reference;

        if (referencedElement && !hasRootElement(referencedElement)) {

          // add root element
          collectionAdd(rootElements, referencedElement);

          context.addedRootElements.push(referencedElement);
        }
      });
    }, true);

    this.reverted('shape.create', (context) => {
      const { addedRootElements } = context;

      if (!addedRootElements) {
        return;
      }

      const rootElements = bpmnjs.getDefinitions().get('rootElements');

      // remove root elements
      addedRootElements.forEach((addedRootElement) => {
        collectionRemove(rootElements, addedRootElement);
      });
    }, true);

    eventBus.on('copyPaste.copyElement', function(context) {
      const {
        descriptor,
        element
      } = context;

      const businessObject = getBusinessObject(element);

      if (element.labelTarget || !canHaveNestedRootElementReference(businessObject)) {
        return;
      }

      const rootElements = getRootElements(businessObject, getReferencingElement(element));

      if (rootElements) {
        descriptor.referencedRootElements = rootElements;
      }
    });

    eventBus.on('copyPaste.pasteElement', LOW_PRIORITY, (context) => {
      const { descriptor } = context;

      const {
        businessObject,
        referencedRootElements
      } = descriptor;

      if (!referencedRootElements) {
        return;
      }

      referencedRootElements.forEach((reference) => {
        let {
          idx,
          referencedElement
        } = reference;

        if (!referencedElement) {
          return;
        }

        if (!hasRootElement(referencedElement)) {
          referencedElement = moddleCopy.copyElement(
            referencedElement,
            bpmnFactory.create(referencedElement.$type)
          );
        }

        setRootElement(businessObject, referencedElement, idx);
      });

      delete descriptor.referencedRootElements;
    });
  }
}

CopyPasteRootElementBehavior.$inject = [
  'bpmnFactory',
  'bpmnjs',
  'eventBus',
  'moddleCopy'
];


// helpers //////////

function getReferencingElement(element) {
  if (is(element, 'bpmn:ServiceTask')) {
    return 'camunda:ErrorEventDefinition';
  }
}

function getRootElementReferencePropertyName(bo) {
  if (is(bo, 'camunda:ErrorEventDefinition')) {
    return 'errorRef';
  }
}

function canHaveNestedRootElementReference(businessObject) {
  return is(businessObject, 'bpmn:ServiceTask') && businessObject.get('type') === 'external';
}

/**
 * Retrieves a list of to-be copied references for the extension elements
 * of a given element in the following form.
 *
 * [
 *  {
 *    idx: 0, // position of extension in the list of extension elements
 *    referencedElement: {ModdleElement} // reference to root element
 *  }
 * ]
 *
 *
 * @param {ModdleElement} businessObject
 * @param {String} extensionElementType
 *
 * @returns {Array}
 */
function getRootElements(businessObject, extensionElementType) {
  const extensionElements = businessObject.get('extensionElements');

  if (!extensionElements) {
    return [];
  }

  return extensionElements
    .get('values')
    .filter((element) => is(element, extensionElementType))
    .reduce((result, element) => {
      const referencedElement = element.get(getRootElementReferencePropertyName(element));

      if (referencedElement) {
        result.push({
          idx: getExtensionElementId(businessObject, element),
          referencedElement
        });
      }

      return result;
    }, []);
}

function setRootElement(businessObject, rootElement, index) {
  const extensionElement = businessObject.get('extensionElements').get('values')[ index ];

  extensionElement.set(getRootElementReferencePropertyName(extensionElement), rootElement);
}

function getExtensionElementId(businessObject, extensionElement) {
  const extensionElements = businessObject.get('extensionElements');

  if (!extensionElements) {
    return -1;
  }

  return extensionElements.get('values').indexOf(extensionElement);
}
