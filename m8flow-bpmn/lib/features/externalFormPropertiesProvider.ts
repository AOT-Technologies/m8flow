/**
 * "External Form URL" field on User Tasks — ported from m8flow-frontend's
 * `components/bpmn/ExternalFormPropertiesProvider.js` (a real m8flow-native
 * extension, not part of upstream bpmn-js-spiffworkflow: it slots a plain
 * URL field into the same "Web Form (with Json Schemas)" group
 * bpmn-js-spiffworkflow's own ExtensionsPropertiesProvider renders, keyed
 * off the same `user_task_properties` group id). `ExternalFormAwareTaskShow`
 * (m8flow-frontend) reads this value at runtime to decide whether a task
 * shows the built-in form renderer or redirects to an external URL.
 *
 * Ported, not re-derived from scratch, since the moddle-write plumbing
 * (getExtensionValue/setExtensionValue via SpiffExtensionTextInput) has to
 * match m8flow-frontend's own byte-for-byte — this is the same
 * `spiffworkflow:externalFormUrl` extension property either app writes into
 * the same .bpmn file.
 */
import { is } from 'bpmn-js/lib/util/ModelUtil';
// @ts-expect-error missing type declarations
import { SpiffExtensionTextInput } from 'bpmn-js-spiffworkflow/app/spiffworkflow/extensions/propertiesPanel/SpiffExtensionTextInput';

import { insertGroupAfter } from './propertiesPanelGroups';

const LOW_PRIORITY = 500;

export const EXTERNAL_FORM_URL_PROP = 'externalFormUrl';
export const EXTERNAL_FORM_GROUP_ID = 'external_form_properties';

// Upstream "Web Form (with Json Schemas)" group; ours slots in right after it.
const JSON_SCHEMA_GROUP_ID = 'user_task_properties';

export function ExternalFormPropertiesProvider(
  this: any,
  propertiesPanel: any,
  translate: any,
  moddle: any,
  commandStack: any,
) {
  this.getGroups = function (element: any) {
    return function (groups: any[]) {
      if (is(element, 'bpmn:UserTask')) {
        const group = createExternalFormGroup(element, translate, moddle, commandStack);
        insertGroupAfter(groups, group, JSON_SCHEMA_GROUP_ID);
      }
      return groups;
    };
  };
  propertiesPanel.registerProvider(LOW_PRIORITY, this);
}

(ExternalFormPropertiesProvider as any).$inject = ['propertiesPanel', 'translate', 'moddle', 'commandStack'];

function createExternalFormGroup(element: any, translate: any, moddle: any, commandStack: any) {
  return {
    id: EXTERNAL_FORM_GROUP_ID,
    label: translate('Web Form (External Form)'),
    entries: [
      {
        id: `extension_${EXTERNAL_FORM_URL_PROP}`,
        element,
        moddle,
        commandStack,
        component: SpiffExtensionTextInput,
        name: EXTERNAL_FORM_URL_PROP,
        label: translate('External form URL'),
        description: translate(
          'When set, this user task uses an external form. Assignees are emailed a secure link to this URL. Clear the field to disable.',
        ),
      },
    ],
  };
}

export const externalFormPropertiesModule = {
  __init__: ['externalFormPropertiesProvider'],
  externalFormPropertiesProvider: ['type', ExternalFormPropertiesProvider],
};
