import { is } from 'bpmn-js/lib/util/ModelUtil';
import { SpiffExtensionTextInput } from 'bpmn-js-spiffworkflow/app/spiffworkflow/extensions/propertiesPanel/SpiffExtensionTextInput';
import { createElement } from '@bpmn-io/properties-panel/preact';
import {
  ExternalFormSmtpLabel,
  ExternalFormSmtpStatus,
} from './ExternalFormSmtpStatus';

const LOW_PRIORITY = 500;

export const EXTERNAL_FORM_URL_PROP = 'externalFormUrl';
export const EXTERNAL_FORM_GROUP_ID = 'external_form_properties';

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
    // A VNode, not a plain string: the panel renders `label` as TooltipWrapper children,
    // and this is the only part of the group that stays visible while it is collapsed.
    // ExternalFormSmtpLabel appends a warning marker when the tenant cannot send email,
    // so the modeler sees the problem without having to expand the group first.
    label: createElement(ExternalFormSmtpLabel, {
      label: translate('Web Form (External Form)'),
    }),
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
          'When set, this user task uses an external form. Assignees are emailed a secure link to this URL. Clear the field to disable.'
        ),
      },
      {
        // Warns when the tenant has no usable NATS_SMTP_* secrets, so the emailed link
        // this field promises would never actually be delivered. Renders nothing when
        // SMTP is configured, or when the status cannot be read.
        id: 'extension_externalFormSmtpStatus',
        element,
        component: ExternalFormSmtpStatus,
      },
    ],
  };
}
