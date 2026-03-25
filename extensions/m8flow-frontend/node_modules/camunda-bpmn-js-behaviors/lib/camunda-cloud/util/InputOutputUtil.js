import {
  getBusinessObject,
  is
} from 'bpmn-js/lib/util/ModelUtil';

import { createElement } from '../../util/ElementUtil';

/**
 * Get zeebe:IoMapping from an element.
 *
 * @param {djs.model.Base|ModdleElement} element
 *
 * @return {ModdleElement}
 */
export function getIoMapping(element) {
  const businessObject = getBusinessObject(element);

  const extensionElements = businessObject.get('extensionElements');

  if (!extensionElements) {
    return;
  }

  return extensionElements.get('values').find((value) => {
    return is(value, 'zeebe:IoMapping');
  });
}

/**
 * Get zeebe:InputParameters from an element.
 *
 * @param  {djs.model.Base|ModdleElement} element
 *
 * @return {Array<ModdleElement>}
 */
export function getInputParameters(element) {
  const ioMapping = getIoMapping(element);

  if (ioMapping) {
    return ioMapping.get('zeebe:inputParameters');
  }

  return [];
}

/**
 * Get zeebe:OutputParameters from an element.
 *
 * @param  {djs.model.Base|ModdleElement} element
 *
 * @return {Array<ModdleElement>}
 */
export function getOutputParameters(element) {
  const ioMapping = getIoMapping(element);

  if (ioMapping) {
    return ioMapping.get('zeebe:outputParameters');
  }

  return [];
}

/**
 * Get zeebe:Input at index.
 *
 * @param {djs.model.Base|ModdleElement} element
 * @param {number} index
 *
 * @return {ModdleElement}
 */
export function getInputParameter(element, index) {
  return getInputParameters(element)[ index ];
}

/**
 * Get zeebe:Output at index.
 *
 * @param {djs.model.Base|ModdleElement} element
 * @param {number} index
 *
 * @return {ModdleElement}
 */
export function getOutputParameter(element, index) {
  return getOutputParameters(element)[ index ];
}

export function createIoMapping(parent, bpmnFactory, properties) {
  return createElement('zeebe:IoMapping', properties, parent, bpmnFactory);
}
