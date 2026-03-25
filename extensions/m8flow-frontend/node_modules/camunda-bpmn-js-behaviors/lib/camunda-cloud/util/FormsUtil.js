import {
  getBusinessObject,
  is
} from 'bpmn-js/lib/util/ModelUtil';

import { getPrefixedId } from '../../util/IdsUtil';

import { getExtensionElementsList } from '../../util/ExtensionElementsUtil';

const FORM_KEY_PREFIX = 'camunda-forms:bpmn:',
      USER_TASK_FORM_ID_PREFIX = 'UserTaskForm_';

export function getFormDefinition(element) {
  const businessObject = getBusinessObject(element);

  const formDefinitions = getExtensionElementsList(businessObject, 'zeebe:FormDefinition');

  return formDefinitions[ 0 ];
}

export function getUserTaskForm(element, options = {}) {
  let {
    formKey,
    rootElement
  } = options;

  rootElement = rootElement || getRootElement(element);

  if (!formKey) {
    const formDefinition = getFormDefinition(element);

    if (!formDefinition) {
      return;
    }

    formKey = formDefinition.get('formKey');
  }

  const userTaskForms = getExtensionElementsList(rootElement, 'zeebe:UserTaskForm');

  return userTaskForms.find(userTaskForm => {
    return userTaskFormIdToFormKey(userTaskForm.get('id')) === formKey;
  });
}

export function userTaskFormIdToFormKey(userTaskFormId) {
  return `${ FORM_KEY_PREFIX }${ userTaskFormId }`;
}

export function formKeyToUserTaskFormId(formKey) {
  return formKey.replace(FORM_KEY_PREFIX, '');
}

export function isUserTaskFormKey(formKey) {
  return formKey && formKey.startsWith(FORM_KEY_PREFIX);
}

export function createUserTaskFormId() {
  return getPrefixedId(USER_TASK_FORM_ID_PREFIX);
}

export function getRootElement(element) {
  const businessObject = getBusinessObject(element);

  let parent = businessObject;

  while (parent.$parent && !is(parent, 'bpmn:Process')) {
    parent = parent.$parent;
  }

  return parent;
}