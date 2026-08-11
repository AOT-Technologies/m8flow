import { is } from 'bpmn-js/lib/util/ModelUtil';
import { SpiffExtensionTextInput } from 'bpmn-js-spiffworkflow/app/spiffworkflow/extensions/propertiesPanel/SpiffExtensionTextInput';
import { ExternalFormSmtpStatus } from './ExternalFormSmtpStatus';

const LOW_PRIORITY = 500;

export const EXTERNAL_FORM_URL_PROP = 'externalFormUrl';
export const EXTERNAL_FORM_GROUP_ID = 'external_form_properties';
export const EXTERNAL_FORM_SMTP_STATUS_ENTRY_ID = 'external_form_smtp_status';

// Upstream "Web Form (with Json Schemas)" group; we slot ours right after it.
const JSON_SCHEMA_GROUP_ID = 'user_task_properties';

export default function ExternalFormPropertiesProvider(
  propertiesPanel,
  translate,
  moddle,
  commandStack
) {
  this.getGroups = function (element) {
    return function (groups) {
      if (is(element, 'bpmn:UserTask')) {
        const group = createExternalFormGroup(
          element,
          translate,
          moddle,
          commandStack
        );
        const anchorIndex = groups.findIndex(
          (g) => g && g.id === JSON_SCHEMA_GROUP_ID
        );
        if (anchorIndex === -1) {
          groups.push(group);
        } else {
          groups.splice(anchorIndex + 1, 0, group);
        }
      }
      return groups;
    };
  };
  propertiesPanel.registerProvider(LOW_PRIORITY, this);
}

ExternalFormPropertiesProvider.$inject = [
  'propertiesPanel',
  'translate',
  'moddle',
  'commandStack',
];

function createExternalFormGroup(element, translate, moddle, commandStack) {
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
          'When set, this user task uses an external form. Assignees are emailed a secure link to this URL. Clear the field to disable. Sending requires the NATS_SMTP_HOST and NATS_SMTP_FROM_EMAIL tenant secrets under Configuration > Secrets.'
        ),
      },
      {
        // Live warning when this tenant cannot actually send the email the field above
        // promises. Renders nothing when SMTP is configured or the status is unknown.
        id: EXTERNAL_FORM_SMTP_STATUS_ENTRY_ID,
        element,
        component: ExternalFormSmtpStatus,
      },
    ],
  };
}
